# Together Compiler reproduction on DeepSeek V4.1 Flash

This reproduces the system in *Together Compiler: Continual Compilation for AI Inference* (Together AI, 2026-11-04) at small scale. Agents optimize the forward pass of the production vLLM build of DeepSeek V4.1 Flash on one 4×B300 node (RunPod `yzno396wdsidu4`). A tiered persistent engine measures every candidate without restarting.

All numbers below were measured on 2026-11-07 unless labelled otherwise.

## What was built

| Module | Paper component |
| --- | --- |
| `tkcc/engine.py`, `tkcc/worker_ext.py` | Tiered persistent engine. vLLM starts once per tier. A job hot-reloads a candidate on all four TP ranks, recaptures the decode CUDA graphs, runs a correctness gate, measures decode speed, and tears down. |
| `tkcc/prepare.py` | Fast tier model: the first 12 of 40 layers, with cross-layer references (shared KV, indexers, Engram) trimmed to match. |
| `tkcc/workload.py` | Real code and prose prompts of exactly 32,768 tokens. AgentX traces publish only token lengths, so their shape is kept and the content is real text. |
| `tkcc/scoring.py` | Correctness gate relative to the stock engine's own run-to-run agreement (stock greedy decoding is not deterministic), plus a weight checksum. |
| `tkcc/costmodel.py`, `tkcc/micro.py` | Appendix D cost model with exact byte counts from the checkpoint headers and tiered hardware inputs (spec sheet or measured). |
| `tkcc/remote.py`, `agent/TASK.md` | Agent harness: three Claude Code agents (Opus 5.5, high effort), the minimal "make this forward pass as fast as possible" prompt, the engine source, and a shared message board. No knowledge base, no assigned strategies. |
| `tkcc/experiments/` | Interleaved A/B (`ab.py`), GSM8K check (`quality.py`), routing fidelity (`fidelity.py`), and gate controls. |

The decode metric is per-user tokens per second at concurrency 1, 8 and 32. It is computed from engine-core token timestamps over the window in which every request is decoding, so prefill is excluded.

## Results

### Optimization: 1.24× geometric-mean decode speedup

The best stack, `tkcc/experiments/best_stack_a3_fullstack2.py`, was measured in four interleaved A/B rounds against the stock forward pass on the 40-layer tier. The correctness gate passed in every round.

| Concurrency | Stock tok/s per user | Candidate tok/s per user | Paired speedup (min–max) |
| ---: | ---: | ---: | ---: |
| 1 | 168.6 | 228.4 | 1.35× (1.33–1.40) |
| 8 | 135.9 | 164.0 | 1.21× (1.19–1.28) |
| 32 | 99.7 | 115.3 | 1.16× (1.15–1.18) |

GSM8K few-shot accuracy on 200 problems was 91.0% for stock and 89.0% for the candidate. The four-problem gap is within one standard error (about 2 points each), so no quality change is detectable at this sample size.

The stack combines the agents' findings:
- a fused mHC (hyper-connection) boundary kernel that also emits the MXFP8 inputs (a3)
- the FlashMLA tile planner shared across KV-cache groups, cutting it from 10 to 3 calls per step (a2)
- a faster candidate-block top-k (a2)
- an Engram key-value K-split (a2)
- the host-side attention-metadata build captured in a CUDA graph (a2)
- a CPU fast path for the remaining metadata (a1)

Concurrency-1 decode was close to host-bound: about 3.2 ms of the 4.3 ms of host time per step went to metadata building, against a GPU forward pass of about 5.2 ms. Removing host work only paid off once the GPU-side fusions had made the forward pass shorter.

Several results were durably negative. A custom Lamport all-reduce, Triton MoE GEMMs, a fused finalize plus all-reduce plus norm kernel, and a custom router were each slower than the vendor kernels. The stock all-reduce took 37.6% of GPU kernel time, but FlashInfer's one-shot all-reduce was already at 4.7–6.2 µs.

The agents ran 91 jobs (69 successful slow-tier measurements) over about 3.5 hours of effective search.

### Persistent engine versus restarting

| Path | Measured time |
| --- | ---: |
| Cold start (empty JIT and autotune caches) | 916 s, of which FlashInfer autotuning was 524 s |
| Warm restart, weights in page cache | 173–202 s, plus ~70 s to the first measurement |
| Warm restart after another workload evicted the page cache | 608 s |
| Hot reload plus CUDA-graph recapture, 40 layers | 5.7 s median |
| Full slow-tier job (gate plus 3 repeats at each concurrency) | 35.6 s median |

Derived from these: restarting per experiment allows about 12 experiments an hour warm and about 3.4 cold, against about 100 with hot reload. That is a 8–30× gain, not the paper's 252×, because our baseline restart is a warm local restart rather than RSI-Inference-Bench's 11-minute engine launch.

### Measurement fidelity: experts hit per prefill chunk

Measured on the 40-layer tier, 320 layer-chunks per set.

| Query tokens | Real text | Random token ids | Uniform routing (analytical) |
| ---: | ---: | ---: | ---: |
| 128 | 153 | 135 (−12%) | 332 (+117%) |
| 256 | 202 | 168 (−17%) | 377 (+86%) |
| 512 | 242 | 198 (−18%) | 384 (+58%) |

Random token ids route to fewer experts than real text. The uniform routing that kernel benchmarks usually assume routes to far more. Either way, synthetic inputs misstate MoE load, which is the paper's point. Its "13–38% more experts" matches the uniform-routing case in direction, not magnitude.

### Cost model

The spec-sheet tier ranks attention TP4 with MoE TP4 first at concurrency 1, 8 and 32, with an upper bound of about 1,490 tok/s per user at concurrency 1. The measured tier uses 6.53 TB/s HBM copy bandwidth (82% of spec) and eager NCCL collectives at 45–70 µs. It flips the ranking to TP2-based layouts, the same kind of disagreement as the paper's Figure 4b.

Neither ranking was validated by measuring alternative layouts. The eager NCCL curve overstates in-graph collective cost.

## Limitations

- **One node.** The paper gives each tier its own replica; here the two tiers share the four GPUs and serialize through a lock. CPU contention from the fast tier biased slow-tier baselines by about 4–10% until the baseline was re-measured every 4 jobs. Final numbers therefore use interleaved A/B only.
- **Weak fast tier.** Twelve layers produce nonsense text, so the fast-tier gate only catches crashes and gross errors. At concurrency 1, the 12-layer and 40-layer tiers decode at the same speed because decode is host-bound there.
- **Gate sensitivity.** The stock engine's greedy outputs agree with themselves on only 25–60% of 8-token prefixes. The gate caught a 10% final-norm scaling but not a 3% routed-expert scaling, so it cannot certify subtle numeric errors.
- **Graphs.** Piecewise (prefill) CUDA-graph recapture hit a PyTorch allocator assertion, so both tiers ran `FULL_DECODE_ONLY`.
- **Process hygiene.** In-process profiling (CUPTI) permanently slowed the engine, which then restarted after profiled jobs. Watchdog exits orphaned GPU workers until exits killed all descendants.
- **Budget.** The agents had about 3.5 hours, not 24.

## Running it

See `tkcc/engine.py` (tier server), `tkcc/remote.py` (agent CLI), and the `agent/` brief. The tests run without a GPU:

```bash
cd research/tkcc && PYTHONPATH=. python3 -m unittest tests/test_tkcc.py
```

The production follow-up for SGLang lives in `product/inference/livetune`.
