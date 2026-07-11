use anyhow::{Context, Result};
use candle_core::{DType, Device};
use serde::Deserialize;
use std::path::Path;

/// Llama-family model config, read from a HuggingFace config.json.
#[derive(Debug, Clone, Deserialize)]
pub struct ModelConfig {
    pub hidden_size: usize,
    pub intermediate_size: usize,
    pub num_hidden_layers: usize,
    pub num_attention_heads: usize,
    pub num_key_value_heads: usize,
    pub vocab_size: usize,
    pub rms_norm_eps: f64,
    #[serde(default = "default_rope_theta")]
    pub rope_theta: f64,
    pub max_position_embeddings: usize,
    #[serde(default)]
    pub tie_word_embeddings: bool,
    #[serde(default)]
    pub attention_bias: bool,
    #[serde(default, deserialize_with = "deser_eos")]
    pub eos_token_id: Vec<u32>,
    #[serde(default)]
    pub head_dim: Option<usize>,
}

fn default_rope_theta() -> f64 {
    10000.0
}

/// eos_token_id is either a single int or a list in HF configs.
fn deser_eos<'de, D: serde::Deserializer<'de>>(d: D) -> Result<Vec<u32>, D::Error> {
    #[derive(Deserialize)]
    #[serde(untagged)]
    enum OneOrMany {
        One(u32),
        Many(Vec<u32>),
    }
    Ok(match Option::<OneOrMany>::deserialize(d)? {
        Some(OneOrMany::One(x)) => vec![x],
        Some(OneOrMany::Many(xs)) => xs,
        None => vec![],
    })
}

impl ModelConfig {
    pub fn load(model_dir: &Path) -> Result<Self> {
        let raw = std::fs::read_to_string(model_dir.join("config.json"))
            .with_context(|| format!("reading {}/config.json", model_dir.display()))?;
        let cfg: ModelConfig = serde_json::from_str(&raw).context("parsing config.json")?;
        Ok(cfg)
    }

    pub fn head_dim(&self) -> usize {
        self.head_dim
            .unwrap_or(self.hidden_size / self.num_attention_heads)
    }

    pub fn group_size(&self) -> usize {
        self.num_attention_heads / self.num_key_value_heads
    }
}

/// Engine-level knobs. Cost-first defaults: big batch, explicit context budget.
#[derive(Debug, Clone)]
pub struct EngineConfig {
    pub max_slots: usize,
    /// Per-sequence context budget (prompt + output). KV is preallocated to
    /// max_slots * max_ctx; admission enforces the budget, so the engine can
    /// never OOM or preempt mid-flight.
    pub max_ctx: usize,
    pub prefill_chunk: usize,
    pub dtype: DType,
    pub device: Device,
}

impl EngineConfig {
    pub fn kv_bytes(&self, m: &ModelConfig) -> usize {
        2 * m.num_hidden_layers
            * self.max_slots
            * self.max_ctx
            * m.num_key_value_heads
            * m.head_dim()
            * self.dtype.size_in_bytes()
    }
}
