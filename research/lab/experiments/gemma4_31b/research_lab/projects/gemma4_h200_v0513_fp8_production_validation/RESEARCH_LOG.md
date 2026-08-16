# Research log

## 2026-07-20 — public quality assets content-bound offline

Question: can the exact v0.5.13 FP8 production-validation project enter its paired quality capture with public GPQA-Diamond and TauBench inputs bound locally while QKV uses the warm H200?

Action: materialized the public GPQA-Diamond CSV from the OpenAI simple-evals public endpoint and the pinned Sierra tau-bench source/data at commit `59a200c6d575d595120f1cb70fea53cef0632f6b`. `bind_assets.py` parses only the downloaded bytes, emits deterministic request JSONL, and records SHA-256 identities for every source and request file.

Evidence: `artifacts/offline-bind-20260720/OFFLINE_BINDING_TERMINAL.json` passes with 198 GPQA-Diamond requests, 50 airline TauBench tasks, and 115 retail TauBench tasks. The binding manifest records the exact model revision, v0.5.13 paired arms, `/v1/chat/completions` path, tool-path requirement, seed, FP8/BF16 weight modes, and FP8-E5M2 KV. Scientific invocation and provider spend are both zero.

Interpretation: the quality assets are ready for the retained same-runtime paired capture. This is offline preparation, not a quality result; no output, score, or production conclusion is inferred.

Next move: wait for `gemma4_h200_qkv_epilogue_fusion` to emit its final typed terminal and ready-release the retained H200, then claim that bench and run the exact BF16 control followed by dynamic-FP8 candidate through the compact feature/NLL gate and directly into these paired GPQA-Diamond/TauBench requests.

## 2026-07-20 — production-quality owner reached typed retrieval boundary

Question/action: execute the admitted v0.5.13 BF16/FP8 quality comparison under one durable owner.

Evidence: the first owner claimed and released after a pre-capture input-path defect; its traceback proves no server or scientific invocation began. The bounded repair owner then claimed the H200, staged the corrected worker, and returned SSH code 255 during post-worker retrieval. The provider lookup subsequently returned no instance/public IP, and one direct SSH retrieval to the last observed endpoint returned empty stdout/stderr. No `INVOCATION_STATE.json`, compact worker terminal, raw capture, or tool trace was retrievable.

Decision: typed `unreachable_guest_retrieval_failure`, not a scientific pass/fail. Arm consumption is unknown and no replay is authorized. The bench was released to `maintenance` with [RETRIEVAL_TERMINAL.json](artifacts/production-quality-repair-20260720t0329z/RETRIEVAL_TERMINAL.json); cumulative project exposure is conservatively `$0.02727`. Director inspection/reconciliation is required before any further claim.

## 2026-07-20 — QKV terminal-and-release dependency remains unmet

Action/evidence: reconciled the named QKV project once after the watchdog extension. Its status remains `active` with `terminal: null` and a next action to run the v0.5.13 FP8+QKV endpoint stack. The pool reports the H200 `available`, but the only newly discovered `fp8-qkv-stack-20260720t0140z` directory has bench metadata and empty worker stdout/stderr, not a typed scientific terminal or release record.

Decision: typed external dependency boundary `typed_external_dependency_not_released`. This project did not claim the bench, invoke CUDA, or spend provider budget. Preserve the bound assets and wait for QKV's terminal plus ready release; do not infer completion from pool availability.

## 2026-07-20T02:49:12Z — dependency still pending

Reconciled QKV and the pool once under the unchanged scheduler decision. QKV remains `active` with no terminal or active session; the H200 is `available` with no claim. The offline binder remains reproducible at the existing terminal hash and all 198 GPQA-Diamond/165 TauBench counts. Decision remains `typed_external_dependency_not_released`; no claim, CUDA invocation, or spend occurred in this project.

## 2026-07-20T02:58:56Z — QKV outer still missing

The required dependency check found QKV still `active` with `terminal: null`; its next action is explicitly to implement the missing v0.5.13 stack outer and repair the stale v0.5.12 worker binding. The H200 is available but unclaimed. This project’s offline binding reruns unchanged with 198 GPQA-Diamond and 165 TauBench requests. Decision remains `typed_external_dependency_not_released`; no GPU claim or scientific invocation is authorized in this project until QKV emits its typed terminal and releases the bench.

