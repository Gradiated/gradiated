use crate::sample::{SamplerState, SamplingParams};
use std::collections::VecDeque;
use tokio::sync::mpsc::UnboundedSender;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FinishReason {
    Stop,
    Length,
}

/// What the engine emits per sequence. Token ids only — detokenization happens
/// at the edge (server/bench), and only when someone actually needs text.
#[derive(Debug)]
pub enum Out {
    Token(u32),
    Done { finish: FinishReason },
}

pub struct Sequence {
    pub prompt: Vec<u32>,
    pub out: Vec<u32>,
    /// Number of tokens whose KV is written.
    pub computed: usize,
    pub params: SamplingParams,
    pub sampler: SamplerState,
    pub tx: UnboundedSender<Out>,
}

impl Sequence {
    pub fn new(prompt: Vec<u32>, params: SamplingParams, tx: UnboundedSender<Out>) -> Self {
        let sampler = SamplerState::new(params.seed);
        Self {
            prompt,
            out: vec![],
            computed: 0,
            params,
            sampler,
            tx,
        }
    }

    /// Next token to feed at decode time (the newest sampled token, or the
    /// last prompt token right after prefill).
    pub fn next_input(&self) -> u32 {
        let idx = self.computed;
        if idx < self.prompt.len() {
            self.prompt[idx]
        } else {
            self.out[idx - self.prompt.len()]
        }
    }
}

pub struct PrefillChunk {
    /// KV slot the prefilling sequence occupies (always the top slot).
    pub slot: usize,
    pub start: usize,
    pub tokens: Vec<u32>,
    /// True when this chunk completes the prompt — sample from its logits.
    pub completes: bool,
}

/// Throughput-first continuous batching.
///
/// Slot discipline: decoding sequences occupy slots [0, n_dec) — always
/// compacted, so decode-batch KV reads are pure views. At most one sequence
/// prefills at a time (a chunk of `prefill_chunk` tokens per step saturates
/// compute by itself), parked in the top slot; on completion its KV moves
/// into the decode region (one copy, amortized per request).
///
/// No preemption, no priorities, no fairness: admission control guarantees a
/// sequence admitted never OOMs (prompt + max_tokens <= max_ctx budget), and
/// FCFS maximizes batch fullness, which is the only thing $/token cares about.
pub struct Scheduler {
    pub waiting: VecDeque<Sequence>,
    pub decoding: Vec<Sequence>,
    pub prefilling: Option<Sequence>,
    pub max_slots: usize,
    pub max_ctx: usize,
    pub prefill_chunk: usize,
}

impl Scheduler {
    pub fn new(max_slots: usize, max_ctx: usize, prefill_chunk: usize) -> Self {
        Self {
            waiting: VecDeque::new(),
            decoding: vec![],
            prefilling: None,
            max_slots,
            max_ctx,
            prefill_chunk,
        }
    }

    pub fn top_slot(&self) -> usize {
        self.max_slots - 1
    }

    pub fn submit(&mut self, seq: Sequence) -> Result<(), Sequence> {
        if seq.prompt.len() + seq.params.max_tokens > self.max_ctx {
            return Err(seq); // over context budget: reject at the door
        }
        self.waiting.push_back(seq);
        Ok(())
    }

    pub fn has_work(&self) -> bool {
        !self.waiting.is_empty() || !self.decoding.is_empty() || self.prefilling.is_some()
    }

    /// Admit the next waiting sequence into the prefill slot if it's free.
    pub fn admit(&mut self) {
        if self.prefilling.is_none() && self.decoding.len() + 1 < self.max_slots {
            if let Some(seq) = self.waiting.pop_front() {
                self.prefilling = Some(seq);
            }
        }
    }

    /// The next prefill chunk to run this step, if any.
    pub fn prefill_plan(&self) -> Option<PrefillChunk> {
        let seq = self.prefilling.as_ref()?;
        let remaining = seq.prompt.len() - seq.computed;
        let take = remaining.min(self.prefill_chunk);
        let tokens = seq.prompt[seq.computed..seq.computed + take].to_vec();
        Some(PrefillChunk {
            slot: self.top_slot(),
            start: seq.computed,
            tokens,
            completes: take == remaining,
        })
    }
}
