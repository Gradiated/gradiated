use std::path::{Path, PathBuf};

use barge::config::EngineConfig;
use barge::engine::{Engine, Request};
use barge::kv::KvCache;
use barge::model::Model;
use barge::sample::SamplingParams;
use barge::sched::Out;
use candle_core::{DType, Device, Tensor};
use candle_nn::VarBuilder;
use candle_transformers::models::llama as ref_llama;

const PROMPT: [u32; 16] = [
    1, 306, 763, 304, 4380, 285, 728, 297, 278, 4556, 310, 263, 521, 431, 1078, 29889,
];
const MAX_CTX: usize = 64;

fn models_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../models")
}

fn load_barge(model: &str) -> (Model, KvCache) {
    let dev = Device::Cpu;
    let model = Model::load(&models_root().join(model), DType::F32, &dev, MAX_CTX).unwrap();
    let kv = KvCache::new(
        model.cfg.num_hidden_layers,
        4,
        MAX_CTX,
        model.cfg.num_key_value_heads,
        model.cfg.head_dim(),
        DType::F32,
        &dev,
    )
    .unwrap();
    (model, kv)
}

fn ref_last_logits(model: &str, cfg: &ref_llama::Config, tokens: &[u32]) -> Tensor {
    let dev = Device::Cpu;
    let file = models_root().join(model).join("model.safetensors");
    let vb = unsafe { VarBuilder::from_mmaped_safetensors(&[file], DType::F32, &dev).unwrap() };
    let llama = ref_llama::Llama::load(vb, cfg).unwrap();
    let mut cache = ref_llama::Cache::new(true, DType::F32, cfg, &dev).unwrap();
    let x = Tensor::from_slice(tokens, (1, tokens.len()), &dev).unwrap();
    llama.forward(&x, 0, &mut cache).unwrap()
}

// tinyllama-15m config.json predates some LlamaConfig fields; build directly.
fn tinyllama_ref_config() -> ref_llama::Config {
    ref_llama::Config {
        hidden_size: 288,
        intermediate_size: 768,
        vocab_size: 32000,
        num_hidden_layers: 6,
        num_attention_heads: 6,
        num_key_value_heads: 6,
        use_flash_attn: false,
        rms_norm_eps: 1e-5,
        rope_theta: 10000.0,
        bos_token_id: Some(1),
        eos_token_id: Some(ref_llama::LlamaEosToks::Single(2)),
        rope_scaling: None,
        max_position_embeddings: 256,
        tie_word_embeddings: true,
    }
}

fn smollm2_ref_config() -> ref_llama::Config {
    ref_llama::Config {
        hidden_size: 576,
        intermediate_size: 1536,
        vocab_size: 49152,
        num_hidden_layers: 30,
        num_attention_heads: 9,
        num_key_value_heads: 3,
        use_flash_attn: false,
        rms_norm_eps: 1e-5,
        rope_theta: 100000.0,
        bos_token_id: Some(1),
        eos_token_id: Some(ref_llama::LlamaEosToks::Single(2)),
        rope_scaling: None,
        max_position_embeddings: 8192,
        tie_word_embeddings: true,
    }
}

fn max_abs_diff(a: &Tensor, b: &Tensor) -> f32 {
    let a: Vec<f32> = a.flatten_all().unwrap().to_vec1().unwrap();
    let b: Vec<f32> = b.flatten_all().unwrap().to_vec1().unwrap();
    assert_eq!(a.len(), b.len(), "logit vectors differ in length");
    a.iter()
        .zip(&b)
        .map(|(x, y)| (x - y).abs())
        .fold(0f32, f32::max)
}

#[test]
fn logits_parity_tinyllama() {
    let (model, kv) = load_barge("tinyllama-15m");
    let ours = model.prefill(&kv, 0, 0, &PROMPT, true).unwrap().unwrap();
    let theirs = ref_last_logits("tinyllama-15m", &tinyllama_ref_config(), &PROMPT);
    let d = max_abs_diff(&ours, &theirs);
    eprintln!("logits_parity_tinyllama max abs diff = {d:e}");
    assert!(d < 1e-3, "barge vs candle-transformers logits diverge: max abs diff {d}");
}

#[test]
fn logits_parity_smollm2_gqa() {
    let (model, kv) = load_barge("smollm2-135m-instruct");
    let ours = model.prefill(&kv, 0, 0, &PROMPT, true).unwrap().unwrap();
    let theirs = ref_last_logits("smollm2-135m-instruct", &smollm2_ref_config(), &PROMPT);
    let d = max_abs_diff(&ours, &theirs);
    eprintln!("logits_parity_smollm2_gqa max abs diff = {d:e}");
    assert!(d < 1e-3, "barge vs candle-transformers logits diverge (GQA): max abs diff {d}");
}

