//! Byte-exact per-op trace of one engine step: where every byte moves and
//! every FLOP burns, and which resource binds each op on the given hardware.
//! Mirrors the formulas in lib.rs (a unit test asserts the totals agree).

use crate::gemm_bound;
use sartor_spec::*;
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct TraceRow {
    pub op: String,
    /// Instances per step (usually layer count).
    pub count: f64,
    pub flops: f64,
    pub weight_bytes: f64,
    pub kv_bytes: f64,
    pub time_us: f64,
    pub bound: &'static str,
    pub pct: f64,
}

pub struct Trace {
    pub rows: Vec<TraceRow>,
    pub step_us: f64,
    pub tokens_per_step: f64,
}

fn row(
    op: &str,
    count: f64,
    flops: f64,
    wb: f64,
    kvb: f64,
    time_s: f64,
    bound: &'static str,
) -> TraceRow {
    TraceRow {
        op: op.into(),
        count,
        flops: flops * count,
        weight_bytes: wb * count,
        kv_bytes: kvb * count,
        time_us: time_s * count * 1e6,
        bound,
        pct: 0.0,
    }
}

/// GEMM row: per-instance sizes, time = max(floor, math, stream).
fn gemm_row(
    op: &str,
    count: f64,
    hw: &HardwareSpec,
    k: &KernelSpec,
    m_rows: f64,
    n_cols: f64,
    k_inner: f64,
    wbytes: f64,
    grouped: bool,
) -> TraceRow {
    let (t, bound) = gemm_bound(hw, k, m_rows, n_cols, k_inner, wbytes, grouped);
    row(
        op,
        count,
        2.0 * m_rows * n_cols * k_inner,
        n_cols * k_inner * wbytes,
        0.0,
        t,
        bound,
    )
}

