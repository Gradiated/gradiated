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

/// A prefilling sequence parked in a dedicated top slot.
pub struct Prefilling {
    pub seq: Sequence,
    pub slot: usize,
}

pub struct PrefillChunk {
    /// Index into `prefilling`.
    pub idx: usize,
    pub slot: usize,
    pub start: usize,
    pub len: usize,
    /// True when this chunk completes the prompt — sample from its logits.
    pub completes: bool,
}

/// Throughput-first continuous batching.
///
/// Slot discipline: decoding sequences occupy slots [0, n_dec), always
/// compacted (swap-remove on completion) so decode-batch KV reads are pure
/// views. The top `prefill_slots` slots are a dedicated prefill region;
/// several prompts can prefill in one step under a shared token budget
/// (`prefill_chunk`), each as its own forward. On completion a sequence's KV
/// moves into the decode region — one copy, amortized per request.
///
/// No preemption, no priorities, no fairness: admission control guarantees an
/// admitted sequence never OOMs (prompt + max_tokens <= max_ctx), and FCFS
/// maximizes batch fullness, which is the only thing $/token cares about.
pub struct Scheduler {
    pub waiting: VecDeque<Sequence>,
    pub decoding: Vec<Sequence>,
    pub prefilling: Vec<Prefilling>,
    free_prefill_slots: Vec<usize>,
    /// Fixed size of the top prefill region; decode capacity is the rest.
    prefill_region: usize,
    pub max_slots: usize,
    pub max_ctx: usize,
    pub prefill_chunk: usize,
}

impl Scheduler {
    pub fn new(max_slots: usize, max_ctx: usize, prefill_chunk: usize, prefill_slots: usize) -> Self {
        let prefill_region = prefill_slots.clamp(1, max_slots / 2);
        Self {
            waiting: VecDeque::new(),
            decoding: vec![],
            prefilling: vec![],
            free_prefill_slots: (max_slots - prefill_region..max_slots).collect(),
            prefill_region,
            max_slots,
            max_ctx,
            prefill_chunk,
        }
    }

    pub fn decode_capacity(&self) -> usize {
        self.max_slots - self.prefill_region
    }

    pub fn submit(&mut self, seq: Sequence) -> Result<(), Sequence> {
        if seq.prompt.len() + seq.params.max_tokens > self.max_ctx {
            return Err(seq); // over context budget: reject at the door
        }
        self.waiting.push_back(seq);
        Ok(())
    }

    pub fn has_work(&self) -> bool {
        !self.waiting.is_empty() || !self.decoding.is_empty() || !self.prefilling.is_empty()
    }

    /// Admit waiting sequences into free prefill slots, bounded by the step's
    /// prefill token budget (so admissions don't starve ongoing prefills) and
    /// by decode capacity (an admitted sequence must have a decode slot when
    /// its prefill completes).
    pub fn admit(&mut self) {
        let mut backlog: usize = self
            .prefilling
            .iter()
            .map(|p| p.seq.prompt.len() - p.seq.computed)
            .sum();
        while !self.free_prefill_slots.is_empty()
            && !self.waiting.is_empty()
            && backlog < self.prefill_chunk
            && self.decoding.len() + self.prefilling.len() < self.decode_capacity()
        {
            let seq = self.waiting.pop_front().unwrap();
            backlog += seq.prompt.len();
            let slot = self.free_prefill_slots.pop().unwrap();
            self.prefilling.push(Prefilling { seq, slot });
        }
    }

    /// Plan this step's prefill chunks, FCFS under the shared token budget.
    pub fn prefill_plans(&self) -> Vec<PrefillChunk> {
        let mut budget = self.prefill_chunk;
        let mut plans = vec![];
        for (idx, p) in self.prefilling.iter().enumerate() {
            if budget == 0 {
                break;
            }
            let remaining = p.seq.prompt.len() - p.seq.computed;
            let take = remaining.min(budget);
            budget -= take;
            plans.push(PrefillChunk {
                idx,
                slot: p.slot,
                start: p.seq.computed,
                len: take,
                completes: take == remaining,
            });
        }
        plans
    }

    pub fn release_prefill_slot(&mut self, slot: usize) {
        self.free_prefill_slots.push(slot);
    }
}