#[test]
fn chunked_prefill_equivalence() {
    let (model, kv) = load_barge("tinyllama-15m");
    let full = model.prefill(&kv, 0, 0, &PROMPT, true).unwrap().unwrap();
    assert!(model.prefill(&kv, 1, 0, &PROMPT[..9], false).unwrap().is_none());
    let chunked = model.prefill(&kv, 1, 9, &PROMPT[9..], true).unwrap().unwrap();
    let d = max_abs_diff(&full, &chunked);
    eprintln!("chunked_prefill_equivalence max abs diff = {d:e}");
    assert!(d < 1e-4, "one-shot vs 9+7 chunked prefill logits diverge: max abs diff {d}");
}

#[test]
fn decode_matches_prefill() {
    let (model, kv) = load_barge("tinyllama-15m");
    let n = PROMPT.len() - 1;
    assert!(model.prefill(&kv, 0, 0, &PROMPT[..n], false).unwrap().is_none());
    let decoded = model.decode(&kv, &[n], &[PROMPT[n]]).unwrap();

    let (_, kv2) = load_barge("tinyllama-15m");
    let full = model.prefill(&kv2, 0, 0, &PROMPT, true).unwrap().unwrap();
    let d = max_abs_diff(&decoded, &full);
    eprintln!("decode_matches_prefill max abs diff = {d:e}");
    assert!(d < 1e-3, "decode at position {n} vs direct prefill logits diverge: max abs diff {d}");
}

fn greedy() -> SamplingParams {
    SamplingParams {
        temperature: 0.0,
        top_p: 1.0,
        top_k: 0,
        max_tokens: 16,
        seed: 0,
        ignore_eos: false,
        stop: vec![],
    }
}

/// Run prompts through a fresh Engine; returns each request's emitted token
/// ids in submission order.
fn run_engine(prompts: &[Vec<u32>]) -> Vec<Vec<u32>> {
    let dev = Device::Cpu;
    let model = Model::load(&models_root().join("tinyllama-15m"), DType::F32, &dev, MAX_CTX).unwrap();
    let ecfg = EngineConfig {
        max_slots: 16,
        max_ctx: MAX_CTX,
        prefill_chunk: 64,
        dtype: DType::F32,
        device: dev,
    };
    let mut engine = Engine::new(model, &ecfg).unwrap();
    let (tx, rx) = std::sync::mpsc::channel();
    let mut outs = Vec::new();
    for p in prompts {
        let (otx, orx) = tokio::sync::mpsc::unbounded_channel();
        tx.send(Request {
            prompt: p.clone(),
            params: greedy(),
            tx: otx,
        })
        .unwrap();
        outs.push(orx);
    }
    drop(tx);
    engine.run(rx).unwrap();
    outs.into_iter()
        .map(|mut orx| {
            let mut toks = Vec::new();
            let mut done = false;
            while let Ok(out) = orx.try_recv() {
                match out {
                    Out::Token(t) => toks.push(t),
                    Out::Done { .. } => {
                        done = true;
                        break;
                    }
                }
            }
            assert!(done, "request finished without Out::Done");
            toks
        })
        .collect()
}

fn different_prompts() -> Vec<Vec<u32>> {
    (0..8u64)
        .map(|i| {
            let len = 4 + 2 * i as usize;
            let mut toks = vec![1u32];
            let mut x = 0x9E3779B97F4A7C15u64.wrapping_mul(i + 1);
            for _ in 1..len {
                x = x
                    .wrapping_mul(6364136223846793005)
                    .wrapping_add(1442695040888963407);
                toks.push((x >> 33) as u32 % 32000);
            }
            toks
        })
        .collect()
}

#[test]
fn batch_invariance_identical_prompts() {
    let solo = run_engine(std::slice::from_ref(&PROMPT.to_vec()));
    assert!(!solo[0].is_empty(), "solo run produced no tokens");
    let batch = run_engine(&vec![PROMPT.to_vec(); 8]);
    for (i, out) in batch.iter().enumerate() {
        assert_eq!(
            &solo[0], out,
            "identical request {i} in batch of 8 diverged from solo run"
        );
    }
}

#[test]
fn batch_invariance_different_prompts() {
    let prompts = different_prompts();
    let solos: Vec<Vec<u32>> = prompts
        .iter()
        .map(|p| run_engine(std::slice::from_ref(p)).remove(0))
        .collect();
    let batch = run_engine(&prompts);
    for i in 0..prompts.len() {
        assert_eq!(
            solos[i], batch[i],
            "prompt {i} (len {}) diverged between solo and batched run",
            prompts[i].len()
        );
    }
}
