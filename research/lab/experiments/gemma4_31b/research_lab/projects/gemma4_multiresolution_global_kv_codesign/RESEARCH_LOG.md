# Research log

## 2026-07-26T10:22:41Z — one-tile global-KV candidate

Question: can old global K/V alone close the locked 20% target while every
token still traverses all 60 full-width layers and every 1,024-token local
window stays exact?

Action: hash-bound the exact config, M384 c32 trace, pinned Gemma/backend/kernel
source, and prior subtype map; joined all 900 `_fwd_kernel` calls by source
shape, shared memory, and repeated layer order; implemented incremental
post-RoPE K/V summaries, protected/recent exact tiers, multiplicity-aware
causal attention, ordinary prefill, TARGET_VERIFY, decode, and a fused
one-tile Triton consumer. Ran dependency-free geometry/information-path tests
and the complete physical screen. The coordinator lacks Torch/CUDA, so the
consumer was source-audited and syntax-checked but not compiled or timed.

Evidence: every one of 15 cycles is `LLLLLG` repeated ten times: 750 local
calls sum to `997,521.149 us`; 150 global calls sum to `490,684.609 us`.
The selected 512-token summary / 8 recent / 8 protected design needs at most
57 compact entries in any claimed 32-row phase and 37 in the locked
12-token verifier, so it stays within one 64-key tile. Charging the fused tile
at 1.5x trace-linear cost, 256,901,120 bytes of worst-case summary and compact
traffic at 3x the impossible H200 HBM floor, and `110 us/cycle` of explicit
fixed overhead yields `0.4999581203857146 s/request`, a
`0.00016116118928138912 s/request` target margin. Artifact:
`MULTIRESOLUTION_GLOBAL_KV_PHYSICAL_SCREEN.json`
(`1d7d59a96a50f95b8cbadbb763ee072b5a4c462e1bb03f039dccda3905c84a30`).

Interpretation: `source_complete_physical_candidate`, intentionally
semantics-changing and quality-unqualified. The candidate is brittle:
256-token summaries, a 16-token recent tier, or 16 protected positions require
two tiles and miss; fallback must remain below `0.128732%`. No prompt-state,
local-attention, token/layer/width, or late-GEMM savings were credited.

Next move: only under a later GPU admission, compile the fused consumer on the
pinned H200 runtime, verify the real producer/consumer and request ownership,
measure profiler-off component and exact c32 endpoint timing, and reject on a
second tile or fallback above the bound before quality recovery.

## 2026-07-28T11:39Z — H200 execution path bound offline

Question: can the narrow one-tile candidate move directly to a real H200
component measurement without touching the occupied B200 lane?

Action: added `h200_component_runner.py` and `h200_endpoint_owner.sh`, then
ran the exact CPU/source fixture and geometry tests. The runner imports the
installed SGLang package only in component mode, executes the actual
producer/consumer boundary for prefill (32 rows), target verification (12
rows), and decode (one row), records compact-entry/fallback/request-ownership
contracts, and emits a stock/candidate timing pair only on CUDA. The owner
reads the future claimed H200 connection from the lab inventory, stages only
hash-mismatched immutable project bytes, heartbeats the retained claim, and
requires component success before a director-bound endpoint command.

Evidence: all geometry tests passed; the CPU fixture binds runner SHA-256
`3014ebf6beb96ecbd8a58cac0953bb4d3667dcd06c03251206068a91c4229d54`,
owner SHA-256
`f73a0d7b56ca6e90a59a31f2da4520d5cc4f27c159b16fd43259f43589a8eb8e`,
and candidate SHA-256
`ab5d951d338b3c404606efce2dbcb2f9235d016a8943ee6c01d601ee2f289f20`
in `H200_EXECUTION_READY.json`. No provider API, H200 claim, B200 access, or
scientific invocation occurred.

Interpretation: offline implementation is complete, but this is explicitly
not target-runtime readiness or a measurement. The project is paused for the
director's exact `$8.00` reservation and one registered `nvidia-h200-sxm`
bench.

## 2026-07-28T12:15Z — H200 owner repair and retained claim

The director-registered H200 passed its start fence and was atomically claimed
at `2026-07-28T12:15:43.326500Z`. The first detached owner exited before claim
because its inventory parser dereferenced `claim: null`; this is a localized
pre-science launcher defect, not scientific evidence. Its raw diagnostic is
preserved in `artifacts/h200-global-kv-20260728t1210z/owner.log`.

