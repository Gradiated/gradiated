# Research log

## 2026-07-17 — director admission

Activated after exact measured linears/head plus deterministic KV reads closed every BF16 point except c32. The primary is the actual pinned-image H200 attention consumer over exact hybrid contexts; the only retained arm is the actual non-GEMM residual stack behind a decision/start-ready trigger.

## 2026-07-17 — durable actual-attention owner launched

- Question: does the pinned-image c32 attention path, combined only with measured linears+head, close the remaining BF16 point?
- Action: the 12-check director identity assertion and final exact-image import/audit passed. The owner is a user-systemd service `gemma-h200-c32-attn-20260717t13071784286428z.service`, PID `2023647`, cgroup `/user.slice/user-0.slice/user@0.service/app.slice/gemma-h200-c32-attn-20260717t13071784286428z.service`; its typed pre-create gate passed and it created `computeinstance-e00eyyypp5a7s9fvtv` under the 30-minute/$1.2298611 bound.
- Evidence: `artifacts/final-staged-audit-20260717T130800Z.json`, `artifacts/gemma-h200-c32-attn-20260717t13071784286428z/PRECREATE_TERMINAL.json`, and `provider-request.json`. The exact immutable image exposes the pinned `flash_attn_varlen_func` consumer for sliding head-dim 256 and `unified_attention` Triton consumer for global head-dim 512.
- Interpretation: the owner is intentionally left running for its typed stage artifact and authenticated cleanup. Two earlier services failed before provider creation (missing artifact directory, then an overly strict local audit token); both gates were fail-closed and created no resource.
- Next move: deferred terminal reconciliation only; do not replace or restart this owner.

## 2026-07-17 — terminal reconciliation: invalid science, cleanup verified

- Action: reconciled only the durable owner's local typed terminal, retrieved archive, lifecycle events, cost summary, authenticated cleanup proof, and the independent behavioral audit. No owner/provider/CUDA mutation or repair was performed.
- Evidence: the primary emitted one sliding row and reported `0.002679253` useful GPU-seconds, then failed at the first global consumer invocation with `TypeError: 'int' object is not subscriptable`; zero global and residual rows completed. The independent audit had predicted this exact failure and separately proved the lone sliding row non-decision-bearing (non-paged K/V, no numerical oracle, trivial zero K/V), plus an invalid 358x global aggregation, broken economic flag, absent residual arm, and incomplete false-passing staged audit.
- Accounting: authenticated create-to-cleanup exposure was `573.717` seconds. Derived cost is `$0.390446108223` compute + `$0.001549385777` disk + `$0` other = `$0.391995494` (invoice pending), within the `$1.50` cap. Cleanup passed with zero final/matching instances and disks.
- Interpretation: all rows and timings are invalid for the campaign decision; make no c32 attention, residual, throughput, or economic inference. Close without retry or successor. Typed evidence: `artifacts/RECONCILED_TERMINAL.json`.
