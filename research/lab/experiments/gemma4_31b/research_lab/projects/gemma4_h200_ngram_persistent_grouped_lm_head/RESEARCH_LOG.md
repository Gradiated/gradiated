# Research log

## 2026-07-25T17:04:00Z — offline grouped LM-head implementation

- **Question:** Can one production-shaped launch preserve 12 independent M=32 target-decision domains while reducing repeated tied-weight traffic?
- **Action:** Verified `DIRECTOR_BINDING.json` and every bound digest; materialized the admitted source, trace, checkpoint manifest, runner, model index, and consumer bytes under `inputs/bound/`. Traced the pinned `LogitsProcessor._get_logits` BF16 `torch.matmul` path, built `grouped_lm_head.py`, and built `exact_consumer_component.py` to consume candidate outputs through the pinned SGLang processor, top-two/argmax comparison, accepted-prefix oracle, replay check, warm distributions, and launch telemetry. Added the bounded NCU counter probe, resumable qualified-control/grouped-candidate c32 pair, remote experiment, and shared-`detached-owner` controller with claim heartbeat, immutable hardlink staging, repair handshake, compact-first retrieval, spend settlement, and release. Compiled the exact shape for SM90 in the pinned image without a GPU.
- **Evidence:** Measured baseline attribution is 180 M=32 GEMMs / 15 steps / 124.664394 ms, or 8.310960 ms per step and 5.2487% of the profile window. The 2.818572 GB BF16 tied weight implies 34.028323 GB sequential compulsory bytes and a 7.089234 ms H200 HBM floor per step. The depth-interleaved launch keeps a separate `[32,256]` FP32 accumulator per depth and orders the 12 programs for each vocabulary tile consecutively; its predicted discriminator is lower DRAM reads through L2 reuse without folding depth into native M=384. Triton 3.6.0 compiled it for SM90 with 8 warps, 3 stages, and 36 KiB shared memory. See `OFFLINE_CAUSAL_MODEL.json` and `artifacts/SM90_COMPILE_RESULT.json`.
- **Interpretation:** The mechanism is physically credible and has a maximum measured-window bound of 5.2487%, but compilation is not a CUDA sample. Exact target decisions, registers, DRAM reads, and warm latency remain unmeasured.
- **Next:** Priority 8490 still owns and heartbeats `h200-dflash-adapter-e00vyqp7gxsr34wrtz` under a repair handshake. Do not claim. After its mixed-local terminal and release, review supersession and lifecycle gates, hardlink/hash the immutable resident checkpoint into this project, then run the exact component and only conditionally the matched c32 endpoint pair.

## 2026-07-25T17:21:24Z — queue-boundary observation

- **Question:** Is the admitted H200 available for the grouped LM-head CUDA falsifier?
- **Action:** Read the current pool record, priority-8490 status, durable-owner state, and required predecessor terminal; checked the project gate and the shared H200 experimental rate.
- **Evidence:** `h200-dflash-adapter-e00vyqp7gxsr34wrtz` remains claimed by `gemma4_h200_ngram_fixed_m384_executor_rewrite`, with a fresh heartbeat at `17:21:22Z`, a live controller (`pid 915680`), and lease through `19:21:22Z`. `MIXED_LOCAL_M384_TERMINAL.json` is absent. The H200 lifecycle remains to `22:00Z`; the exact `$5` reservation is the gate's required ledger entry and the actual experimental rate is `$2.45/GPU-hour`.
- **Interpretation:** This is a typed shared-queue boundary, not a scientific or readiness result. Claiming now would violate the director's serial order and fail the project's preflight before any GPU work.
- **Next:** Wait for the durable predecessor terminal and release, then re-run the already implemented atomic gate/owner path; it will reject supersession, a missing exact reservation, or less than 60 minutes of lifecycle before claiming.

## 2026-07-25T17:40:53Z — two-predecessor queue amendment

