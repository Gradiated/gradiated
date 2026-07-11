use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};
use rayon::prelude::*;

/// Minimal sampling surface: the cheap 99% of what OS-model hosting needs.
/// No beams, no logprobs, no penalties — each cut is a measured cost decision.
#[derive(Debug, Clone)]
pub struct SamplingParams {
    pub temperature: f32,
    pub top_p: f32,
    pub top_k: usize,
    pub max_tokens: usize,
    pub seed: u64,
    pub ignore_eos: bool,
    pub stop: Vec<String>,
}

impl Default for SamplingParams {
    fn default() -> Self {
        Self {
            temperature: 1.0,
            top_p: 1.0,
            top_k: 0,
            max_tokens: 256,
            seed: 0,
            ignore_eos: false,
            stop: vec![],
        }
    }
}

pub struct SamplerState {
    rng: StdRng,
}

impl SamplerState {
    pub fn new(seed: u64) -> Self {
        Self {
            rng: StdRng::seed_from_u64(seed),
        }
    }
}

/// Sample one token per row from `logits` [b, vocab] (f32, host memory).
/// Runs on CPU: on unified memory the logits copy is cheap, and CPU sampling
/// keeps every sampling feature off the accelerator's critical path.
pub fn sample_batch(
    logits: &[f32],
    vocab: usize,
    params: &[&SamplingParams],
    states: &mut [&mut SamplerState],
) -> Vec<u32> {
    let rows: Vec<(usize, &[f32])> = logits.chunks_exact(vocab).enumerate().collect();
    rows.into_par_iter()
        .zip(params.par_iter())
        .map(|((i, row), p)| {
            // rand's StdRng is not Sync-shareable across the pool; derive a
            // per-step value deterministically instead.
            let _ = i;
            sample_row(row, p, None)
        })
        .collect::<Vec<_>>()
        .into_iter()
        .zip(states.iter_mut())
        .zip(params.iter())
        .map(|((greedy_or_needs_rng, st), _p)| match greedy_or_needs_rng {
            RowResult::Token(t) => t,
            RowResult::Dist(items) => {
                let r: f32 = st.rng.random();
                pick(&items, r)
            }
        })
        .collect()
}

enum RowResult {
    Token(u32),
    /// (token, cumulative probability) pairs after top-k/top-p filtering.
    Dist(Vec<(u32, f32)>),
}

fn sample_row(row: &[f32], p: &SamplingParams, _rng: Option<&mut StdRng>) -> RowResult {
    if p.temperature <= 0.0 {
        let mut best = 0usize;
        let mut bv = f32::NEG_INFINITY;
        for (i, &v) in row.iter().enumerate() {
            if v > bv {
                bv = v;
                best = i;
            }
        }
        return RowResult::Token(best as u32);
    }
    // Softmax with temperature over a top-k prefilter (cap work at 512).
    let k = if p.top_k == 0 { 512 } else { p.top_k.min(512) };
    let mut idx: Vec<u32> = (0..row.len() as u32).collect();
    let kth = k.min(row.len());
    idx.select_nth_unstable_by(kth - 1, |&a, &b| {
        row[b as usize].total_cmp(&row[a as usize])
    });
    idx.truncate(kth);
    idx.sort_unstable_by(|&a, &b| row[b as usize].total_cmp(&row[a as usize]));
    let maxv = row[idx[0] as usize];
    let mut probs: Vec<f32> = idx
        .iter()
        .map(|&i| ((row[i as usize] - maxv) / p.temperature).exp())
        .collect();
    let sum: f32 = probs.iter().sum();
    for q in probs.iter_mut() {
        *q /= sum;
    }
    // top-p cut, then cumulative distribution.
    let mut cum = 0f32;
    let mut items = Vec::with_capacity(probs.len());
    for (i, &q) in idx.iter().zip(probs.iter()) {
        cum += q;
        items.push((*i, cum));
        if cum >= p.top_p {
            break;
        }
    }
    RowResult::Dist(items)
}

fn pick(items: &[(u32, f32)], r: f32) -> u32 {
    let total = items.last().map(|x| x.1).unwrap_or(1.0);
    let target = r * total;
    for &(tok, c) in items {
        if target <= c {
            return tok;
        }
    }
    items.last().map(|x| x.0).unwrap_or(0)
}
