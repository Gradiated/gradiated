# Research log

## 2026-07-18 — exact c64 runner prepared offline

Question: can the bound SGLang v0.5.12 Gemma 4 H200 resident state improve the valid c32 comparator at c64, with c96 admitted only after a typed >=5% c64 improvement and safe memory telemetry?

Action: inspected the bound bindings and the validated deterministic trace contract. Implemented `c64_frontier_runner.py` and `ARTIFACT_CONTRACT.json`. The runner uses the validated `primary_c16.scored` request bodies repeated in order to form c64, adds the known repaired-consumer `stream:false` field, synchronously persists request/response bytes, snapshots `/metrics`, samples `nvidia-smi`, and writes an atomic per-stage terminal before any conditional arm. It admits c96 only on valid c64 plus >=5% improvement; c48 remains the single typed-capacity fallback contract.

Evidence: offline trace terminal `../gemma_exact_cache_trace_contract/TRACE_TERMINAL.json` passes with trace hash `ccc559094ee612d5da11e771c2ebf8ac14046ad03b8ec7bd6ae165be25725d68`; c32 comparator is `0.3633031778124973 s/request`. Current quality owner status has no paired-quality terminal and the only H200 bench is claimed by that owner, so no claim or GPU execution was authorized this turn. No provider mutation or spend occurred.

Interpretation: the execution path is prepared but not scientifically run. The next admissible move is a typed paired-quality pass, then an atomic claim of a released identity-compatible H200 bench followed by c64.

Audit: `python3 -m py_compile c64_frontier_runner.py` passed. The existing trace validator passed all checks and reproduced the bound trace hash. No durable process was started, no GPU claim was attempted, and no provider resource or quality-owner state was mutated.

## 2026-07-18 — quality-gate dependency remains active

The required one-time dependency check found `sglang_v0512_h200_stock_quality_validation` still active with no paired-quality terminal. Its typed next action is to retain the claimed H200 and repair an HTTP 400 at the BF16 `/v1/chat/completions` control capture before any quality inference. The pool shows the only compatible H200 still claimed by that owner, not released. This is an in-scope external blocker for c64 execution; no claim, provider mutation, spend, or bench disturbance was performed.
