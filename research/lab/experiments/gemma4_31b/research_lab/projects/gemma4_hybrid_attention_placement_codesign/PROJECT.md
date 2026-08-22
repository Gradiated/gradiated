# Gemma 4 hybrid-attention placement co-design

## 2026-07-27 permanent 55-local/5-global endpoint readmission

The settled exact H200 component is positive: replacing full attention at
layers `[11,23,35,47,59]` with the nearest compatible local-attention weights
reduced the weighted attention boundary by `20.334496%`, with finite,
all-close local outputs and bit-exact global replay. The bound matched c32
endpoint was never run; its only terminal is `unrun_claim_gate_closed`, with
no claim, server, request, control, or candidate invocation.

Readmit only that unconsumed permanent 55-local/5-global endpoint under
`DIRECTOR_HYBRID_55L5G_CURRENT_WARM_READMISSION_20260727T0121Z.json`. First
implement the two named current-bench runner/owner files offline. Do not claim
until the exact cumulative `$8.50` reservation, a lifecycle extension, and a
later director claim binding are durable. The old phase-selective
TARGET_VERIFY consumer, its HTTP-500 requests, all completed components, and
all DFlash work remain closed.

## 2026-07-25 H200 component reopening

The prior H200 continuation closed only because its claim-time predecessor gate
expired; it consumed no science and all five bound hashes matched. DFlash has
now completed its one authorized endpoint pair and released the retained H200.
Reopen only the already-bound quality-unsafe 55-local/5-global execution proxy.

Claim the named bench only under
`DIRECTOR_HYBRID_55L5G_H200_COMPONENT_REOPENING.json`, run one matched
profiler-off exact-c32 target-forward control/candidate component through the
real pinned runtime, persist `HYBRID_55L5G_H200_EXECUTION_TERMINAL.json`, stop
all experiment processes, and release. No endpoint, training, broad quality
evaluation, deployability claim, or DFlash replay is authorized.

## Question

Can a model-level change to the number or placement of full-attention versus
1,024-token sliding-attention layers materially reduce the exact Gemma 4 c32
critical path on H200, while retaining a credible post-training and quality
recovery path?

## Why it matters

The campaign target is `0.500119281574996 s/request` against the locked
quality-qualified `0.625149101968745 s/request` denominator. Kernel work shows
that attention is important but cannot close the target alone without changing
the model geometry: the complete measured M384 attention family has only a
`17.03–19.42%` maximum whole-request opportunity.

The exact checkpoint has 60 text layers arranged as ten repetitions of five
sliding-attention layers followed by one full-attention layer. The qualified
runtime's exact c32 component measures a `30.0726%` local-attention reduction,
approximately unchanged stock global attention, and a `20.2089%` weighted
attention reduction. This creates a concrete model/chip question: whether
fewer or differently placed expensive global layers, or a related change to
the hybrid geometry, can remove work on the H200 critical path or unlock more
economic batching.

## Bound evidence

- Exact checkpoint configuration:
  `../gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/config.json`,
  SHA256 `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`.
- Exact critical-path and attention ceiling:
  `../gemma4_h200_ngram_fixed_m384_executor_rewrite/FIXED_M384_EXECUTOR_OFFLINE_RESULT.json`,
  SHA256 `87199d4f35a3d4131e1b11cf619547a28ffc1d7d06467237b80cc320efdb67a4`.
- Exact mixed local-only component:
  `../gemma4_h200_ngram_fixed_m384_executor_rewrite/artifacts/mixed-local-m384-20260725t165205Z/preserved-component-attempt-1/COMPONENT_TERMINAL.json`,
  SHA256 `12fb8457e1b54c82de43506e72ef159b40ccf9379eb2f0f84607aef85417b115`.

## Scope and immediate evidence

Work offline and do not claim or provision a GPU. Reconstruct the pinned Gemma
4 layer geometry, SGLang producer/consumer path, exact prompt and verification
shapes, and H200 execution cost at layer granularity. Use the shared
accelerator inventory for stable chip facts and current source or papers only
where they resolve a concrete architectural uncertainty.

