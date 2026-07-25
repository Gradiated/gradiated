# Research log

## 2026-07-25 — source-complete 55-local/5-global candidate

Question: can changing the pinned 60-layer 5-local/1-global geometry produce a
material H200 c32 gain with a credible recovery path?

Action: verified the three director-bound hashes, the exact M384 trace, the
scope-matched prefill subtype map, the prefill profile, and the four-row NCU
export. `simulate_placements.py` reconstructs all 60 layers. For verification
it maps 15 exact c32 target cycles into each layer's QKV, attention, output,
gate/up, and down cost. For prefill it combines measured local/global attention
subtype time with measured aggregate FP8-linear time apportioned by exact
projection FLOPs. It also computes exact causal/windowed attention pairs, FP8
KV bytes, projection parameters, and two counter-derived full-request pass
counts.

Evidence: stock M384 attention is `1.339264 ms` per local layer and
`3.275520 ms` per global layer; the valid mixed component is `0.936512 ms`
local and `3.274080 ms` global. The trace-derived attention projection medians
are `0.138144 ms` local and `0.211249 ms` global. Scope-matched prefill
attention is `34.671859 ms` per local layer and `150.025741 ms` per global
layer per c32 batch. Placement-only movement with ten global layers has zero
modeled cost effect.

Result: retain one quality-unsafe candidate with full layers
`[5,17,29,41,53]`. Replacing the other five global layers predicts
`12.053363 ms` less target-cycle work, `31.526–33.291 ms/request` total
savings, and `0.591858–0.593624 s/request` against the locked
`0.625149102` denominator: `5.043–5.325%`. It removes `330,301,440`
attention-linear parameters and `1,419,509,760` c32 KV bytes (`7.493%`).
Measured NCU geometry per converted layer moves from 255 to 173
registers/thread, 102.4 to 37.888 KiB dynamic shared memory, 7.76 to 15.52
waves/SM, 1.351311 to 0.662617 GB DRAM reads, and 6.713353 to 1.554938 GB L2
bytes. No batching gain is credited because prior c48/c64 results were
negative.

Interpretation: this is a source-complete performance candidate, not a
deployable model or a measured endpoint. The M8 endpoint consumer produced no
durable pair, and prefill linear time is a FLOP-calibrated allocation rather
than a per-shape timing. The cheapest later proxy copies nearest-local
attention weights into the five converted modules, keeps MLP/norm weights,
and measures one exact c32 target-forward comparison before any endpoint.
Recovery requires teacher hidden-state/attention/logit distillation on
long-context and tool-use data, then exact GPQA-Diamond, TauBench,
long-context, tool-format, and multimodal gates.

One initial local invocation was invalid only because the NCU CSV units row
was parsed as a sample. The consumer now filters nonnumeric IDs; the same
deterministic simulation completed without changing the scientific question.
`python3 -m unittest -v test_simulate_placements.py` passes both binding and
combinatoric tests. No GPU was claimed and provider spend is `$0`.

## 2026-07-25 — conditional H200 component not run

Question: can the promoted 55-local/5-global proxy be measured through one
exact-c32 target-forward control/candidate component on the retained H200?

Action: audited `DIRECTOR_HYBRID_55L5G_H200_COMPONENT_BINDING.json` and all
five bound input hashes. Every hash matched, including the binding digest.
The required predecessor `DFLASH_CYCLE_ORACLE_TERMINAL.json` was absent and
the predecessor project remained active with the H200 claimed, so the claim
gate was closed at 2026-07-25T18:05:01Z. No bench was claimed, no checkpoint
was altered, and no runtime, profiler, endpoint, training, or quality arm
started. The project-local tree has no exact-runtime proxy/consumer to run
offline; adding a speculative runner after the closed gate would not create
decision-bearing evidence.

Result: persist `HYBRID_55L5G_H200_COMPONENT_TERMINAL.json` as typed
`unrun_claim_gate_closed` with zero incremental spend and yield the warm bench
window to grouped LM-head. The offline result remains source-complete only:
predicted 5.043–5.325% service reduction and 7.493% c32 KV residency saving;
no H200 component claim is made.
## 2026-07-25 — measured hybrid component