## 2026-07-20 — fresh production-quality recovery completed with failed tool gate

Question/action: execute the fresh content-bound replacement-bench run `v0513-fp8-quality-recovery-20260720t0340z`, with BF16 first and dynamic-FP8 second through the real text/tool path.

Evidence: the durable owner cold-staged and hash-verified the exact eight-file checkpoint and pinned v0.5.13 image. BF16 completed all 3 feature, 439-token NLL, 198 GPQA-Diamond, and 165 TauBench captures before an ordinary scorer defect (`tool_calls: null`) stopped postprocessing; the persisted control captures were preserved. A null-safe scorer repair reconstructed BF16 and ran the unconsumed FP8 arm without replay. The final terminal is [TERMINAL.json](artifacts/v0513-fp8-quality-recovery-repair-20260720t0425z/TERMINAL.json), hash `64c161451ec8d1b60d7476f890d7f30be7f359ae6eeeb6f1c7474689ab7a614c`; both invocation markers are true and all raw captures/tool traces are local.

Result: both arms failed the preregistered feature/tool gate because the runtime returned textual JSON (`[{"name":"lookup_user",...}]`) in message content instead of structured `tool_calls`. BF16/FP8 NLL means were `0.5379274`/`0.5350131` (delta `-0.0029143`), GPQA accuracies `26.26%`/`25.76%`, and TauBench success `5.45%`/`5.45%`. The terminal therefore fails quality admission despite the negative NLL delta. Total new replacement exposure was approximately `$1.72663` (initial owner `$1.44444` plus repair owner `$0.28219`); the vanished guest remains unknown and excluded.

Decision: close this project as a measured quality-gate failure. Do not replay either scientific arm, infer structured tool behavior from textual output, or merge the vanished guest. QKV and MTP remain excluded.

## 2026-07-20 — native Gemma 4 tool consumer repaired and TauBench rescored

Question/action: repair the shared tool consumer without regenerating the already-bound GPQA, TauBench, or NLL requests. Inspect the exact v0.5.13 image and checkpoint schema, then run fresh BF16/FP8 single- and multi-tool sentinels.

Evidence: the checkpoint schema binds Gemma grammar `<|tool_call>call:<name>{...}<tool_call|>`, and the exact image exposes `--tool-call-parser ... gemma4`; the server auto-detected `tool_call_parser='gemma4'`. After two ordinary pre-sentinel owner defects were repaired (proxy lifecycle, then missing FP8 audit environment), the final owner ran both arms with native `--tool-call-parser gemma4`. Each arm passed exact single- and multi-tool names/arguments, `finish_reason: tool_calls`, nonnegative integer usage fields, null content, and identical parser bytes `45ab8607bb7bc3ace674efb229720a112125107f6c870f789e34684f01025e9b`.

Result: the existing hash-bound 165-row raw files were verified unchanged and normalized through the same parser bytes; no benchmark or NLL request was regenerated. Prefix-action scorer results are BF16 `36/165 = 21.82%` and FP8 `32/165 = 19.39%`; paired FP8-minus-BF16 difference is `-2.42` percentage points with deterministic 10,000-replicate 95% bootstrap CI `[-6.06, +0.61]` points. Raw hashes are BF16 `86a04466f9864ebfd5ee9415378c106a0a73f282ffaaaab1da087f5fb335cd30` and FP8 `68b41767219fc44fa29907c64f9ee07a5611b450d8104b9609fe622b1b281341`.

Decision: the shared structured-tool consumer boundary passes for both representations; TauBench remains low and the interval includes zero, so there is no statistically credible material FP8 regression from this consumer repair. Final artifact: [FINAL_TERMINAL.json](artifacts/tool-bridge-20260720t0458z/FINAL_TERMINAL.json), hash `7d9f6a1a8e376489e30cd67dacf753aa8574bc8348a140341b3439b7ee8b5430`. Total cumulative project provider spend is `$2.14666`, below the `$7` ceiling. No further GPU work is admitted.