Build the smallest reproducible simulator or executable configuration proxy
that compares the baseline 50-local/10-global placement with a small set of
causally justified alternatives. Account separately for prefill, target
verification, KV bytes and residency, tensor-core geometry, launch structure,
memory capacity, and any batch-size consequence. Label a layer-remapping or
weight-reuse proxy as quality-unsafe; do not call it deployable evidence.

Return either:

1. one source-complete candidate with a predicted whole-request delta, the
   H200 counter or physical change that would falsify it, its post-training and
   quality burden, and the cheapest later target-GPU execution proxy; or
2. a typed `none` showing that plausible full/sliding placement changes cannot
   produce a competitive bound or credible quality-recovery path.

Do not broaden this into generic attention-kernel tuning, low-bit execution,
or another literature review. A later GPU experiment requires a new director
decision after the current mixed-M384 and grouped-head sequence.

## Portfolio consequence

A viable candidate becomes a quality-unsafe execution proxy before any
post-training spend. A negative result closes only hybrid layer placement and
releases the deep slot to the campaign's next hardware-specific low-bit or
sparse model intervention.

## Director-bound H200 component continuation

`PLACEMENT_SIMULATION_RESULT.json` selects the 55-local/5-global candidate with
full attention at layers `[5,17,29,41,53]`. The next result is executional:
materialize one explicit nearest-compatible-local attention weight-copy proxy
for converted layers `[11,23,35,47,59]` and measure a single exact-c32
target-forward control/candidate component through the real pinned runtime.

The exact identities, claim gate, evidence, and budgets are bound in
`DIRECTOR_HYBRID_55L5G_H200_COMPONENT_BINDING.json`. This proxy is explicitly
quality-unsafe. It authorizes no endpoint, training, broad evaluation, or
deployability claim. Claim only after DFlash releases and only when the bound
time and lifecycle gates preserve the grouped LM-head window.

## 2026-07-25 phase-selective deep continuation

The permanent 55-local/5-global proxy produced a positive exact H200 component
but exposes prefill, ordinary decode, and target verification to the same
quality-unsafe intervention. Investigate one narrower mechanism: preserve the
stock 50-local/10-global geometry for prefill and ordinary decode, and select
the five converted attention modules only for speculative target-verification
rows.

Work offline under `DIRECTOR_PHASE_SELECTIVE_HYBRID_CONTINUATION.json`. Trace
the pinned forward-batch modes, graph boundary, KV semantics, row ownership,
Gemma layer geometry, and H200 consequences together. Return either a
source-complete dispatcher with a measured-evidence-grounded phase cost model
and cheapest later falsification, or typed `none`. Do not claim a GPU, run an
endpoint, imply quality preservation, or reopen the completed permanent
placement comparison.

## 2026-07-25 exact H200 dual-cache component falsification

`PHASE_SELECTIVE_HYBRID_RESULT.json` is source-complete and predicts only a
`1.703–2.169%` whole-request reduction, so spend is limited to the cheapest
causal discriminator rather than an endpoint. Under
`DIRECTOR_PHASE_SELECTIVE_H200_COMPONENT_BINDING.json`, reuse the released
retained H200 for one exact c32 dual-cache sequence: stock prefill and ordinary
decode, one 384-row depth-12 TARGET_VERIFY replay, mirrored accepted-prefix
move/free, and one post-accept stock decode against an eager dual-cache
reference.

This iteration is executional. Require every stock-path, row-ownership,
cache-lifecycle, graph, and positive-net-timing gate in the binding. A
nonpositive net result or any exactness failure closes this realization
without an endpoint. Do not claim quality preservation, train, run endpoint
requests, or mutate provider lifecycle.

## 2026-07-25 full-model binding repair and conditional endpoint

The first H200 attempt reached only a synthetic attention operator and is an
`infrastructure_terminal`; it did not exercise the required full-model stock
prefill, ordinary decode, target verification, or post-accept eager reference.
Repair that integration boundary inside this project under
`DIRECTOR_PHASE_SELECTIVE_FULL_MODEL_H200_BINDING.json`.

