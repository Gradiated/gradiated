# Research log

## 2026-07-15 — retained-evidence frontier bound and local contract audit

**Question.** Is there a cache-off fixed-workload concurrency point above V21 c8 that is resource- and SLO-admissible enough to justify a bounded paid measurement?

**Decision, hypothesis, and scope.** Test the project hypothesis that V21's residual c8 headroom can be exposed by raising sequence concurrency, with model, AWQ checkpoint, vLLM 0.15.0, BF16 activation dtype, 8,192-input/1,024-output geometry, seed, generation, and disabled prefix caching held fixed. This pass is the required low-fidelity gate: retained-artifact reconstruction plus local runner validation. No provider mutation or paid run was attempted because `CAMPAIGN_STATUS.json` currently sets `claims_permitted: false` and there is no active provider owner.

**What I did.**

- Read the project contract, lab campaign objective/status, V19/V21 summaries and preregistration, V21 internal archive, and the current remote launcher, batch runner, and retained-instance recovery code.
- Extracted the authoritative V21 server log evidence: vLLM 0.15.0 ran chunked prefill with `max_num_batched_tokens=65536`, `max_num_seqs=8`, 16.82 GiB available KV cache, and 333,488 KV-cache tokens.
- Recomputed fixed-request live-token envelopes (`8192 + 1024` per request), the c8-to-strong-gate throughput gap, and a deliberately conservative prefill-wave TTFT proxy.
- Validated the unmodified local scripts with `python3 -m py_compile` and the runner's `--help` interface. The checks passed, but they also demonstrate that the present runner/launcher/recovery path cannot produce c16: all retain or hard-code the sequence limit/profile geometry at c8.
- Wrote the reproducible derived evidence artifact [FRONTIER_BOUND_V1.json](FRONTIER_BOUND_V1.json).

**Measured evidence.**

- V21 c8 was valid: 355.772 output tok/s, $0.6700/M output tokens, p95 TTFT 4.951 s, p95 TPOT 18.789 ms, exact geometry/success/SLO/prefix-cache checks all passed. It improved V19 c8 by 3.36% while removing V19's 0.595 s mean queue time.
- The V21 archive contains raw c1/c8 request rows, metrics deltas, telemetry, semantic/quality evidence, model identity, server command, and manifest. Whole-session telemetry (not c8-isolated) has 410 samples, 35.471% mean GPU utilization, 129.168 W mean power, and 332.78 W peak power.
- The fixed live-token upper bounds are 147,456 at c16 and 294,912 at c32. Both are below 333,488 KV tokens, but c32 leaves only 38,576 tokens / 11.57% capacity headroom before reserve or fragmentation.

**Derived result and interpretation.**

- c16 is the sole admitted next measurement. With the unchanged 65,536-token batch budget, its two prompt-budget waves yield a 9.903 s TTFT proxy from V21's c8 p95—only 97 ms below the SLO. This is not a claim that c16 will pass; chunked-prefill interleaving and decode contention remain unmeasured falsifiers.
- c32 is not admitted under the unchanged scheduler budget. Its four-wave proxy is 19.806 s, far above the 10 s TTFT ceiling, and its KV margin is thin.
- The strong $0.60/M condition needs 397.279 output tok/s, 11.667% above V21 c8. A 16-request arm must finish in at most 41.241 s to reach it; if TTFT consumed its full 10 s SLO allowance, the implied TPOT budget is only 30.538 ms. Therefore a merely SLO-passing c16 result is not sufficient to promote it.

**Failure / readiness result.** The existing campaign execution contract is not c16-capable: the remote server fixes `--max-num-seqs 8`, `vllm_batched_runner.py` measures only c1/c8, and `vllm_recover_existing.py` cannot propagate a sequence limit. The retained V21 artifact also lacks a c16 profile and explicit scheduler iteration-state contract. This is a local reproducible readiness failure, not evidence against c16 performance.

