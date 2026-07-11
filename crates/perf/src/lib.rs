//! Performance model: analytical roofline per engine step + a closed-loop
//! workload simulation that mirrors a continuous-batching engine (admission
//! by prefill budget, decode over all active, completion churn).
//!
//! Fidelity contract: every term here corresponds to a measured quantity
//! (barge probe/bench on M4, public anchors for datacenter parts). Where the
//! model must guess, it guesses conservatively and says so in comments.

use sartor_spec::*;
use serde::Serialize;

#[derive(Debug, Clone, Serialize, Default)]
pub struct Breakdown {
    pub compute_s: f64,
    pub memory_s: f64,
    pub dispatch_s: f64,
    pub sync_s: f64,
    pub sched_s: f64,
    pub prefill_s: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct PerfReport {
    pub wall_s: f64,
    pub steps: u64,
    pub avg_decode_batch: f64,
    pub output_tok_per_s: f64,
    pub total_tok_per_s: f64,
    pub energy_j: f64,
    pub breakdown: Breakdown,
    /// Fraction of wall time the accelerator does useful math or moves data.
    pub device_busy_frac: f64,
}

/// Expected distinct MoE experts hit by a batch of B tokens choosing top_k of E.
fn expected_active_experts(experts: usize, top_k: usize, batch: usize) -> f64 {
    let e = experts as f64;
    let draws = (batch * top_k) as f64;
    e * (1.0 - (1.0 - 1.0 / e).powf(draws))
}

/// Weight bytes that must be read for one decode step at batch B.
fn step_weight_bytes(m: &ModelSpec, batch: usize) -> f64 {
    let d = m.hidden as f64;
    let attn = m.layers as f64 * {
        let qo = 2.0 * d * (m.heads * m.head_dim) as f64;
        let kv = 2.0 * d * (m.kv_heads * m.head_dim) as f64;
        qo + kv
    };
    let head = (m.vocab * m.hidden) as f64;
    let ffn = match &m.ffn {
        Ffn::Dense => m.layers as f64 * 3.0 * d * m.intermediate as f64,
        Ffn::Moe {
            experts,
            top_k,
            shared_experts,
            moe_intermediate,
            first_k_dense,
        } => {
            let dense = *first_k_dense as f64 * 3.0 * d * m.intermediate as f64;
            let moe_layers = (m.layers - first_k_dense) as f64;
            let active = expected_active_experts(*experts, *top_k, batch) + *shared_experts as f64;
            dense + moe_layers * active * 3.0 * d * *moe_intermediate as f64
        }
    };
    (attn + head + ffn) * m.weight_bytes
}

/// Time for one GEMM producing m_rows x n_cols from k_inner, weights streamed
/// from memory: max(dispatch floor, math at occupancy-adjusted efficiency,
/// weight-streaming time).
fn gemm_s(hw: &HardwareSpec, k: &KernelSpec, m_rows: f64, n_cols: f64, k_inner: f64, wbytes: f64) -> f64 {
    let flops = 2.0 * m_rows * n_cols * k_inner;
    let eff = k.gemm_eff(m_rows * n_cols).max(1e-3);
    let math = flops / (hw.tflops * 1e12 * eff);
    let stream = n_cols * k_inner * wbytes / (hw.mem_bw_gbs * 1e9);
    (hw.dispatch_us * 1e-6).max(math).max(stream)
}

/// One decode step: batch `b` sequences at average context `ctx`.
/// Per-op roofline: each kernel costs max(dispatch floor, its own math time,
/// its own memory time) — small ops are pure dispatch, the LM head is compute,
/// big-model FFNs are weight streaming.
pub fn decode_step_s(cfg: &StackConfig, b: usize, ctx: f64, bk: &mut Breakdown) -> f64 {
    let (m, hw, k, s) = (&cfg.model, &cfg.hardware, &cfg.kernel, &cfg.serving);
    let bf = b as f64;
    let d = m.hidden as f64;
    let floor = hw.dispatch_us * 1e-6;
    let eff_ctx = match &m.sparse_attention {
        Some(sa) => ctx.min(sa.index_top_k as f64),
        None => ctx,
    };

    let p = &cfg.parallel;
    let (tp, ep) = (p.tp.max(1) as f64, p.ep.max(1));
    // Attention projections per layer, column/row-sharded across TP ranks.
    let qkv_cols = ((m.heads + 2 * m.kv_heads) * m.head_dim) as f64 / tp;
    let t_qkv = gemm_s(hw, k, bf, qkv_cols, d, m.weight_bytes);
    let t_o = gemm_s(hw, k, bf, d, (m.heads * m.head_dim) as f64 / tp, m.weight_bytes);
    // FFN per layer: dense width (TP-sharded) or this GPU's share of the
    // experts activated by the EP group's combined batch.
    let (ffn_width, moe_layers, dense_layers) = match &m.ffn {
        Ffn::Dense => (m.intermediate as f64 / tp, 0.0, m.layers as f64),
        Ffn::Moe {
            experts,
            top_k,
            shared_experts,
            moe_intermediate,
            first_k_dense,
        } => {
            let group_batch = b * ep;
            let active = expected_active_experts(*experts, *top_k, group_batch) / ep as f64
                + *shared_experts as f64;
            (
                active * *moe_intermediate as f64,
                (m.layers - first_k_dense) as f64,
                *first_k_dense as f64,
            )
        }
    };
    let dense_width = m.intermediate as f64 / tp;
    let ffn_layer = |w: f64| {
        gemm_s(hw, k, bf, 2.0 * w, d, m.weight_bytes) + gemm_s(hw, k, bf, d, w, m.weight_bytes)
    };
    // Communication per layer (does not overlap in v1 — conservative).
    let ic = hw.interconnect_gbs.unwrap_or(f64::INFINITY) * 1e9;
    let lat = hw.interconnect_latency_us * 1e-6;
    let t_tp_comm = if p.tp > 1 {
        2.0 * (bf * d * p.act_bytes * 2.0 * (tp - 1.0) / tp / ic + lat)
    } else {
        0.0
    };
    let t_ep_comm = |top_k: f64| {
        if ep > 1 {
            2.0 * (bf * top_k * d * p.act_bytes * (ep as f64 - 1.0) / ep as f64 / ic + lat)
        } else {
            0.0
        }
    };
    // KV read for attention (the per-sequence term paging/kernels fight over).
    let kv_bytes_layer = bf * eff_ctx * m.kv_bytes_per_token() / m.layers as f64;
    let t_attn = 2.0 * floor.max(kv_bytes_layer / (hw.mem_bw_gbs * 1e9 * k.attn_bw_efficiency) / 2.0);
    // Elementwise/norm/rope ops: pure dispatch floor, plus their activation traffic.
    let small_ops = (k.dispatches_per_layer - 6.0).max(0.0);
    let act_bytes = bf * d * 4.0 * 2.0; // one read+write per elementwise op, f32-equivalent
    let t_small = small_ops * floor.max(act_bytes / (hw.mem_bw_gbs * 1e9))
        * (1.0 + k.unfused_activation_traffic);

    let moe_topk = match &m.ffn {
        Ffn::Moe { top_k, .. } => *top_k as f64,
        Ffn::Dense => 0.0,
    };
    let per_moe_layer =
        t_qkv + t_o + ffn_layer(ffn_width) + t_attn + t_small + t_tp_comm + t_ep_comm(moe_topk);
    let per_dense_layer = t_qkv + t_o + ffn_layer(dense_width) + t_attn + t_small + t_tp_comm;
    let t_head = gemm_s(hw, k, bf, m.vocab as f64 / tp, d, m.weight_bytes);
    let t_fixed = k.dispatches_fixed * floor;

    let device = moe_layers * per_moe_layer + dense_layers * per_dense_layer + t_head + t_fixed;

    let sync_s = hw.step_sync_us * 1e-6
        + match s.sampling {
            SamplingPlacement::Host { logits_copy: true } => {
                bf * m.vocab as f64 * 4.0 / (hw.mem_bw_gbs * 1e9)
            }
            _ => 0.0,
        };
    let sched_s = s.sched_overhead_us * 1e-6 + bf * s.per_token_host_us * 1e-6;

    // Attribution for the report: compute vs memory character of the step.
    let weights = step_weight_bytes(m, b);
    bk.memory_s += (weights + bf * eff_ctx * m.kv_bytes_per_token()) / (hw.mem_bw_gbs * 1e9);
    bk.compute_s += 2.0 * m.active_params() * bf / (hw.tflops * 1e12);
    bk.dispatch_s += (m.layers as f64 * k.dispatches_per_layer + k.dispatches_fixed) * floor;
    bk.sync_s += sync_s;
    bk.sched_s += sched_s;
    device + sync_s + sched_s
}

/// Prefill `t` tokens (one chunk of one sequence) with existing context `past`.
pub fn prefill_s(cfg: &StackConfig, t: usize, past: f64, bk: &mut Breakdown) -> f64 {
    let (m, hw, k) = (&cfg.model, &cfg.hardware, &cfg.kernel);
    let tf = t as f64;
    let d = m.hidden as f64;
    let floor = hw.dispatch_us * 1e-6;
    let eff_past = match &m.sparse_attention {
        Some(sa) => past.min(sa.index_top_k as f64),
        None => past,
    };
    // Same per-op model with m_rows = t; attention has the quadratic term.
    let qkv_cols = ((m.heads + 2 * m.kv_heads) * m.head_dim) as f64;
    let t_qkv = gemm_s(hw, k, tf, qkv_cols, d, m.weight_bytes);
    let t_o = gemm_s(hw, k, tf, d, (m.heads * m.head_dim) as f64, m.weight_bytes);
    let ffn_width = match &m.ffn {
        Ffn::Dense => m.intermediate as f64,
        Ffn::Moe {
            experts,
            top_k,
            shared_experts,
            moe_intermediate,
            ..
        } => (expected_active_experts(*experts, *top_k, t) + *shared_experts as f64)
            * *moe_intermediate as f64,
    };
    let t_ffn = gemm_s(hw, k, tf, 2.0 * ffn_width, d, m.weight_bytes)
        + gemm_s(hw, k, tf, d, ffn_width, m.weight_bytes);
    let attn_flops = 4.0 * tf * (eff_past + tf / 2.0) * (m.heads * m.head_dim) as f64;
    let t_attn = (2.0 * floor).max(attn_flops / (hw.tflops * 1e12 * k.gemm_eff(tf * (eff_past + tf))));
    let small_ops = (k.dispatches_per_layer - 6.0).max(0.0);
    let act_bytes = tf * d * 4.0 * 2.0;
    let t_small = small_ops * floor.max(act_bytes / (hw.mem_bw_gbs * 1e9))
        * (1.0 + k.unfused_activation_traffic);
    let device = m.layers as f64 * (t_qkv + t_o + t_ffn + t_attn + t_small)
        + k.dispatches_fixed * floor;
    bk.prefill_s += device;
    device
}

/// Closed-loop simulation of the whole workload through a continuous-batching
/// engine (mirrors barge's scheduler; vLLM-style stacks differ only via
/// ServingSpec/KernelSpec parameters).
pub fn simulate(cfg: &StackConfig) -> PerfReport {
    let w = &cfg.workload;
    let s = &cfg.serving;
    let effective_input =
        ((w.input_len as f64) * (1.0 - s.prefix_cache_hit)).max(1.0).round() as usize;

    let mut waiting = w.num_requests;
    let mut prefilling: Vec<usize> = vec![]; // remaining prompt tokens per admitted seq
    let mut decoding: Vec<(f64, f64)> = vec![]; // (remaining output tokens, ctx so far)
    let mut wall = 0.0f64;
    let mut steps = 0u64;
    let mut batch_sum = 0u64;
    let mut out_tokens = 0.0f64;
    let mut bk = Breakdown::default();
    // MTP: expected tokens accepted per sequence per decode step.
    let tps = 1.0 + cfg.model.mtp_accept;

    while waiting > 0 || !prefilling.is_empty() || !decoding.is_empty() {
        // Admission under prefill budget, bounded by batch capacity.
        let mut backlog: usize = prefilling.iter().sum();
        while waiting > 0
            && backlog < s.prefill_chunk
            && decoding.len() + prefilling.len() < s.max_batch
        {
            prefilling.push(effective_input);
            backlog += effective_input;
            waiting -= 1;
        }
        // Decode pass over all active sequences.
        let b = decoding.len();
        if b > 0 {
            let avg_ctx: f64 = decoding.iter().map(|(_, c)| *c).sum::<f64>() / b as f64;
            wall += decode_step_s(cfg, b, avg_ctx, &mut bk);
            batch_sum += b as u64;
            for d in decoding.iter_mut() {
                let take = tps.min(d.0);
                out_tokens += take;
                d.0 -= take;
                d.1 += take;
            }
            decoding.retain(|(rem, _)| *rem > 0.0);
        }
        // Prefill chunks under shared budget (each its own forward pass).
        let mut budget = s.prefill_chunk;
        let mut i = 0;
        while i < prefilling.len() && budget > 0 {
            let take = prefilling[i].min(budget);
            let past = (effective_input - prefilling[i]) as f64;
            wall += prefill_s(cfg, take, past, &mut bk);
            prefilling[i] -= take;
            budget -= take;
            if prefilling[i] == 0 {
                // completes: first output token sampled from prefill logits
                prefilling.remove(i);
                out_tokens += 1.0;
                if w.output_len > 1 {
                    decoding.push(((w.output_len - 1) as f64, w.input_len as f64 + 1.0));
                }
            } else {
                i += 1;
            }
        }
        // Idle-step guard (nothing running): shouldn't happen, but don't loop.
        if b == 0 && prefilling.is_empty() && waiting == 0 && decoding.is_empty() {
            break;
        }
        steps += 1;
        if steps > 50_000_000 {
            break;
        }
    }

    let total_prompt = (w.num_requests * w.input_len) as f64;
    let device_busy = bk.compute_s.max(bk.memory_s) + bk.prefill_s;
    PerfReport {
        wall_s: wall,
        steps,
        avg_decode_batch: batch_sum as f64 / steps.max(1) as f64,
        output_tok_per_s: out_tokens / wall,
        total_tok_per_s: (total_prompt + out_tokens) / wall,
        energy_j: cfg.hardware.tdp_w * wall * (0.35 + 0.65 * (device_busy / wall).min(1.0)),
        breakdown: bk,
        device_busy_frac: (device_busy / wall).min(1.0),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn moe_expert_coverage_saturates() {
        assert!(expected_active_experts(128, 8, 1) - 8.0 < 1e-6);
        assert!(expected_active_experts(128, 8, 256) > 120.0);
    }
}