pub fn trace_decode(cfg: &StackConfig, b: usize, ctx: f64) -> Trace {
    let (m, hw, k, s) = (&cfg.model, &cfg.hardware, &cfg.kernel, &cfg.serving);
    let p = &cfg.parallel;
    let (bf, d) = (b as f64, m.hidden as f64);
    let (tp, ep) = (p.tp.max(1) as f64, p.ep.max(1));
    let floor = hw.dispatch_us * 1e-6;
    let nl = m.layers as f64;
    let eff_ctx = match &m.sparse_attention {
        Some(sa) => ctx.min(sa.index_top_k as f64),
        None => ctx,
    };
    let mut rows: Vec<TraceRow> = vec![];

    match &m.attention {
        Attention::Gqa => {
            let qkv_cols = ((m.heads + 2 * m.kv_heads) * m.head_dim) as f64 / tp;
            rows.push(gemm_row("attn.qkv_proj", nl, hw, k, bf, qkv_cols, d, m.weight_bytes, false));
            rows.push(gemm_row(
                "attn.o_proj",
                nl,
                hw,
                k,
                bf,
                d,
                (m.heads * m.head_dim) as f64 / tp,
                m.weight_bytes,
                false,
            ));
        }
        Attention::Mla {
            kv_lora_rank,
            qk_rope_dim,
            q_lora_rank,
            qk_nope_head_dim,
            v_head_dim,
        } => {
            let h = m.heads as f64 / tp;
            let (r_kv, r_q) = (*kv_lora_rank as f64, *q_lora_rank as f64);
            let (nope, rope, vh) = (*qk_nope_head_dim as f64, *qk_rope_dim as f64, *v_head_dim as f64);
            rows.push(gemm_row("mla.q_down", nl, hw, k, bf, r_q, d, m.weight_bytes, false));
            rows.push(gemm_row("mla.q_up", nl, hw, k, bf, h * (nope + rope), r_q, m.weight_bytes, false));
            rows.push(gemm_row("mla.kv_down", nl, hw, k, bf, r_kv + rope, d, m.weight_bytes, false));
            rows.push(gemm_row("mla.absorb_qk", nl, hw, k, bf * h, r_kv, nope, m.weight_bytes, false));
            rows.push(gemm_row("mla.absorb_v", nl, hw, k, bf * h, vh, r_kv, m.weight_bytes, false));
            rows.push(gemm_row("mla.o_proj", nl, hw, k, bf, d, h * vh, m.weight_bytes, false));
        }
    }

    // Attention core: latent/KV reads vs score math.
    let kv_bytes_layer = bf * eff_ctx * m.kv_bytes_per_token() / nl;
    let attn_read_s = kv_bytes_layer / (hw.mem_bw_gbs * 1e9 * k.attn_bw_efficiency);
    let score_flops = match &m.attention {
        Attention::Gqa => 4.0 * bf * (m.heads * m.head_dim) as f64,
        Attention::Mla {
            kv_lora_rank,
            qk_rope_dim,
            ..
        } => {
            let h = m.heads as f64 / tp;
            2.0 * bf * h * (*kv_lora_rank + *qk_rope_dim) as f64 + 2.0 * bf * h * *kv_lora_rank as f64
        }
    } * eff_ctx;
    let attn_math_s = score_flops / (hw.tflops * 1e12 * k.gemm_peak_efficiency);
    let t_attn = (2.0 * floor).max(attn_read_s).max(attn_math_s);
    rows.push(row(
        "attn.core(score+value)",
        nl,
        score_flops,
        0.0,
        kv_bytes_layer,
        t_attn,
        if attn_read_s >= attn_math_s && attn_read_s > 2.0 * floor {
            "kv-read"
        } else if attn_math_s > 2.0 * floor {
            "math"
        } else {
            "dispatch"
        },
    ));

    // FFN.
    match &m.ffn {
        Ffn::Dense => {
            let w = m.intermediate as f64 / tp;
            rows.push(gemm_row("ffn.gate_up", nl, hw, k, bf, 2.0 * w, d, m.weight_bytes, false));
            rows.push(gemm_row("ffn.down", nl, hw, k, bf, d, w, m.weight_bytes, false));
        }
        Ffn::Moe {
            experts,
            top_k,
            shared_experts,
            moe_intermediate,
            first_k_dense,
            shared_intermediate,
        } => {
            let moe_l = (m.layers - first_k_dense) as f64;
            let dense_l = *first_k_dense as f64;
            let group_batch = b * ep;
            let active = (crate::expected_active_experts(*experts, *top_k, group_batch) / ep as f64).max(1e-9);
            let pairs = bf * *top_k as f64;
            let w = *moe_intermediate as f64;
            let imb = p.ep_imbalance;
            let mut gu = gemm_row(
                "moe.experts.gate_up (grouped)",
                moe_l * active,
                hw,
                k,
                pairs / active,
                2.0 * w,
                d,
                m.weight_bytes,
                k.grouped_moe,
            );
            gu.time_us *= imb;
            rows.push(gu);
            let mut dn = gemm_row(
                "moe.experts.down (grouped)",
                moe_l * active,
                hw,
                k,
                pairs / active,
                d,
                w,
                m.weight_bytes,
                k.grouped_moe,
            );
            dn.time_us *= imb;
            rows.push(dn);
            if *shared_experts > 0 {
                let ws = *shared_experts as f64
                    * shared_intermediate.unwrap_or(*moe_intermediate) as f64;
                rows.push(gemm_row("moe.shared.gate_up", moe_l, hw, k, bf, 2.0 * ws, d, m.weight_bytes, false));
                rows.push(gemm_row("moe.shared.down", moe_l, hw, k, bf, d, ws, m.weight_bytes, false));
            }
            rows.push(row("moe.router+dispatch", moe_l, 0.0, 0.0, 0.0, imb * 2.0 * floor, "dispatch"));
            if dense_l > 0.0 {
                let wd = m.intermediate as f64 / tp;
                rows.push(gemm_row("ffn.dense.gate_up", dense_l, hw, k, bf, 2.0 * wd, d, m.weight_bytes, false));
                rows.push(gemm_row("ffn.dense.down", dense_l, hw, k, bf, d, wd, m.weight_bytes, false));
            }
        }
    }

    // Small unfused ops.
    let small_ops = (k.dispatches_per_layer - 6.0).max(0.0);
    let act_bytes = bf * d * 4.0 * 2.0;
    let t_small = floor.max(act_bytes / (hw.mem_bw_gbs * 1e9)) * (1.0 + k.unfused_activation_traffic);
    rows.push(row("elementwise/norm/rope", nl * small_ops, 0.0, 0.0, 0.0, t_small, "dispatch"));

    // Communication.
    let ic = hw.interconnect_gbs.unwrap_or(f64::INFINITY) * 1e9;
    let lat = hw.interconnect_latency_us * 1e-6;
    let expose = 1.0 - p.comm_overlap.clamp(0.0, 1.0);
    if p.tp > 1 {
        let t = expose * 2.0 * (bf * d * p.act_bytes * 2.0 * (tp - 1.0) / tp / ic + lat);
        rows.push(row("comm.tp_allreduce", nl, 0.0, 0.0, 0.0, t, "interconnect"));
    }
    if ep > 1 {
        if let Ffn::Moe { top_k, first_k_dense, .. } = &m.ffn {
            let cross = m.expert_locality * (ep as f64 - 1.0) / ep as f64;
            let t = p.ep_imbalance
                * expose
                * 2.0
                * (bf * *top_k as f64 * d * p.act_bytes * cross / ic + lat);
            rows.push(row(
                "comm.ep_all2all",
                (m.layers - first_k_dense) as f64,
                0.0,
                0.0,
                0.0,
                t,
                "interconnect",
            ));
        }
    }

    // Head + fixed + host.
    rows.push(gemm_row("lm_head", 1.0, hw, k, bf, m.vocab as f64 / tp, d, m.weight_bytes, false));
    rows.push(row("fixed dispatches", 1.0, 0.0, 0.0, 0.0, k.dispatches_fixed * floor, "dispatch"));
    let sync_s = hw.step_sync_us * 1e-6
        + match s.sampling {
            SamplingPlacement::Host { logits_copy: true } => (b * m.vocab) as f64 * 4.0 / (hw.mem_bw_gbs * 1e9),
            _ => 0.0,
        };
    rows.push(row("host.sync+logits", 1.0, 0.0, 0.0, 0.0, sync_s, "sync"));
    rows.push(row(
        "host.sched+stream",
        1.0,
        0.0,
        0.0,
        0.0,
        (s.sched_overhead_us + s.step_overhead_us) * 1e-6 + bf * s.per_token_host_us * 1e-6,
        "host",
    ));

    let step_us: f64 = rows.iter().map(|r| r.time_us).sum();
    for r in rows.iter_mut() {
        r.pct = r.time_us / step_us * 100.0;
    }
    rows.sort_by(|a, b| b.time_us.partial_cmp(&a.time_us).unwrap());
    Trace {
        rows,
        step_us,
        tokens_per_step: bf * (1.0 + m.mtp_accept),
    }
}
