//! Stack-configuration schemas. A simulation run is a pure function:
//! (ModelSpec, HardwareSpec, KernelSpec, ServingSpec, WorkloadSpec) -> PerfReport
//! and CostSpec maps PerfReport -> $/Mtok under an Objective.
//!
//! Every efficiency parameter is calibratable: it must correspond to
//! something measurable (barge probe/bench on local hardware, or a public
//! benchmark anchor), and configs carry a `calibration` note saying which.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Attention {
    /// Grouped-query attention; kv_heads == heads means MHA.
    Gqa,
    /// Multi-head latent attention (DeepSeek/GLM-5 family): KV cached as a
    /// shared latent of `kv_lora_rank` + `qk_rope_dim` per token per layer.
    /// Decode uses absorbed matmuls: scores/values run against the latent
    /// directly (per-head compute scales with the latent dim — MLA's
    /// deliberate compute-for-memory trade).
    Mla {
        kv_lora_rank: usize,
        qk_rope_dim: usize,
        q_lora_rank: usize,
        qk_nope_head_dim: usize,
        v_head_dim: usize,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Ffn {
    Dense,
    /// Fine-grained MoE: `experts` routed, `top_k` chosen, optional shared
    /// experts always active. `moe_intermediate` is per-expert width.
    Moe {
        experts: usize,
        top_k: usize,
        shared_experts: usize,
        moe_intermediate: usize,
        /// Layers 0..first_k_dense use the dense FFN instead.
        first_k_dense: usize,
        /// Width of EACH shared expert (decoupled from routed width);
        /// None = same as moe_intermediate.
        #[serde(default)]
        shared_intermediate: Option<usize>,
    },
}

/// Sparse attention (DSA-style top-k token selection) — bounds effective
/// attended context. None = full attention.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SparseAttention {
    pub index_top_k: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelSpec {
    pub name: String,
    pub layers: usize,
    pub hidden: usize,
    pub heads: usize,
    pub kv_heads: usize,
    pub head_dim: usize,
    pub intermediate: usize,
    pub vocab: usize,
    pub tied_embeddings: bool,
    pub attention: Attention,
    pub ffn: Ffn,
    pub sparse_attention: Option<SparseAttention>,
    /// Bytes per weight element (2.0 f16/bf16, 1.0 fp8, 0.5 int4).
    pub weight_bytes: f64,
    /// Bytes per KV cache element.
    pub kv_bytes: f64,
    /// Multi-token prediction: expected extra accepted tokens per decode step
    /// (0 = MTP off; DeepSeek/GLM report ~0.7-0.85 with one MTP layer).
    #[serde(default)]
    pub mtp_accept: f64,
    // --- surgery knobs: model modifications that require finetune-healing ---
    /// Fraction of routed tokens that must leave the local EP rank after
    /// routing-locality finetuning (1.0 = random routing). Grounded by
    /// measured expert co-activation statistics (twin experiments).
    #[serde(default = "one")]
    pub expert_locality: f64,
    /// Adjacent layers sharing one KV latent/cache (CLA-style, healed).
    /// 1 = no sharing; 2 = pairs (halves KV bytes and kv_down weights).
    #[serde(default = "one_u")]
    pub kv_share_layers: usize,
    /// MoE top_k used for prompt tokens only (asymmetric routing: prompts
    /// route through fewer experts than generation; healed). None = same.
    #[serde(default)]
    pub prefill_top_k: Option<usize>,
}

fn one_u() -> usize {
    1
}

impl ModelSpec {
    /// Attention block parameter count per layer (q/k/v/o projections).
    pub fn attn_params_per_layer(&self) -> f64 {
        let d = self.hidden as f64;
        match &self.attention {
            Attention::Gqa => {
                let qo = 2.0 * d * (self.heads * self.head_dim) as f64;
                let kv = 2.0 * d * (self.kv_heads * self.head_dim) as f64;
                qo + kv
            }
            Attention::Mla {
                kv_lora_rank,
                qk_rope_dim,
                q_lora_rank,
                qk_nope_head_dim,
                v_head_dim,
            } => {
                let h = self.heads as f64;
                let (r_kv, r_q) = (*kv_lora_rank as f64, *q_lora_rank as f64);
                let (nope, rope, vh) = (*qk_nope_head_dim as f64, *qk_rope_dim as f64, *v_head_dim as f64);
                d * r_q // q down
                    + r_q * h * (nope + rope) // q up
                    + d * (r_kv + rope) // kv down
                    + r_kv * h * (nope + vh) // kv up (absorbed at decode)
                    + h * vh * d // o
            }
        }
    }

    fn ffn_params_active_per_layer(&self) -> f64 {
        let d = self.hidden as f64;
        match &self.ffn {
            Ffn::Dense => 3.0 * d * self.intermediate as f64,
            Ffn::Moe {
                top_k,
                shared_experts,
                moe_intermediate,
                shared_intermediate,
                ..
            } => {
                let sw = shared_intermediate.unwrap_or(*moe_intermediate) as f64;
                3.0 * d * (*moe_intermediate as f64 * *top_k as f64 + sw * *shared_experts as f64)
            }
        }
    }

    fn ffn_params_total_per_layer(&self) -> f64 {
        let d = self.hidden as f64;
        match &self.ffn {
            Ffn::Dense => 3.0 * d * self.intermediate as f64,
            Ffn::Moe {
                experts,
                shared_experts,
                moe_intermediate,
                shared_intermediate,
                ..
            } => {
                let sw = shared_intermediate.unwrap_or(*moe_intermediate) as f64;
                3.0 * d * (*moe_intermediate as f64 * *experts as f64 + sw * *shared_experts as f64)
            }
        }
    }

    fn dense_ffn_layers(&self) -> usize {
        match &self.ffn {
            Ffn::Dense => self.layers,
            Ffn::Moe { first_k_dense, .. } => *first_k_dense,
        }
    }

    pub fn embed_params(&self) -> f64 {
        let e = (self.vocab * self.hidden) as f64;
        if self.tied_embeddings {
            e
        } else {
            2.0 * e
        }
    }

    /// Total parameters (storage).
    pub fn total_params(&self) -> f64 {
        let moe_layers = self.layers - self.dense_ffn_layers();
        let dense_layers = self.dense_ffn_layers();
        let d = self.hidden as f64;
        let dense_ffn = 3.0 * d * self.intermediate as f64;
        self.embed_params()
            + self.layers as f64 * self.attn_params_per_layer()
            + dense_layers as f64 * dense_ffn
            + moe_layers as f64 * self.ffn_params_total_per_layer()
    }

    /// Parameters touched per token at decode (active path + lm_head).
    pub fn active_params(&self) -> f64 {
        let moe_layers = self.layers - self.dense_ffn_layers();
        let dense_layers = self.dense_ffn_layers();
        let d = self.hidden as f64;
        let dense_ffn = 3.0 * d * self.intermediate as f64;
        (self.vocab * self.hidden) as f64 // lm_head matmul always runs
            + self.layers as f64 * self.attn_params_per_layer()
            + dense_layers as f64 * dense_ffn
            + moe_layers as f64 * self.ffn_params_active_per_layer()
    }

    /// KV cache bytes per token (all layers).
    pub fn kv_bytes_per_token(&self) -> f64 {
        let per_layer = match &self.attention {
            Attention::Gqa => 2.0 * (self.kv_heads * self.head_dim) as f64,
            Attention::Mla {
                kv_lora_rank,
                qk_rope_dim,
                ..
            } => (*kv_lora_rank + *qk_rope_dim) as f64,
        };
        per_layer * self.layers as f64 * self.kv_bytes / self.kv_share_layers.max(1) as f64
    }

    pub fn weight_bytes_total(&self) -> f64 {
        self.total_params() * self.weight_bytes
    }

    /// Load a ModelSpec from a HuggingFace config.json (llama-family and
    /// common MoE fields), with dtype byte-widths supplied by the caller.
    pub fn from_hf_config(name: &str, raw: &str, weight_bytes: f64, kv_bytes: f64) -> anyhow::Result<Self> {
        let v: serde_json::Value = serde_json::from_str(raw)?;
        let g = |k: &str| v.get(k).and_then(|x| x.as_u64()).map(|x| x as usize);
        let layers = g("num_hidden_layers").ok_or_else(|| anyhow::anyhow!("layers"))?;
        let hidden = g("hidden_size").ok_or_else(|| anyhow::anyhow!("hidden"))?;
        let heads = g("num_attention_heads").ok_or_else(|| anyhow::anyhow!("heads"))?;
        let kv_heads = g("num_key_value_heads").unwrap_or(heads);
        let head_dim = g("head_dim").unwrap_or(hidden / heads);
        let intermediate = g("intermediate_size").unwrap_or(4 * hidden);
        let vocab = g("vocab_size").ok_or_else(|| anyhow::anyhow!("vocab"))?;
        let tied = v.get("tie_word_embeddings").and_then(|x| x.as_bool()).unwrap_or(false);
        let attention = match g("kv_lora_rank") {
            Some(r) => Attention::Mla {
                kv_lora_rank: r,
                qk_rope_dim: g("qk_rope_head_dim").unwrap_or(64),
                q_lora_rank: g("q_lora_rank").unwrap_or(hidden / 4),
                qk_nope_head_dim: g("qk_nope_head_dim").unwrap_or(128),
                v_head_dim: g("v_head_dim").unwrap_or(128),
            },
            None => Attention::Gqa,
        };
        let ffn = match g("n_routed_experts").or_else(|| g("num_experts")).or_else(|| g("num_local_experts")) {
            Some(experts) => Ffn::Moe {
                experts,
                top_k: g("num_experts_per_tok").unwrap_or(8),
                shared_experts: g("n_shared_experts").unwrap_or(0),
                moe_intermediate: g("moe_intermediate_size").unwrap_or(intermediate),
                first_k_dense: g("first_k_dense_replace").unwrap_or(0),
                shared_intermediate: None,
            },
            None => Ffn::Dense,
        };
        let sparse_attention = g("index_topk").map(|k| SparseAttention { index_top_k: k });
        Ok(ModelSpec {
            mtp_accept: 0.0, // acceptance is a deployment choice, not a config fact
            expert_locality: 1.0,
            kv_share_layers: 1,
            prefill_top_k: None,
            name: name.into(),
            layers,
            hidden,
            heads,
            kv_heads,
            head_dim,
            intermediate,
            vocab,
            tied_embeddings: tied,
            attention,
            ffn,
            sparse_attention,
            weight_bytes,
            kv_bytes,
        })
    }
}

/// Kernel maturity on a given hardware backend. These are the calibrated
/// "software quality" multipliers — the difference between framework ops,
/// hand-fused kernels, and bespoke per-model kernels.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KernelSpec {
    pub name: String,
    /// Kernel launches per transformer layer at decode (framework ~25, fused ~5, bespoke ~2).
    /// GEMMs and attention account for ~6; the rest are elementwise/norm/rope ops
    /// that each cost roughly the dispatch floor.
    pub dispatches_per_layer: f64,
    /// Fixed launches per step outside layers (embed, head, sampling glue).
    pub dispatches_fixed: f64,
    /// GEMM efficiency at full occupancy (fraction of peak TFLOPS).
    pub gemm_peak_efficiency: f64,
    /// Output cells (M*N) at which GEMM efficiency reaches half its peak —
    /// models tile under-occupancy for small matrices. Calibrated from probe:
    /// candle-metal ~2e5; mature CUDA stacks much lower.
    pub gemm_occupancy_half_cells: f64,
    /// Fraction of peak memory bandwidth achieved by attention/KV reads.
    pub attn_bw_efficiency: f64,
    /// Extra bytes moved per parameter due to unfused elementwise chains
    /// (activations re-read/written between kernels). 0 = perfectly fused.
    pub unfused_activation_traffic: f64,
    /// Multiplier on modeled prefill chunk time for runtimes whose prefill
    /// path carries extra activation traffic (measured: candle-metal ~3x).
    #[serde(default = "one")]
    pub prefill_overhead_mult: f64,
    /// Grouped-GEMM MoE kernels (one launch for all experts). Without it,
    /// every expert pays the dispatch floor.
    #[serde(default)]
    pub grouped_moe: bool,
}

