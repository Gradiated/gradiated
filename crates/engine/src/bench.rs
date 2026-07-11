//! Offline throughput benchmark, metric-compatible with vLLM's
//! benchmark_throughput.py: submit all requests at t=0, run to completion,
//! report total and output token throughput. JSON out for the experiment
//! ledger.
use crate::config::EngineConfig;
use crate::engine::{Engine, Request};
use crate::model::Model;
use crate::sample::SamplingParams;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::time::Instant;
use tokenizers::Tokenizer;

#[derive(Debug, Clone, Serialize)]
pub struct BenchConfig {
    pub model: String,
    pub device: String,
    pub dtype: String,
    pub num_requests: usize,
    pub input_len: Option<usize>,
    pub output_len: usize,
    pub dataset: Option<String>,
    pub max_slots: usize,
    pub max_ctx: usize,
    pub prefill_chunk: usize,
}

#[derive(Debug, Serialize)]
pub struct BenchResult {
    #[serde(flatten)]
    pub config: BenchConfig,
    pub total_prompt_tokens: u64,
    pub total_output_tokens: u64,
    pub wall_s: f64,
    /// (prompt + output) tokens / wall — vLLM's "total token throughput".
    pub total_tok_per_s: f64,
    /// output tokens / wall — vLLM's "output token throughput".
    pub output_tok_per_s: f64,
    pub requests_per_s: f64,
    pub steps: u64,
    pub avg_decode_batch: f64,
    pub timestamp: String,
}

#[derive(Deserialize)]
struct ShareGptConv {
    conversations: Vec<ShareGptTurn>,
}
#[derive(Deserialize)]
struct ShareGptTurn {
    from: String,
    value: String,
}

/// (prompt_token_ids, output_len) pairs.
fn build_workload(
    tokenizer: &Tokenizer,
    n: usize,
    input_len: Option<usize>,
    output_len: usize,
    dataset: &Option<PathBuf>,
    max_ctx: usize,
    vocab: usize,
) -> Result<Vec<(Vec<u32>, usize)>> {
    if let Some(path) = dataset {
        let raw = std::fs::read_to_string(path).context("reading dataset")?;
        let convs: Vec<ShareGptConv> = serde_json::from_str(&raw).context("parsing ShareGPT")?;
        let mut out = vec![];
        for c in convs {
            if out.len() >= n {
                break;
            }
            let human = c.conversations.iter().find(|t| t.from == "human");
            let gpt = c.conversations.iter().find(|t| t.from == "gpt");
            let (Some(h), Some(g)) = (human, gpt) else {
                continue;
            };
            let p = tokenizer
                .encode(h.value.as_str(), false)
                .map_err(|e| anyhow::anyhow!("{e}"))?
                .get_ids()
                .to_vec();
            let glen = tokenizer
                .encode(g.value.as_str(), false)
                .map_err(|e| anyhow::anyhow!("{e}"))?
                .get_ids()
                .len();
            // vLLM's ShareGPT filter: drop tiny and oversized samples.
            if p.len() < 4 || glen < 4 {
                continue;
            }
            let o = glen.min(output_len);
            if p.len() + o > max_ctx {
                continue;
            }
            out.push((p, o));
        }
        anyhow::ensure!(out.len() == n, "dataset yielded only {} of {n} usable prompts", out.len());
        Ok(out)
    } else {
        // Synthetic: fixed-length random-token prompts (vLLM benchmark style).
        let ilen = input_len.unwrap_or(128);
        anyhow::ensure!(ilen + output_len <= max_ctx, "input+output exceeds max_ctx");
        use rand::{Rng, SeedableRng};
        let mut rng = rand::rngs::StdRng::seed_from_u64(0);
        Ok((0..n)
            .map(|_| {
                let p: Vec<u32> = (0..ilen)
                    .map(|_| rng.random_range(0..vocab as u32))
                    .collect();
                (p, output_len)
            })
            .collect())
    }
}