The repaired launch window was claimed atomically on `h200-dflash-adapter-e00vyqp7gxsr34wrtz` at 20:14:32Z. The five bound inputs were copied into `inputs/bound/` and hash-verified. A five-layer nearest-compatible-local weight-copy proxy (candidate layers 5,17,29,41,53; copied local layers 11,23,35,47,59; MLP/norm/embedding/lm_head preserved) was measured once through pinned SGLang v0.5.13 with profiler off, exact c32, and no endpoint/training/DFlash replay.

Measured result: weighted attention reduction `0.20334496337472074` (split checks `0.2033000292246645`, `0.20262042704666094`); local sliding component median 1.34915 ms control vs 0.94061 ms candidate; full component median 3.29338 ms control vs 3.29469 ms candidate. Both outputs were finite and allclose; full output was bit-exact and candidate replay was bitwise reproducible. This is component evidence only, not a quality or deployability result. The H200 was released ready at about 20:18Z; conservative project spend recorded as $0.19.

## 2026-07-25 — endpoint claim gate closed

Question: can the settled quality-unsafe 55-local/5-global proxy be tested as one exact-c32 stock-control/candidate endpoint pair?

Action: verified `DIRECTOR_HYBRID_55L5G_H200_ENDPOINT_BINDING.json` and its binding hash. The hard claim deadline was `20:30:00Z`; the gate and clean shared-pool state were checked at `20:30:35Z`. The retained H200 was available with a `22:00:00Z` lifecycle deadline, but the binding explicitly forbade a late claim. No GPU was claimed, no endpoint or request invocation started, no DFlash or component work was replayed, and no new spend accrued.

Result: persist `HYBRID_55L5G_H200_ENDPOINT_TERMINAL.json` as typed `unrun_claim_gate_closed`. The endpoint hypothesis remains unmeasured; the prior component result remains settled component-only evidence. Await a new in-window director binding rather than violating the expired contract.

## 2026-07-25 — phase-selective dispatcher and dual-cache bound

Question: can the five measured local proxies run only in speculative target
verification while prefill and ordinary decode remain on stock attention?

Action: traced the pinned `ForwardMode`, ngram verifier, CUDA-graph runner,
Gemma attention constructor, SWA/full cache pools, and Triton cache writes.
`TARGET_VERIFY` is one scalar mode for the whole captured graph and owns
request-major `batch × draft_depth` rows (`32 × 12 = 384` here); padding rows
own no request. Verification allocates all draft KV slots, then frees or moves
unaccepted rows. Gemma's global and local modules cannot share K/V: they have
different head dimensions (`512` versus `256`), KV-head counts (`4` versus
`16`), RoPE, projection shapes, receptive fields, and cache layouts.

Result: `phase_dispatcher.py` is an executable, source-bound dispatch contract.
At converted layers `[11,23,35,47,59]`, prefill/decode use stock attention and
also write proxy-local shadow K/V; `TARGET_VERIFY` uses proxy-local attention
and also writes stock-global shadow K/V. Allocation, accepted-row moves, and
rejected-row frees must be mirrored across both banks. The phase branch is
capture-static because the speculative graph is captured separately as
`TARGET_VERIFY`; only values and logical row counts vary at replay.

Cost: the measured placement model supplies `12.548–14.313 ms/request` gross
target-only savings. Width-scaled versus full-QKV-launch bounds for the shadow
projections, plus analytical H200 peak-bandwidth write floors, cost
`0.755–1.904 ms/request` when ordinary-decode steps are zero. Net is therefore
`10.644–13.558 ms/request`, or `1.703–2.169%` of the locked
`0.625149102 s/request` denominator, with `1,342,177,280` extra c32 cache bytes
(`7.085%`). A 358-step ordinary-decode sensitivity remains positive at
`5.897–11.183 ms/request`, but that is a scenario, not measured workload
telemetry.

Decision: retain a narrow `source_complete_candidate` for one later exact-c32
component falsification, not an endpoint. The first expected semantic
divergence is the layer-11 target-verification attention output. The later
component must populate both banks, prove stock equivalence before verification,
replay one 384-row verify graph, mirror an accept/move/free pattern, prove the
next stock-operator decode matches an eager dual-cache reference, and show
positive net timing. Stock operators after verification do not restore
all-stock semantics: later-layer stock K/V for accepted rows are derived from
hybrid hidden state after the first converted layer diverges. No GPU was
claimed, no endpoint ran, no provider mutation occurred, and incremental spend
was `$0`. `python3 -m unittest -v test_phase_dispatcher.py` passes 8 tests.
