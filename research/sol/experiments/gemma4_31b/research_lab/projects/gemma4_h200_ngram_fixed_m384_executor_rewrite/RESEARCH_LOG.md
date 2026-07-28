# Research log

## 2026-07-25 — admitted

This lane is admitted as the second genuine 20%-class bet alongside DFlash.
It is not another mask or scheduler micro-optimization: the required output is
an exact fixed-M384 target-forward executor implementation and measurement.
Offline source/trace work starts immediately; H200 work queues behind the
independent live DFlash owner.

## 2026-07-25 — bound trace resolved; executor packet ready behind DFlash

Question: does the persisted c32 trace leave enough non-overlapping
target-forward time for the 20% objective, and which exact recurring boundary
should receive the one implementation?

Action: verified all nine `EVIDENCE_BINDING.json` hashes, materialized the
exact trace and runtime sources project-locally, reconstructed the request and
verification union, and froze a guarded H200 c32/M384/max-extend-12
`BLOCK_M=8` attention overlay. Added the actual stock/candidate
`extend_attention_fwd` consumer, CUDA-graph replay oracle, four-launch NCU
consumer, matched c32 endpoint pair, immutable packet, and retained-claim
owner. The experiment contract is `EXPERIMENT_CONTRACT.json`.

Evidence: `artifacts/BOUND_CRITICAL_PATH.json` (`bcc523eb...`) binds 15 exact
M384 cycles. Counter-derived full-request target verification is
`0.158548-0.180858 s/request`, or `25.36-28.93%` of the qualified
`0.625149 s/request` baseline. Reaching `0.500119 s/request` therefore needs
`69.13-78.86%` target-boundary reduction. Attention contributes
`1.488206 s` of the `2.216848 s` captured GPU union (`67.13%`), with 750 local
and 150 global launches, 255 registers/thread, and stock 64/32-row tiles for
12 useful rows. The eight-row tensor-core shape compiled for SM90 in the
pinned Triton 3.6.0 image; actual candidate execution remains unconsumed.

Interpretation: the complete target-forward 20% ceiling is physically open
but narrow and demands a large boundary win. Attention is 67.13% of that
target GPU union, so even eliminating the entire family would save only
17.03-19.42% of a qualified request. The implemented attention candidate is
therefore stackable-only; it cannot independently establish the 20% campaign
objective. It remains a causal, fixed-geometry test of padded
query/live-accumulator waste, not a replay of the rejected 1x2x1 FP8 cluster,
BLOCK_M=16/32 tree candidates, masks, penalties, or allocator work.

Terminal: `FIXED_M384_EXECUTOR_OFFLINE_RESULT.json` records the required
source-complete offline result. The protected H200 remains claimed by live
priority-8490 `gemma4_h200_dflash_endpoint` owner PID 841139, and the current
director binding explicitly forbids GPU or remote-bench access. After DFlash
releases, the director must consume the offline result, decide whether this
stackable-only candidate remains competitive, and explicitly bind a paid
execution plus lifecycle/watchdog before any claim. Current project provider
spend remains `$0`.

## 2026-07-25 — H200 execution continuation active

Question: can the director-bound fixed-M384 exact-consumer measurement reach
its component, four-launch counter, and conditional endpoint decision under
the released resident H200?

Action: verified every `DIRECTOR_H200_EXECUTION_BINDING.json` input and its
current available H200 identity, then launched a durable host-side owner with
a three-hour/$7.35 maximum exposure. The first pre-science materialization
attempt proved the resident root-owned checkpoint rejects unprivileged
hard-links into the project directory. It did not invoke CUDA, the component,
or either endpoint arm. The repair uses privileged hard-links only, preserving
and re-hashing the resident bytes without a download or restage; it is now
progressing under the retained-claim continuation.

Evidence: `H200_EXECUTION_BINDING_VERIFICATION.json` binds all required local
hashes. The invalid attempt is preserved at
`artifacts/fixed-m384-20260725t162032Z/OWNER_EXCEPTION.json`; its measured
exposure is `$0.027903122819444445`. The durable replacement controller is
recorded in `STATUS.json.active_session`, with current staging evidence under
`artifacts/fixed-m384-20260725t162212Z/`.

Interpretation and next move: this is an ordinary filesystem ownership defect,
not scientific evidence. The resident target remains intact and exact; once
the hard-link reconciliation finishes, the controller proceeds directly into
the pinned CUDA-graph A/B, only profiles a correct positive component, then
runs the one matched c32 pair and persists the terminal/release evidence.

## 2026-07-25 — mixed local-only continuation launched

Question: can the measured local M8 gain survive exact target decisions when
global attention retains stock M32 geometry?

Action: verified the mixed director binding and all six bound hashes, claimed
`h200-dflash-adapter-e00vyqp7gxsr34wrtz` once, and amended only the authorized
packet. The candidate now dispatches M8 exclusively for exact sliding-window
M384/head-dim-256 and audits stock M32 for exact global head-dim-512. The
component records first differing coordinates and split-sample reproducibility;
a 24-token exact c32 target-decision guard must pass before the sole full c32
pair.