- **Question:** Does the new DFlash cycle-oracle dependency alter the admissible H200 launch path?
- **Action:** Read the new priority-8600 project state and its required terminal, then amended the project-local durable owner to require both predecessor terminals before it can atomically claim.
- **Evidence:** Priority 8490 still holds the H200 with a fresh `17:40:53Z` heartbeat. `MIXED_LOCAL_M384_TERMINAL.json` and `gemma4_h200_dflash_endpoint/DFLASH_CYCLE_ORACLE_TERMINAL.json` are both absent; the exact `$5` reservation remains durable. The amended owner now hash-records both terminals only after checking each for mechanism supersession and target-reaching service time, then requires an unclaimed available bench and at least 60 lifecycle minutes.
- **Interpretation:** The added dependency is a queue constraint, not evidence against grouped LM-head reuse. The gate amendment prevents a stale one-predecessor owner from racing priority 8600.
- **Next:** Wait for both durable terminals and releases, then run the corrected detached owner directly into hardlink staging, the component consumer, and its conditional endpoint pair.

## 2026-07-25T18:02:14Z — mixed-M384 resolution and hybrid itinerary amendment

- **Question:** Does the mixed-M384 terminal close grouped LM-head reuse, and what queue contract now applies?
- **Action:** Read the durable mixed-M384 terminal, current DFlash claim, and the director-bound hybrid component contract; amended the grouped-head owner to retire the resolved priority-8490 prerequisite and require DFlash plus the hybrid terminal or its durable claim-time bypass.
- **Evidence:** Mixed M8 was a semantic negative for that attention realization: its local component was positive but the completed 32/32 target-decision guard diverged, and the endpoint pair was skipped. The terminal does not supersede grouped LM-head reuse. Priority 8600 now owns the H200. The optional quality-unsafe hybrid component is explicitly sequenced after DFlash and must either terminalize or write a typed claim-time bypass before this project may claim.
- **Interpretation:** Grouped LM-head remains an independent, unconsumed mechanism. Its owner now reflects the director's DFlash-then-hybrid itinerary and cannot race a closed or executed hybrid continuation.
- **Next:** After DFlash and hybrid have durably resolved and released, the owner will verify the reservation/lifecycle gates, claim once, hardlink the resident checkpoint bytes, and run the exact component before any conditional c32 pair.

## 2026-07-25T19:19:37Z — DFlash/hybrid prerequisite reconciliation

- **Question:** Are the two named successors now resolved enough to run grouped LM-head?
- **Action:** Read `DFLASH_CYCLE_ORACLE_TERMINAL.json`, `HYBRID_55L5G_H200_COMPONENT_TERMINAL.json`, and the current H200 inventory once; no claim, SSH, or lifecycle action was taken.
- **Evidence:** DFlash evaluated 112 cycles with `pass: true` and no first divergence. Hybrid terminalized `unrun_claim_gate_closed` with `science_consumed: false` and `$0.00` spend. The H200 inventory still records a DFlash claim; the director separately binds that claim to the live authorized c32 depth measurement.
- **Interpretation:** Both prerequisite artifacts are durable, and hybrid cannot consume the bench. The remaining boundary is the protected active DFlash c32 owner, not a scientific negative, missing artifact, or budget deficiency. Grouped LM-head remains unconsumed at `$0.00` actual spend.
- **Next:** Do not touch the DFlash owner. On its release, run the existing atomic gate; only then stage the exact checkpoint and execute the component, followed by the conditional single c32 pair.

## 2026-07-25T19:53:27Z — offline live-contract localization and repair