#[allow(clippy::too_many_arguments)]
pub fn run_bench(
    model_dir: &Path,
    cfg: BenchConfig,
    dataset: Option<PathBuf>,
    results_path: Option<PathBuf>,
) -> Result<BenchResult> {
    let dev = crate::parse_device(&cfg.device)?;
    let dt = crate::parse_dtype(&cfg.dtype)?;
    let ecfg = EngineConfig {
        max_slots: cfg.max_slots,
        max_ctx: cfg.max_ctx,
        prefill_chunk: cfg.prefill_chunk,
        dtype: dt,
        device: dev.clone(),
    };
    let model = Model::load(model_dir, dt, &dev, cfg.max_ctx)?;
    let tokenizer = Tokenizer::from_file(model_dir.join("tokenizer.json"))
        .map_err(|e| anyhow::anyhow!("tokenizer: {e}"))?;
    let vocab = model.cfg.vocab_size;
    let workload = build_workload(
        &tokenizer,
        cfg.num_requests,
        cfg.input_len,
        cfg.output_len,
        &dataset,
        cfg.max_ctx,
        vocab,
    )?;
    let total_prompt_tokens: u64 = workload.iter().map(|(p, _)| p.len() as u64).sum();
    let expected_output: u64 = workload.iter().map(|(_, o)| *o as u64).sum();

    let mut engine = Engine::new(model, &ecfg)?;
    // Warmup: absorb Metal pipeline compilation outside the timed window.
    {
        let (tx, rx) = std::sync::mpsc::channel();
        let (otx, _orx) = tokio::sync::mpsc::unbounded_channel();
        tx.send(Request {
            prompt: vec![1, 2, 3, 4],
            params: SamplingParams {
                temperature: 0.0,
                max_tokens: 4,
                ignore_eos: true,
                ..Default::default()
            },
            tx: otx,
        })?;
        drop(tx);
        engine.run(rx)?;
        engine.stats = Default::default();
    }

    let (tx, rx) = std::sync::mpsc::channel();
    let mut sinks = vec![];
    for (i, (prompt, out_len)) in workload.into_iter().enumerate() {
        let (otx, orx) = tokio::sync::mpsc::unbounded_channel();
        sinks.push(orx);
        tx.send(Request {
            prompt,
            params: SamplingParams {
                temperature: 0.0,
                max_tokens: out_len,
                ignore_eos: true, // fixed output length, vLLM-bench style
                seed: i as u64,
                ..Default::default()
            },
            tx: otx,
        })?;
    }
    drop(tx);
    let t0 = Instant::now();
    engine.run(rx)?;
    let wall = t0.elapsed().as_secs_f64();

    let s = engine.stats.clone();
    anyhow::ensure!(
        s.decode_tokens + (sinks.len() as u64) >= expected_output,
        "generated {} tokens, expected {expected_output}",
        s.decode_tokens + sinks.len() as u64
    );
    let total_output = expected_output;
    let result = BenchResult {
        total_prompt_tokens,
        total_output_tokens: total_output,
        wall_s: wall,
        total_tok_per_s: (total_prompt_tokens + total_output) as f64 / wall,
        output_tok_per_s: total_output as f64 / wall,
        requests_per_s: cfg.num_requests as f64 / wall,
        steps: s.steps,
        avg_decode_batch: s.decode_batch_sum as f64 / s.steps.max(1) as f64,
        timestamp: chrono_lite_now(),
        config: cfg,
    };
    let line = serde_json::to_string(&result)?;
    println!("{line}");
    if let Some(p) = results_path {
        if let Some(dir) = p.parent() {
            std::fs::create_dir_all(dir)?;
        }
        use std::io::Write;
        let mut f = std::fs::OpenOptions::new().create(true).append(true).open(p)?;
        writeln!(f, "{line}")?;
    }
    Ok(result)
}

fn chrono_lite_now() -> String {
    let d = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap();
    format!("unix:{}", d.as_secs())
}
