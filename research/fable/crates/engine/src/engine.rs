use crate::config::EngineConfig;
use crate::kv::KvCache;
use crate::model::Model;
use crate::sample::sample_batch;
use crate::sched::{FinishReason, Out, Scheduler, Sequence};
use anyhow::Result;
use std::sync::mpsc::Receiver;
use std::time::Instant;

#[derive(Debug, Default, Clone)]
pub struct EngineStats {
    pub steps: u64,
    pub decode_tokens: u64,
    pub prefill_tokens: u64,
    pub decode_batch_sum: u64,
    pub busy_secs: f64,
}

pub struct Request {
    pub prompt: Vec<u32>,
    pub params: crate::sample::SamplingParams,
    pub tx: tokio::sync::mpsc::UnboundedSender<Out>,
}

/// Single-threaded engine loop owning the model + KV cache. No IPC, no
/// serialization, no inter-process anything: a request travels
/// channel -> schedule -> forward -> sample -> channel.
pub struct Engine {
    model: Model,
    kv: KvCache,
    sched: Scheduler,
    eos: Vec<u32>,
    pub stats: EngineStats,
}

impl Engine {
    pub fn new(model: Model, ecfg: &EngineConfig) -> Result<Self> {
        let kv = KvCache::new(
            model.cfg.num_hidden_layers,
            ecfg.max_slots,
            ecfg.max_ctx,
            model.cfg.num_key_value_heads,
            model.cfg.head_dim(),
            model.dtype,
            &model.device,
        )?;
        let sched = Scheduler::new(ecfg.max_slots, ecfg.max_ctx, ecfg.prefill_chunk, 8);
        let eos = model.cfg.eos_token_id.clone();
        Ok(Self {
            model,
            kv,
            sched,
            eos,
            stats: EngineStats::default(),
        })
    }

    /// Blocking loop: run until the request channel closes and all work drains.
    pub fn run(&mut self, rx: Receiver<Request>) -> Result<()> {
        let mut open = true;
        while open || self.sched.has_work() {
            // Drain new requests; block only when fully idle.
            loop {
                match rx.try_recv() {
                    Ok(r) => self.accept(r),
                    Err(std::sync::mpsc::TryRecvError::Empty) => {
                        if !self.sched.has_work() && open {
                            match rx.recv() {
                                Ok(r) => self.accept(r),
                                Err(_) => {
                                    open = false;
                                    break;
                                }
                            }
                        } else {
                            break;
                        }
                    }
                    Err(std::sync::mpsc::TryRecvError::Disconnected) => {
                        open = false;
                        break;
                    }
                }
            }
            if self.sched.has_work() {
                self.step()?;
            }
        }
        Ok(())
    }

    fn accept(&mut self, r: Request) {
        let seq = Sequence::new(r.prompt, r.params, r.tx);
        if let Err(seq) = self.sched.submit(seq) {
            let _ = seq.tx.send(Out::Done {
                finish: FinishReason::Length,
            });
        }
    }