**Next best action.** When campaign dispatch is re-authorized, implement and locally test one arm-scoped `max_num_seqs` parameter through launcher, retained-server recovery, and profile configuration. Preregister and run a single retained-session ladder of c1, adjacent c8 control, and c16 with the 65,536-token scheduler budget unchanged. Require the expanded artifact contract enumerated in `FRONTIER_BOUND_V1.json`; reject c16 on OOM, geometry/semantic/quality/SLO failure, or less than 5% c8 improvement, and do not run c32 in that first session.

## 2026-07-15 — c16 execution contract and bounded live frontier session

**Question.** Can a one-session c1/c8/c16 cache-off ladder measure the admitted c16 point without changing the V21 scheduler budget, model/runtime identity, quality gate, or workload?

**Implementation and local experiment.** I added a fail-closed `max_num_seqs` and frontier-concurrency contract to the vLLM launcher, primary controller, retained-instance recovery controller, and batch runner. The only accepted profile sets are `(1,8)` and `(1,8,16)`; c16 requires `max_num_seqs >= 16`. The runner keeps four c1 requests and two full batches at each higher concurrency (16 requests at c8 and 32 at c16), retains raw per-request profiles and metrics deltas, and reports the terminal profile as the economic point. The remote allocation result now records the sequence limit and frontier tuple. The c16-specific changes are covered by two new behavior tests; the focused suite ran 30 tests successfully, Python compilation and all three CLI parsers passed, and an explicit c16-under-c8-capacity attempt failed closed.

**Preregistration and paid-session contract.** [V31 preregistration](../../../campaign_100/allocations/nebius_l40s_vllm_awq_frontier_c16_v31/preregistration.json) fixes BF16/AWQ/vLLM 0.15.0, 65,536 batched tokens, disabled prefix caching, `(1,8,16)`, and a 3,600-second maximum allocation exposure ($0.8581222 maximum VM-plus-disk cost, below the $1.50 project cap). It retains V21's model manifest and quality suite identities, prohibits c32 and all unrelated mechanism changes, and includes source hashes and the 5% / strong-gate thresholds.

**Provider reconciliation and live state.** Before creation, authenticated Nebius inventory returned zero instances and zero disks. The local AWQ cache passed `validate_local_model` with V21's revision, four shards, 20,170,199,928 weight bytes, and manifest hash. The primary V31 coordinator created one named L40S instance and absolute cleanup watchdog. CUDA/Transformers preflight and tiny-transfer integrity probe passed. The verified checkpoint transfer is active; latest direct remote observation was 6.3 GiB staged in `/workspace/model-awq`.

**Operational incident.** The local execution wrapper returned before the primary coordinator exited, which initially looked like a harness stop. I started the existing recovery path, then discovered the primary was still active; its concurrent input transfer failed and opened its repair window. I killed only that redundant recovery process without running its cleanup handler, preserving the primary process and watchdog. Its `repair_01_*` events remain in the V31 event log as an operational artifact; they are not scientific evidence. The primary then recorded SSH readiness, runtime preflight, and transfer-probe success. No c1/c8/c16 performance or quality result exists yet.

**Current decision and next action.** Keep this project active. Do not create another allocation or intervene concurrently. Wait for the primary controller to retrieve and verify the archive, then inspect `summary.json`, raw c16 profile/metrics/KV/server evidence, and cleanup state. If it times out or fails, preserve the partial artifact and classify the failure before selecting any next lineage.

## 2026-07-15 — V31 primary-loss audit and bounded recovery

**Question.** Can the existing V31 allocation still yield an admissible measurement after its primary coordinator disappears, without creating resources or extending the original deadline?

**Audit.** The primary process was absent while its watchdog remained active. Its partial artifact contains only bootstrap logs and events; there is no archive, summary, or request-level performance/quality evidence. The original staged checkpoint was incomplete (10.76 GB total, first shard only 2.98 MB, checksum failure), so reuse was rejected. The runtime bootstrap itself was valid: it built the pinned runtime, passed CUDA/vLLM/Transformers preflight, and the authenticated provider inventory still contained exactly V31's instance and boot disk.