Evidence: immutable packet `0ac896ce3bcfee6db26bc9654a1b9c6caf6b23822e8de978797dcffc9f948b09`
reuses all eight checkpoint files and the pinned image. PID-managed controller
915680 is live, heartbeat succeeded at `2026-07-25T16:52:50Z`, every checkpoint
row was reused by hash, and remote worker 118442 entered the real experiment
under `artifacts/mixed-local-m384-20260725t165205Z`.

Interpretation and next move: the claimed session is bounded by cumulative
project spend, with an absolute `2026-07-25T18:38:22.595730Z` deadline. It will
persist `MIXED_LOCAL_M384_TERMINAL.json`, retrieve raw evidence, stop experiment
processes, and release the warm bench; a correctness or dispatch failure skips
the full endpoint.

## 2026-07-25 — component and counter consumers repaired in place

Question: did `component_harness_invalid:0` represent failed science, or a
completed producer hidden behind an observer path defect?

Action: retrieved the legacy-path terminal, invocation marker, and raw logs
before signaling repair. The terminal proved a completed component, so it was
moved under the mixed-run artifact root and imported without CUDA replay. The
same path alignment exposed a post-capture root-ownership failure while writing
`ncu.stdout`; the completed NCU report was preserved, its exact capture command
was suppressed once by hash, and only export/parsing resumed. Both repair
requests and amendments are retained project-locally.

Evidence: component terminal `12fb8457...` passed mixed dispatch and both
positive split samples, with a measured `20.2089%` weighted attention reduction.
Local M8 improved `30.0726%`, global stock remained bit-exact, and the local
first difference starts at coordinate `[0,0,0]`, showing tile-dependent numeric
order rather than an eight-row mask boundary. NCU report `5bb0ef1d...` and its
four-launch invocation were consumed once; exported counter terminal preserves
that report hash and CSV `67e03321...`.

Interpretation and next move: neither repair is a new scientific sample. The
shared Docker command path was restored after export. The live retained owner
has crossed both repaired boundaries and launched the exact c32 guard-control
server; only a passing control/candidate decision guard admits the full pair.

## 2026-07-25 — endpoint consumer repaired in place; exactness guard rejected candidate

Question: did `endpoint_pair_harness_invalid:1` hide a consumed endpoint arm, or
was the endpoint consumer reading the wrong output root?

Action: retrieved the complete current pair directory and archived the invalid
zero-terminal root as `pair-invalid-consumer-20260725t174400Z`. The failure was
localized to `endpoint_pair.py`: the runner was given `/work/artifacts/pair/<arm>`
while the consumer read the current mixed artifact root. Patched only that path
translation, wrote the hash-bound repair request against the recorded ready hash,
and resumed the endpoint consumer under the retained owner without replaying the
component or NCU producer.

Evidence: repaired guard control and candidate each completed 32/32 requests with
matching request hashes, stable servers, and the required local-M8/global-stock
dispatch. `TARGET_DECISION_GUARD_TERMINAL.json` records `mixed_dispatch_match=true`
but `semantics_match=false`; `PAIR_TERMINAL.json` therefore records
`endpoint_executed=false`, `valid=false`. The scientific terminal is
`MIXED_LOCAL_M384_TERMINAL.json` with `result=nonpositive_or_invalid` and the
component preserved as passing. Full endpoint timing was correctly not consumed.

Interpretation and next move: the fixed-M384 local-M8 realization is rejected for
exact integrated semantics despite its positive component timing. Close this
candidate and do not replay it. The H200 owner stopped and released; cumulative
measured spend is `$2.9737686855138894`.

## 2026-07-25 — stock-order continuation returns typed none

Question: where does M8 first change target decisions, and can one materially
different stock-order schedule lower its measured 173-register/37,888-byte
dynamic-shared pressure without a GPU?

Action: decoded the persisted 32/32 guard with the hash-matched tokenizer and
compiled the full stock, rejected M8, and one M64/N64/DV64x4 value-stripe
schedule for SM90 in the pinned Triton 3.6.0 image. The only new schedule keeps
stock QK, mask, online-softmax, and per-feature accumulation order while
partitioning independent value features. A deterministic float32 operation-order
fixture was bitwise equal.

Evidence: `artifacts/STOCK_ORDER_LOCALIZATION_AND_FIXTURE.json` shows 15/32
requests diverge; 10 diverge at reconstructed output token zero, beginning with
request 0 (`61599` versus `23304`; the server omitted raw IDs). The earliest
affected model boundary is layer-0 sliding-attention prefix QK. Stock lowers
M64 FP8 E5M2 QK to `warp_group_dot`; M8 widens the operands to FP16 and lowers
an M8 `tt.dot` before the first softmax max/sum. The value-stripe source restores
stock QK lowering, but `artifacts/SM90_STOCK_ORDER_DV64_COMPILE_RESULT.json`
reports 81,920 dynamic-shared bytes and predicts 31.03 waves/SM, versus M8's
measured 37,888 bytes and 15.52 waves/SM.

Interpretation and next move: the new schedule is semantically causal but fails
the required physical mechanism: output striping leaves M64 Q/K staging at the
stock 80-KiB allocation, adds 44,032 shared bytes versus M8, repeats QK/mask
work four times, and doubles grid waves. `STOCK_ORDER_PRESERVING_ATTENTION_OFFLINE_RESULT.json`
therefore records a scoped typed none at `$0`; do not nominate it for H200.
