# Joint one-byte tied embedding/output consumer route

## Decision question

Does the measured tied-head bottleneck justify one truthful joint FP8/int8 embedding-plus-output consumer that both reduces decode wall time and crosses the L40S c8 memory boundary, or is no pinned-runtime route credible enough for a later CUDA/quality falsifier?

The prior FLOP-only bound closed this line at a 0.375% whole-request ceiling. Exact-runtime evidence now contradicts FLOPs as the latency proxy: BF16 head M=1 costs 1.402982 seconds/request over 358 steps, while M8 still costs 0.178124 seconds and the same tied matrix occupies 2.625 GiB. A joint one-byte representation would save 1.3125 GiB and analytically move conservative primary c8 from 45.046 to 43.7335 GiB, but it changes both token embeddings and logits and has no proven pinned consumer. This project resolves that mechanism at `$0`; it does not reopen W4 or claim quality.

## Inputs and required result

Consume the exact six rows in `../gemma_l40s_parallel_lm_head_measurement_final/artifacts/gemma-l40s-head-final-20260717t065653z/summary.json`, `../tied_vocab_projection_cost_bound/VOCAB_BOUND.json`, the pinned image/runtime identities, and exact Gemma source/config. Inspect the actual installed `VocabParallelEmbedding`/`ParallelLMHead`, quantization method interfaces, weight loaders/tie semantics, sampling/logprob path, and supported SM89 one-byte kernels. Use CPU-safe construction/source tests in the exact local image if useful; no CUDA or provider.

Return exactly one `JOINT_HEAD_PACKET.json` or `NONE.json`. A packet must specify one implementation that stores a single shared one-byte weight plus explicit scales without duplicating BF16, truthfully serves both embedding lookup and output projection, binds exact classes/symbols/layout, estimates measured c1/c2/c4/c8/c16/c32 wall savings from a conservative byte/compute model, and defines the later actual-consumer CUDA rows plus raw-output/embedding quality boundary. Require at least 5% plausible whole-request wall reduction at an economically viable batch or a real c8 capacity discontinuity; otherwise typed none.

The later quality gate must include held-out common plus rare multilingual/code/tool tokens, exact token embeddings/logits/output IDs where deterministic, logprobs/sampling/stop behavior, finite scales, and mutation rejection. Label any non-quality-preserving proxy. Do not propose another source/admission successor, a shortlist, output-only duplicate weight, W4 checkpoint, or provider run.

## Budgets

- Wall clock: 50 minutes.
- Compute: 2 local CPU-hours; no GPU.
- Storage: 2 GiB project-local including at most 512 MiB bounded image/source probes; no shared `/tmp`.
- Spend: `$0`; no provider, checkpoint weights, compilation, CUDA, endpoint, or quality execution.

Write the one typed terminal, concise decision/log, and terminal status.