Patched only the parser and exact bench selection, then launched repair
generation 1 under the same durable owner artifact root. The repaired owner is
live with PID `3070398`, start ticks `135696058`, and claim generation
`claim-20260728T121543Z`; the remote command has reached the bound image pull.
No CUDA/science marker, component result, or endpoint command has been
observed. The claim remains retained for the first real component call.

## 2026-07-28T12:24Z — corrected H200 component pair

The first corrected component retry reached CUDA but Triton rejected the
kernel's non-constexpr `GLOBAL_KV_HEADS` references. That invalid attempt has
been preserved in `component-repair1.stderr` and was not counted as a sample.
The two address expressions were patched to the bound literal four, staged
atomically, and the failed remote output root was archived before retry.

The next retry passed the real H200 component contract. After a warmup call
excluded compile time, one stock/candidate pair measured:

- prefill: stock `85.556476 ms`, candidate `2.091168 ms`, 57 compact entries;
- target verification: stock `0.648035 ms`, candidate `1.095317 ms`, 37 entries;
- decode: stock `2.897647 ms`, candidate `1.214158 ms`, 26 entries.

All candidate outputs were finite, request ownership passed, fallback was
false, and the pinned SGLang runtime imported as version 0.5.13 on NVIDIA H200.
Artifact: `COMPONENT_RESULT_REPAIR3.json`. This is component evidence only;
no endpoint command was bound or run, and no endpoint performance claim is
made. The claim remains retained for the director-localized endpoint seam.

The retained repair handshake explicitly forbids stopping or replacing the
live owner. The owner remains PID `3070398` with start ticks `135696058` and
the H200 claim heartbeat is current. No director-bound `H200_ENDPOINT_COMMAND`
or exact checkpoint-backed c32 packet is present, so the endpoint arm remains
an external seam blocker rather than an invented or replayed command.

## 2026-07-28T12:40Z — endpoint repair dispatch is unsafe

Question: can the live retained owner resume only the unconsumed endpoint
operation while adopting `COMPONENT_RESULT_REPAIR3.json`?

Action: inspected the decision-bearing repair diagnostic once, verified the
live PID/start ticks and current heartbeat, and traced the running owner's
actual repair dispatch before signaling it. Also bound the exact checkpoint
manifest (`62,578,655,208` bytes,
`6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6`)
and exact c32 runner
(`143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`).

Evidence: PID `3070398` still matches start ticks `135696058` and heartbeats
the continuous claim. Its running owner bytes
(`4658d039640b5c56d50978c9f8c2cf96799523b5c9a2f626b0a9002c8eb24620`)
accept only `retry_scope=component`, then resume at the monolithic component
invocation. Any endpoint scope exits `76`; there is no retrieval/terminal
adoption scope. The existing generation-1 request is already component-scoped.
Audit:
`artifacts/h200-global-kv-20260728t1210z/REPAIR_ENTRYPOINT_AUDIT_20260728T1240Z.json`.

Interpretation: this is a typed retained-owner controller-contract boundary,
not scientific evidence. A component request would illegally replay the
settled producer, while an endpoint request would stop the owner. Under the
explicit no-stop/no-replace instruction there is no safe request to write.
No request, endpoint submission, process signal, release, or replay occurred.

Next move: authorize the director-specified hash-bound endpoint-owner
transition, or add an in-process endpoint-only adoption mechanism to the live
owner. Never dispatch component scope.

## 2026-07-28T12:52Z — endpoint-only owner launched

Question: can the explicitly authorized replacement preserve the settled
component and begin the exact checkpoint-backed endpoint path before the new
`12:58Z` fence?

Action: materialized the exact checkpoint manifest, all 62,578,655,208
checkpoint bytes, and exact c32 runner under this project; implemented the
production `RadixAttention` global-layer hook, endpoint pair, and durable
controller; hash-bound the packet; and verified hook installation in the
pinned SGLang image. After exact PID/start-ticks verification, stopped only
PID `3070398` and launched the endpoint-only owner in the existing claim.

Evidence: the first replacement exited pre-science because its local inventory
parser assumed list-shaped benches; preserved `owner-endpoint.log`, patched
only that parser, and made the permitted immediate retry. The corrected owner
is live as PID `3109321`, start ticks `135911495`,
`OWNER_STATE_ENDPOINT_RETRY1.json`. It persisted exact component adoption
without replay and finalized two checkpoint manifest entries. No server,
CUDA endpoint request, stock arm, or candidate arm has started.