Claim the retained H200 immediately, replace the synthetic adapter with the
pinned full Gemma forward path, and replay only the unproven component gates.
If and only if the full-model component is exact and net-positive, run the
already-bound contemporaneous c32 stock/candidate endpoint pair in the same
claim. The endpoint is a quality-unsafe execution proxy, not a deployable
candidate. Preserve resident state, release by the binding deadline, and do
not add another source, readiness, audit, or provider gate.

## 2026-07-25 ownerless-terminal recovery and queue yield

The vanished local owner stranded a completed remote
`PHASE_SELECTIVE_FULL_MODEL_H200_COMPONENT_TERMINAL.json`. It is pre-science:
the standalone `ModelRunner` allocated `138.71 GiB` of the `139.80-GiB` H200
while constructing the pinned model, then failed on a `168-MiB` allocation
before the phase adapter or any candidate CUDA invocation. The exact
62.58-GB checkpoint remains intact and no remote worker or GPU process
survived.

Do not replay this deterministic near-capacity construction or hold the warm
bench behind another integration repair. Under
`DIRECTOR_FULL_MODEL_OOM_RECOVERY.json`, work without CUDA to bind an
execution-equivalent single-model producer and the already-selected
phase/dual-cache adapter, with an explicit peak-memory margin and typed source
terminal. This is an operational continuation in the same project; the
scientific hypothesis, converted layers, component gates, and conditional
endpoint remain unchanged and unconsumed. A later director decision owns any
GPU re-admission after the prepared certified-lazy and FP8 components.

## 2026-07-26 corrected-allocator H200 component

The graph-gap and persistent weight-stream arms have both released the retained
H200, and the latter rejected only its exact Stream-K M32 schedule. The
source-complete native-vector and batch-tree allocator repair is now the
highest-value compatible warm-bench discriminator.

Run exactly one corrected full-model TARGET_VERIFY component under
`DIRECTOR_CORRECTED_ALLOCATOR_H200_COMPONENT_20260726T0604Z.json`. This is a
materially new, source-hash-bound realization of the phase-selective 55-local/
5-global proxy, not a replay of the consumed discovery invocation. Measure the
stock and corrected candidate through target logits, accepted-prefix
lifecycle, and post-accept stock decode. No endpoint, training, broad quality
evaluation, or provider lifecycle change is authorized.

## 2026-07-27 expired warm-bench rebind

The selected warm H200 reached its lifecycle deadline before the new endpoint
owner was usable. Its watchdog cleaned the exact instance and managed disk,
provider absence was verified, and the inventory record was retired. Continue
only the same project's localized offline owner repair under
`DIRECTOR_HYBRID_55L5G_RETIRED_BENCH_REBIND_20260727T0139Z.json`.

The scientific endpoint contract is unchanged. A future owner must resolve all
connection, checkpoint, image, claim-generation, and lifecycle fields from a
later live bench record; the retired bench identity and remote checkpoint path
are historical evidence and are not launch authority.

## 2026-07-29 endpoint-proxy reactivation

Reactivate only the unconsumed permanent 55-local/5-global c32 endpoint proxy.
Its exact H200 component reduced weighted attention time by `20.3345%`; the
phase-selective TARGET_VERIFY continuation and every previously consumed arm
remain closed.

First complete the localized bench-free owner repair already identified in
project state: stage the pinned model configuration and tokenizer inputs,
resolve every connection and checkpoint field from a future live inventory
record, and make readiness fail immediately on child or container death.
Then stop with a hash-bound execution packet. Do not claim a GPU or operate a
provider during this preparation.

The project requests a `$22` cumulative ceiling. A later director may
provision one H200 lifecycle only after that exact reservation is durable and
the packet is executable. Run one contemporaneous stock/permanent-55L5G c32
pair with the original quality-unsafe label, fixed checkpoint/workload, and
matching request/token accounting. This is a performance proxy, not a
deployable or quality-qualified model result.