    /// One engine step: a batched decode pass over all decode-ready sequences
    /// plus at most one prefill chunk.
    pub fn step(&mut self) -> Result<()> {
        let trace = std::env::var("BARGE_TRACE").is_ok();
        let t0 = Instant::now();
        self.sched.admit();

        // --- decode pass ---
        let b = self.sched.decoding.len();
        if b > 0 {
            let positions: Vec<usize> = self.sched.decoding.iter().map(|s| s.computed).collect();
            let tokens: Vec<u32> = self.sched.decoding.iter().map(|s| s.next_input()).collect();
            let td = Instant::now();
            let logits = self.model.decode(&self.kv, &positions, &tokens)?;
            let flat: Vec<f32> = logits.flatten_all()?.to_vec1()?;
            if trace {
                eprintln!("  decode fwd+copy b={b}: {:.1}ms", td.elapsed().as_secs_f64() * 1e3);
            }
            let vocab = self.model.cfg.vocab_size;
            let params: Vec<_> = self.sched.decoding.iter().map(|s| s.params.clone()).collect();
            let param_refs: Vec<&_> = params.iter().collect();
            let mut states: Vec<&mut _> = self
                .sched
                .decoding
                .iter_mut()
                .map(|s| &mut s.sampler)
                .collect();
            let next = sample_batch(&flat, vocab, &param_refs, &mut states);
            self.stats.decode_tokens += b as u64;
            self.stats.decode_batch_sum += b as u64;

            let mut finished: Vec<usize> = vec![];
            for (i, tok) in next.into_iter().enumerate() {
                let seq = &mut self.sched.decoding[i];
                seq.computed += 1;
                seq.out.push(tok);
                let _ = seq.tx.send(Out::Token(tok));
                let hit_eos = !seq.params.ignore_eos && self.eos.contains(&tok);
                let hit_len = seq.out.len() >= seq.params.max_tokens
                    || seq.prompt.len() + seq.out.len() >= self.sched.max_ctx;
                if hit_eos || hit_len {
                    let _ = seq.tx.send(Out::Done {
                        finish: if hit_eos {
                            FinishReason::Stop
                        } else {
                            FinishReason::Length
                        },
                    });
                    finished.push(i);
                }
            }
            // Swap-remove finished, highest slot first, keeping KV compacted.
            for &i in finished.iter().rev() {
                let last = self.sched.decoding.len() - 1;
                if i != last {
                    let len = self.sched.decoding[last].computed;
                    self.kv.move_slot(last, i, len)?;
                }
                self.sched.decoding.swap_remove(i);
            }
        }

        // --- prefill chunks (several prompts per step under one token budget) ---
        let plans = self.sched.prefill_plans();
        let mut completed_idx = vec![];
        for plan in &plans {
            let p = &self.sched.prefilling[plan.idx];
            let tokens = p.seq.prompt[plan.start..plan.start + plan.len].to_vec();
            let tp = Instant::now();
            let logits = self
                .model
                .prefill(&self.kv, plan.slot, plan.start, &tokens, plan.completes)?;
            if trace {
                eprintln!(
                    "  prefill fwd t={} start={} slot={}: {:.1}ms",
                    plan.len,
                    plan.start,
                    plan.slot,
                    tp.elapsed().as_secs_f64() * 1e3
                );
            }
            self.stats.prefill_tokens += plan.len as u64;
            let seq = &mut self.sched.prefilling[plan.idx].seq;
            seq.computed += plan.len;
            if plan.completes {
                let flat: Vec<f32> = logits.unwrap().flatten_all()?.to_vec1()?;
                let params = seq.params.clone();
                let tok = sample_batch(
                    &flat,
                    self.model.cfg.vocab_size,
                    &[&params],
                    &mut [&mut seq.sampler],
                )[0];
                seq.out.push(tok);
                let _ = seq.tx.send(Out::Token(tok));
                completed_idx.push(plan.idx);
            }
        }
        // Move completed prefills into the decode region (descending index so
        // swap_remove doesn't disturb pending removals).
        for &idx in completed_idx.iter().rev() {
            let pre = self.sched.prefilling.swap_remove(idx);
            let (slot, seq) = (pre.slot, pre.seq);
            let dest = self.sched.decoding.len();
            self.kv.move_slot(slot, dest, seq.computed)?;
            self.sched.release_prefill_slot(slot);
            let last = *seq.out.last().unwrap();
            if (!seq.params.ignore_eos && self.eos.contains(&last)) || seq.params.max_tokens <= 1 {
                let _ = seq.tx.send(Out::Done {
                    finish: FinishReason::Stop,
                });
            } else {
                self.sched.decoding.push(seq);
            }
        }

        self.stats.steps += 1;
        self.stats.busy_secs += t0.elapsed().as_secs_f64();
        Ok(())
    }
}