- **Question:** Which first live-call field converts the bit-exact eager component into collapsed endpoint acceptance?
- **Action:** Consumed only the bound terminal and immutable grouped-LM-head artifact. Traced target-verify dispatch, graph capture, logits-buffer handling, row/depth reconstruction, softcap, endpoint telemetry, and trace validity. Added a fail-closed activation contract plus an executable exact-shape offline fixture; no GPU, endpoint, provider, DFlash, or spend action occurred.
- **Evidence:** The component used an eager call with `next_token_logits_buffer=None`; the candidate endpoint captured bs=32, whose target shape is `[384,5376]`, into a CUDA graph while the old gate ignored capture and buffer ownership. Acceptance was `0.00454545` versus `0.7835845`, and the later candidate log showed a `10.09/0.83` interval after the active batch fell below the exact-shape grouped gate. The claimed exact SSE IDs are vacuous: all 32 token-ID arrays per arm are empty, while the cumulative scheduler/emitted trace differs. `artifacts/GROUPED_LM_HEAD_LIVE_CONTRACT_FIXTURE.json` passes all eight checks and invokes the production dispatcher to prove its stock fallback, depth calls `0..11`, rows `[d,d+12,...,d+372]`, request-major reconstruction, and float-buffer identity/contents.
- **Interpretation:** The first localized divergence is candidate activation across the CUDA-graph/live-buffer boundary, before softcap, top-k, or accepted-prefix commit. The artifact cannot separate graph-lifetime aliasing from a graph-only kernel mismatch because it captured no live logits, strides, addresses, ownership map, or commit trace. `grouped_lm_head.py` now routes captured or buffered calls through the qualified stock-ordered 12-slice path and retains grouped execution only for the already measured eager, buffer-free contract.
- **Next:** This offline action is terminal in `GROUPED_LM_HEAD_ACCEPTANCE_DIVERGENCE_TERMINAL.json`. A later director may own a repaired GPU discriminator; the repair itself has no endpoint correctness or speed claim.

## 2026-07-25T20:24:00Z — graph-safe buffer-direct source terminal

- **Question:** Can the measured grouped projection enter the captured target-verify path without replacing or copying the live logits buffer?
- **Action:** Starting from the content-addressed localization terminal and fail-closed source, added `grouped_lm_head_into` and `grouped_get_logits_buffer_direct`. The Triton projection now writes BF16-rounded values directly into the exact preallocated FP32 buffer and applies the unchanged fused softcap in place. The gate admits only exact TP1/DP1, null-scale, contiguous CUDA inputs and a `[384,262144]` FP32 buffer with stride `[262144,1]`; every unsupported field retains stock fallback. Replaced the fallback-only fixture with a deterministic candidate-path fixture and added the later exact H200 CUDA-graph discriminator.
- **Evidence:** The synthetic source-execution fixture marks capture active, supplies the live buffer, invokes the buffer-direct branch once, invokes stock zero times, and passes 14/14 checks for object/pointer/dtype/shape/stride/lifetime, request-major depth ownership, logical depth order, BF16-to-FP32 boundary, in-place softcap, target IDs, and accepted prefixes. Derived per verification step: projection launches `12 -> 1`, softcap launches `12 -> 1`, the previous grouped buffer copy `1 -> 0`, and 402,653,184 output-boundary bytes are removed. The buffer epilogue does not change the grouped weight-reuse hypothesis: exact logical stock reads are 33,822,867,456 bytes, with a 2,818,572,288-byte compulsory grouped lower bound.
- **Interpretation:** This is a source-complete graph-replay candidate and exact offline contract result, not CUDA evidence. The first irreducible field is actual SM90 capture/replay of the BF16-rounded store into the persistent FP32 buffer.
- **Next:** `GROUPED_LM_HEAD_GRAPH_SAFE_BUFFER_TERMINAL.json` binds all sources and predictions. Only after new director authorization, content-address the exact weight under this project and run `graph_safe_buffer_discriminator.py` once; do not replay either historical endpoint arm.

## 2026-07-25T20:44:58Z — invalid pre-science materialization attempt

- **Question:** Can the bound resident tied-weight shard be materialized under this project before the one graph-safe CUDA replay?
- **Action:** Atomically claimed the named H200 and started the hash-bound durable owner. Source staging completed, but the first project-local hardlink failed before the container or discriminator was invoked.
- **Evidence:** The remote diagnostic records `Operation not permitted` from a non-privileged `ln`; `INVOCATION_STATE.json` is absent, so no candidate CUDA or scientific invocation began. The metered claim exposure is `$0.00263738` at the registered `$2.45/hour` rate. The attempt artifact is `artifacts/graph-safe-buffer-h200-20260725t204455z/`.
- **Interpretation:** This is an ordinary pre-science staging defect, not a measurement or mechanism result. The owner has been amended to use the same privileged immutable-hardlink procedure already used by the retained bench's predecessor.
- **Next:** Return the mistakenly maintenance-marked, otherwise healthy bench to ready and continue the still-unconsumed single bound replay under the corrected durable owner. No endpoint arm is authorized.
