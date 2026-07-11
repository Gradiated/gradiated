use anyhow::{Context, Result};
use barge::config::EngineConfig;
use barge::engine::{Engine, Request};
use barge::model::{make_random_model, Model};
use barge::sample::SamplingParams;
use barge::sched::Out;
use barge::{parse_device, parse_dtype};
use clap::{Parser, Subcommand};
use std::path::PathBuf;
use std::time::Instant;
use tokenizers::Tokenizer;

#[derive(Parser)]
#[command(name = "barge", about = "cost-first LLM serving engine")]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Generate from prompts (engine smoke test / micro-bench).
    Gen {
        #[arg(long)]
        model: PathBuf,
        #[arg(long, default_value = "Once upon a time")]
        prompt: String,
        /// Number of identical requests to submit (batch saturation test).
        #[arg(long, default_value_t = 1)]
        n: usize,
        #[arg(long, default_value_t = 64)]
        max_tokens: usize,
        #[arg(long, default_value = "metal")]
        device: String,
        #[arg(long, default_value = "f16")]
        dtype: String,
        #[arg(long, default_value_t = 0.0)]
        temp: f32,
        #[arg(long, default_value_t = 64)]
        max_slots: usize,
        #[arg(long, default_value_t = 2048)]
        max_ctx: usize,
        #[arg(long, default_value_t = 512)]
        prefill_chunk: usize,
        /// Apply the model's chat template to the prompt.
        #[arg(long, default_value_t = false)]
        chat: bool,
    },
    /// Op-level microbenchmarks on engine shapes (device fingerprinting).
    Probe {
        #[arg(long)]
        model: PathBuf,
        #[arg(long, default_value = "metal")]
        device: String,
        #[arg(long, default_value = "f16")]
        dtype: String,
        #[arg(long, default_value_t = 32)]
        b: usize,
    },
    /// Write a random-weight model dir from a config.json (benchmarking
    /// without downloads — identical compute cost to real weights).
    MakeModel {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        out: PathBuf,
        #[arg(long, default_value = "f16")]
        dtype: String,
    },
}

fn main() -> Result<()> {
    match Cli::parse().cmd {
        Cmd::Gen {
            model,
            prompt,
            n,
            max_tokens,
            device,
            dtype,
            temp,
            max_slots,
            max_ctx,
            prefill_chunk,
            chat,
        } => {
            let dev = parse_device(&device)?;
            let dt = parse_dtype(&dtype)?;
            let ecfg = EngineConfig {
                max_slots,
                max_ctx,
                prefill_chunk,
                dtype: dt,
                device: dev.clone(),
            };
            let t0 = Instant::now();
            let m = Model::load(&model, dt, &dev, max_ctx).context("loading model")?;
            let tokenizer = Tokenizer::from_file(model.join("tokenizer.json"))
                .map_err(|e| anyhow::anyhow!("tokenizer: {e}"))?;
            eprintln!(
                "loaded {} ({} layers) in {:.2}s; kv budget {:.1} MB",
                model.display(),
                m.cfg.num_hidden_layers,
                t0.elapsed().as_secs_f64(),
                ecfg.kv_bytes(&m.cfg) as f64 / 1e6
            );

            let text = if chat {
                barge::detok::ChatTemplate::detect(&model)
                    .render(&[("user".into(), prompt.clone())])
            } else {
                prompt.clone()
            };
            let ids = tokenizer
                .encode(text, false)
                .map_err(|e| anyhow::anyhow!("encode: {e}"))?
                .get_ids()
                .to_vec();
            eprintln!("prompt tokens: {}", ids.len());

            let mut engine = Engine::new(m, &ecfg)?;
            let (tx, rx) = std::sync::mpsc::channel();
            let mut streams = vec![];
            for i in 0..n {
                let (otx, orx) = tokio::sync::mpsc::unbounded_channel();
                streams.push(orx);
                tx.send(Request {
                    prompt: ids.clone(),
                    params: SamplingParams {
                        temperature: temp,
                        max_tokens,
                        seed: i as u64,
                        ..Default::default()
                    },
                    tx: otx,
                })?;
            }
            drop(tx);
            let t1 = Instant::now();
            engine.run(rx)?;
            let wall = t1.elapsed().as_secs_f64();

            for (i, orx) in streams.iter_mut().enumerate() {
                let mut toks = vec![];
                while let Ok(o) = orx.try_recv() {
                    if let Out::Token(t) = o {
                        toks.push(t);
                    }
                }
                if i == 0 || i + 1 == n {
                    let text = tokenizer
                        .decode(&toks, true)
                        .map_err(|e| anyhow::anyhow!("decode: {e}"))?;
                    println!("--- seq {i} ({} tokens) ---\n{text}\n", toks.len());
                }
            }
            let s = &engine.stats;
            eprintln!(
                "wall {:.2}s | {} steps | prefill {} tok | decode {} tok | avg decode batch {:.1} | decode tok/s {:.1} | total tok/s {:.1}",
                wall,
                s.steps,
                s.prefill_tokens,
                s.decode_tokens,
                s.decode_batch_sum as f64 / s.steps.max(1) as f64,
                s.decode_tokens as f64 / wall,
                (s.prefill_tokens + s.decode_tokens) as f64 / wall,
            );
        }
        Cmd::Probe {
            model,
            device,
            dtype,
            b,
        } => {
            barge::probe::run_probe(&model, &parse_device(&device)?, parse_dtype(&dtype)?, b)?;
        }
        Cmd::MakeModel { config, out, dtype } => {
            make_random_model(&config, &out, parse_dtype(&dtype)?)?;
            println!("wrote random-weight model to {}", out.display());
        }
    }
    Ok(())
}
