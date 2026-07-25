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