fn one() -> f64 {
    1.0
}

impl KernelSpec {
    /// Effective GEMM efficiency for an output of `cells` = M*N elements.
    pub fn gemm_eff(&self, cells: f64) -> f64 {
        self.gemm_peak_efficiency * cells / (cells + self.gemm_occupancy_half_cells)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HardwareSpec {
    pub name: String,
    /// Dense TFLOPS at the serving precision.
    pub tflops: f64,
    pub mem_bw_gbs: f64,
    pub mem_capacity_gb: f64,
    /// Per-kernel-launch overhead (dispatch + scheduling), microseconds.
    pub dispatch_us: f64,
    /// Host<->device round trip forced per step (sampling sync), microseconds.
    pub step_sync_us: f64,
    pub tdp_w: f64,
    pub unit_cost_usd: f64,
    /// Effective per-GPU collective bandwidth for TP/EP traffic, GB/s
    /// (NVLink allreduce effective, or scaled-down IB for cross-node EP).
    #[serde(default)]
    pub interconnect_gbs: Option<f64>,
    #[serde(default)]
    pub interconnect_latency_us: f64,
}

/// Parallelism layout. Perf accounting is per-GPU: `WorkloadSpec` batch terms
/// are per-GPU, throughput is tok/s/GPU, cost is $/GPU — so $/Mtok composes.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParallelSpec {
    pub tp: usize,
    /// Expert-parallel group size; the EP group shares a combined batch.
    pub ep: usize,
    /// Activation bytes on the wire (2.0 bf16, 1.0 fp8 comms).
    pub act_bytes: f64,
    /// Fraction of collective time hidden under compute (dual-microbatch
    /// pipelining etc.). DeepSeek-style decode ~0.75.
    #[serde(default)]
    pub comm_overlap: f64,
    /// Straggler multiplier on MoE layer time from expert load imbalance
    /// (step time = slowest EP rank; EPLB-managed production ~1.5-2.0).
    #[serde(default = "one_f")]
    pub ep_imbalance: f64,
}

fn one_f() -> f64 {
    1.0
}

impl Default for ParallelSpec {
    fn default() -> Self {
        Self { tp: 1, ep: 1, act_bytes: 2.0, comm_overlap: 0.0, ep_imbalance: 1.0 }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SamplingPlacement {
    Host { logits_copy: bool },
    Device,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServingSpec {
    pub name: String,
    pub max_batch: usize,
    pub prefill_chunk: usize,
    /// Host-side engine work per step (scheduling, bookkeeping, serialization),
    /// microseconds. Measured: vLLM 1000-7000, barge ~10-50.
    pub sched_overhead_us: f64,
    /// Runtime churn per live step not visible in static-shape microbenchmarks
    /// (buffer-pool misses on varying shapes, per-step uploads, KV compaction).
    /// CUDA-graph-style capture drives this toward 0; candle-metal ~10-15ms.
    #[serde(default)]
    pub step_overhead_us: f64,
    /// Per-token host work on the response path (detok, streaming).
    pub per_token_host_us: f64,
    pub sampling: SamplingPlacement,
    /// Fraction of prompt tokens served from prefix cache (skipped prefill).
    pub prefix_cache_hit: f64,
    /// Pack prefill fragments from many requests into one forward per step
    /// (SGLang-class engines: true; barge today: false).
    #[serde(default)]
    pub prefill_packing: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkloadSpec {
    pub name: String,
    pub num_requests: usize,
    pub input_len: usize,
    pub output_len: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostSpec {
    pub amortization_months: f64,
    /// Fleet utilization: fraction of wall-clock the hardware earns.
    pub utilization: f64,
    pub power_usd_per_kwh: f64,
    pub pue: f64,
    /// Non-GPU system overhead as a fraction of unit cost (host, network, chassis).
    pub system_overhead_frac: f64,
}

impl Default for CostSpec {
    fn default() -> Self {
        Self {
            amortization_months: 36.0,
            utilization: 0.7,
            power_usd_per_kwh: 0.09,
            pue: 1.25,
            system_overhead_frac: 0.25,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StackConfig {
    pub model: ModelSpec,
    pub hardware: HardwareSpec,
    pub kernel: KernelSpec,
    pub serving: ServingSpec,
    pub workload: WorkloadSpec,
    #[serde(default)]
    pub parallel: ParallelSpec,
    #[serde(default)]
    pub cost: CostSpec,
}

impl StackConfig {
    pub fn from_toml(s: &str) -> anyhow::Result<Self> {
        Ok(toml::from_str(s)?)
    }
    pub fn to_toml(&self) -> anyhow::Result<String> {
        Ok(toml::to_string_pretty(self)?)
    }
}