**Action.** Started exactly one `vllm_recover_existing.py` recovery against `computeinstance-e00zhxe3m62va05fd9`, using the same V31 preregistration hash, 65,536-token budget, `max_num_seqs=16`, `(1,8,16)` ladder, and the original `2026-07-15T08:34:40Z` watchdog deadline. It does not reuse the failed partial checkpoint. Recovery runtime preflight, frozen-input staging, and tiny-transfer probe passed; the clean checkpoint retransfer is active (5.3 GiB at the last observation). No second allocation or configuration change was made.

**Interpretation.** The primary loss is operational evidence only. The c16 hypothesis remains untested. The recovery is the sole remaining admissible route for V31; if it cannot produce a complete verified archive before the watchdog, classify V31 as an operational failure and verify zero inventory rather than retrying.

## 2026-07-15 — V31 terminal cleanup and result classification

**Terminal result.** V31 is an operational failure with no scientific result. Both turn-scoped controllers disappeared before server launch, request execution, artifact retrieval, or summary creation. The primary staged an incomplete checkpoint; the recovery re-established runtime/input preflights but also disappeared before producing a performance archive.

**Measured terminal evidence.** Immediately before cleanup, remote `nvidia-smi` reported 0% GPU utilization, 0 MiB used, and 98.24 W power; no vLLM or runner process was present. Existing artifacts contain bootstrap/preflight and transfer-probe evidence only. They contain no c1/c8/c16 rows, scheduler/KV performance data, semantic/quality result, or valid archive. I used only the existing provider-control cleanup functions, then verified zero Nebius instances and zero disks and no remaining local V31 controller/watchdog processes.

**Accounting and claim limit.** Exposure from the recorded allocation start through cleanup verification was 2,146.089 seconds, or $0.511557399 derived at the frozen $0.8581222/hour VM-plus-disk rate (public IPv4/egress/invoice reconciliation excluded). This cost buys no performance or economics claim. The full terminal contract is [OPERATIONAL_FAILURE.json](../../../campaign_100/allocations/nebius_l40s_vllm_awq_frontier_c16_v31/OPERATIONAL_FAILURE.json).

**Decision.** Release V31 provider ownership and pause this project. The c16 hypothesis remains untested—not rejected—and any future attempt must first demonstrate a durable controller outside the Codex turn/process group that owns setup, transfer, execution, retrieval, and cleanup through a terminal artifact.

## 2026-07-15 — V32 retained-controller frontier attempt: artifact-contract failure

**Question.** Can the reauthorized sole-owner V32 controller produce the fixed cache-off c1/c8/c16 background frontier on one L40S under the unchanged 65,536-token scheduler budget?

**Action and evidence.** Started exactly one fresh Nebius L40S controller with the frozen V31 workload/spec identity, `max_num_seqs=16`, frontier `(1,8,16)`, and the existing watchdog. Empty inventory, SSH readiness (79.823 s), CUDA/Transformers preflight, tiny-transfer probe, and verified AWQ transfer (20.17 GB in 411.764 s) passed. The remote runner exited and returned a hash-valid 9,072-byte archive, but validation failed closed because it contained no `allocation-result.json`, request rows, performance summaries, quality result, or server command. Its phase trace ended at `model_identity: begin`; no c1/c8/c16 arm began. GPU was idle and no vLLM process remained.

**Decision and accounting.** Classify V32 as an operational observability failure, not a c16 performance or economics result. Supported teardown produced `cleanup_pass=true`, zero final instances/disks, and no remaining controller/watchdog. Derived exposure was 1,266.862 s and $0.301978509 at the frozen VM-plus-disk rate. No throughput, SLO, cost-per-token, quality, or batching-frontier claim is admissible.

**Next move.** Do not retry unchanged. Repair and locally test the remote artifact producer/packager so `allocation-result.json` plus exact c1/c8/c16 request, metrics, server, and quality files are emitted before archive retrieval; then require a fresh dispatch decision. The batching hypothesis remains open and untested.