Interpretation: durable endpoint execution is active, not a readiness
terminal. The hook routes only Gemma global layers (`layer_id % 6 == 5`,
32 Q heads, 16 KV heads, head dimension 256) through post-RoPE incremental
512-token summaries plus eight recent and eight protected exact positions;
sliding-window layers remain on the original SGLang consumer.

Next move: let the durable owner finish resumable staging and the single
stock-then-candidate c32 pair. Resume only from
`ENDPOINT_PAIR_TERMINAL.json` or `REPAIR_READY_ENDPOINT2.json`.

## 2026-07-28T13:40Z — candidate-only endpoint repair launched

Question: can the unconsumed candidate c32 arm complete without replaying the
measured stock terminal, component pair, or checkpoint staging?

Action: read the repair-2 binding and failure diagnostic once. The predecessor
PID `3109321` matched start ticks `135911495` and the original claim before it
was replaced. Hash-bound the repair packet in `ENDPOINT_REPAIR2_BINDING.json`,
then launched durable PID `3162265` / start ticks `136204677` before the
13:44Z fence. The only amendment catches a bounded health-curl timeout as an
unready poll and supports `endpoint_repair2`, which adopts stock and component
artifacts and reuses the already-live candidate server.

Evidence: the remote candidate container remained live and no prior candidate
science marker existed. The replacement has crossed its repaired boundary and
persisted `candidate-science-started.json`; therefore the one allowed
candidate submission is now in progress. No stock, component, checkpoint, or
candidate replay is authorized. The durable owner remains responsible for
terminal retrieval, endpoint-pair assembly, spend reconciliation, and release
by 14:25Z.

## 2026-07-28T13:41Z — endpoint terminal adopted

The candidate c32 submission completed: 32/32 requests passed, with raw
candidate service time `0.8379872799375221 s/request` versus preserved stock
`0.7010773845312315 s/request` (delta `+0.13690989540629062`). The candidate
terminal is retrieved and hash-bound as
`ENDPOINT_PAIR_TERMINAL.json` (`1c48455bd29364a480edde0251d44a32a0f2732feeaaddd548e679b7c15b04fb`).

However, its required global-KV telemetry had zero rows, no phases, and no
compact-entry observation. The request is consumed, but the raw slowdown
cannot be attributed to the claimed global-KV consumer path. The adopted
terminal is therefore typed
`typed_inconclusive_consumed_candidate_telemetry_missing`, not a mechanism
negative. The owner released the bench to maintenance after retrieval. The
conservative provider-lifecycle exposure through its 14:32:10Z watchdog is
`$6.15` at `$2.46/hour`, within the `$8.00` reservation.

## 2026-07-28T13:57Z — explicit activation repair failed fast

The director-admitted warm H200 claim began at 13:50:48Z. The only patch made
the candidate server explicitly import and install `global_kv_sglang_hook`
before running SGLang, and used a fresh `endpoint-artifacts-repair3` root.

Its real c1 probe completed one exact 4,214-token / 358-output request with
finite nonempty output, but persisted zero hook telemetry rows, no recognized
phase, and no compact-entry observation. The retrieved archive and raw worker
trace are bound in `INTERVENTION_NOT_ACTIVATED_REPAIR3.json`. Per the
admission, no corrected c32 candidate was submitted. The healthy candidate
server remains resident on port 30000 using 122430 MiB, and the bench was
released to maintenance for director disposition.

## 2026-07-28T14:16Z — repair-4 terminal adopted without replay

The archive-only adoption owner replaced PID `3183625/136340115` inside the
continuous claim, verified the compact archive hash, and reconstructed the
terminal without contacting the endpoint. The c1 activation proof is positive
(`6086` telemetry rows, compact entries `26`, fallback false); the candidate
c32 arm is consumed with all 32 request and 32 response files persisted.

The hook raised CUDA OOM at global layer 35 with only 2.31 MiB free, then the
server exited before metrics could be collected. Candidate latency is recorded
as unavailable, not inferred. This is a typed c32-memory infeasibility of the
exact endpoint implementation, not a global mechanism closure. The claim was
released to maintenance with the checkpoint/image retained and no server.
