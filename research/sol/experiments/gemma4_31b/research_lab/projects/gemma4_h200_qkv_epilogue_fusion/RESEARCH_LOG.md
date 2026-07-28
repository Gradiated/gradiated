# Research log

## 2026-07-19 — activated

The reopened kernel phase requires a distinct hot-kernel test alongside the direct endpoint. Prior stock fused QK normalization/RoPE already improved the canonical comparator by only `0.011981051969165213` seconds/request, so this project admits one custom QKV projection epilogue that must remove intermediate traffic and launches. Prepare offline during H200 bootstrap; claim the retained bench only after the direct FP8 owner releases it.

## 2026-07-19 — content-bound epilogue and offline oracle ready

Question: can one exact-shape post-projection launch replace pinned SGLang's token-granular Q/K/V RMSNorm launch plus its token-granular RoPE launch and clear `0.04597286970625021` seconds/request?

Action: traced SGLang v0.5.12 commit `127b9e3` through `Gemma4Attention`, `gemma_qkv_rmsnorm`, and `RotaryEmbedding.forward_cuda`; implemented `qkv_epilogue_discriminator.py` SHA-256 `7416b0bd31ffa9cdc5a474a07834eca37600ca7409baa11554895acc28d7fc81`. One head-granular Triton grid handles local Q32/KV16/D256 full RoPE and global Q32/KV4/D512 25%-active Gemma cross-mixed RoPE in place. It records actual compiled registers/shared memory/spills and an analytical active-block occupancy estimate on H200. The exact stock symbols remain the control. `remote_component.sh` requires the already-resident pinned image and never pulls or provisions it.

Evidence: `artifacts/offline-prep-20260719t2237z/OFFLINE_ORACLE.json` SHA-256 `72b75a74211a484dbc69a02849fe2356527255f162ec4d758dce024cfd6e5deb` passes both independent float-formula oracles, exact geometry/evidence hashes, all six pinned source hashes, and the one-launch/no-allocation source audit. This is preparation, not target execution. Analytical traffic accounting removes `412,625,141,760` intermediate bytes and `24,840` launches per frozen batch. At 1.0–4.8 TB/s, traffic alone is only `0.012895`–`0.002686` seconds/request, so promotion also requires about `42.6`–`55.8` microseconds of occupancy/launch recovery per eliminated launch. This causal claim is analytical; H200 timing is unmeasured.

Interpretation and next move: the mechanism is plausible only if replacing 32 token CTAs with 1,280–2,048 head CTAs materially repairs decode occupancy. The director has marked bench `h200-kernel-frontier-e00pfvrckjvwn7bhet` available, but primary project `gemma4_h200_inmemory_fp8_endpoint` is still active and has not released it. Do not claim or poll it. After that terminal/release, transfer the immutable project-local manifest bytes, use the first tiny real call as the compile/runtime check, repair only ordinary wiring in the retained claim, then complete the one stock-versus-custom discriminator and conditionally one BF16 c32 endpoint.

## 2026-07-19 — execution controller complete; primary lane still owns readiness

Question: has the FP8 terminal/release gate cleared, and can this lane run through component and conditional endpoint without another setup return?

Action: checked the named primary project once. It remains `active` at priority 700 after a pre-SSH wiring failure; its repaired schedule has made no CUDA call and is explicitly next to claim the available bench. Added bounded `run_outer.py` SHA-256 `f5073c6c...906c4`: one claim, 45-second heartbeats, project-local hash transfer, compact component retrieval before the conditional stage, same-claim repair windows, final archive retrieval, spend accounting, resident-state update, and release. Materialized the exact runner bytes under this project at SHA-256 `143709fd...d184d7`. Added an exact pinned-source integration patch and conditional BF16 endpoint worker; the endpoint is unreachable unless the persisted component gate passes, and it audits both `(Q32,KV16,D256)` and `(Q32,KV4,D512)` candidate calls.

Evidence: regenerated `artifacts/offline-prep-20260719t2237z/INPUT_MANIFEST.json` SHA-256 `e93bc497...90618` over all seven execution inputs; offline preparation still passes at SHA-256 `1c68d1ff...ad78a`. The endpoint patch applies uniquely to pinned `gemma4_causal.py` SHA-256 `683895c5...85856` and the patched file compiles. A behavioral controller preflight exited before artifact creation with typed boundary `primary_fp8_project_still_active`, proving the priority guard does not claim the available-but-reserved bench. No SSH, GPU, provider, or bench mutation occurred; project spend remains `$0`.

Interpretation and next move: this is a typed cross-project scheduling boundary, not a scientific result. Do not claim while the repaired FP8 arm is active. On its terminal and release, invoke the bound outer once and continue through the component result; only a passing `0.045972869706` seconds/request component may start the one BF16 c32 consumer.

## 2026-07-20 — checkpoint-repair priority still fences QKV execution

Question: did the named FP8 project emit its scientific terminal and release the retained H200 for the content-bound QKV outer?

Evidence: one grouped reconciliation at `2026-07-19T23:04:04Z` found the FP8 project still `active` at priority 700 with `terminal: null`. Its admitted next action preserves six matched metadata files and the complete second checkpoint shard, replaces only the `38,906,880`-byte partial first shard, verifies all eight hashes, and resumes the same unconsumed FP8 schedule. The pool reports the H200 as unclaimed and available, but the director's current decision reserves that availability for this repair before the queued priority-690 QKV lane. No image, container, server, CUDA, or scientific invocation exists on the bench.

Decision: typed shared dependency `shared_bench_priority`; do not claim or touch the guest. The QKV component arm remains unconsumed, its immutable execution manifest is unchanged, and project spend remains `$0`. After the FP8 scientific terminal and release, run the bound outer once through the component terminal and conditionally the BF16 c32 consumer.

## 2026-07-20 — primary repair owner is live and uninterrupted

Question: has the retained H200 reached the terminal-and-release gate for QKV execution?

Evidence: the one permitted local reconciliation found the primary FP8 project `active` with `terminal: null` and durable unit `gemma4-inmemory-fp8-c32-20260719t230415z.service`, deadline `2026-07-20T03:10:00Z`. The pool claim is live for that project with heartbeat `2026-07-19T23:07:34Z`. The owner reports seven retained checkpoint files SHA-256 verified, the `38,906,880`-byte partial removed, and only the missing `49,784,788,364`-byte first shard transferring. Image pull, CUDA, and science have not started.

Decision: typed external boundary `shared_bench_claimed`. Preserve the primary owner without service or guest polling or mutation. The QKV arm, manifest, and `$0` spend remain unchanged; run the bound outer only after the primary scientific terminal and release.

## 2026-07-20 — healthy primary claim remains the execution boundary

Question/action: reconcile the named terminal and pool claim once without inspecting the durable service or guest. Evidence: the FP8 project remains `active` with `terminal: null`; its recorded durable owner and `2026-07-20T03:10:00Z` deadline are unchanged, and the pool shows a fresh `2026-07-19T23:12:04Z` heartbeat for that project. Interpretation/next move: `shared_bench_claimed`; preserve the healthy transfer owner. QKV remains unconsumed at `$0` and starts only after the FP8 scientific terminal and release.

## 2026-07-20 — claimed-bench boundary reconfirmed

Question/action: check the named FP8 terminal once, using the supplied pool snapshot for ownership. Evidence: FP8 remains `active` with `terminal: null`; the supplied claim heartbeat is `2026-07-19T23:14:19Z` and is non-stale. Interpretation/next move: `shared_bench_claimed`; do not inspect or disturb the owner. QKV remains unconsumed at `$0`; launch the unchanged bound outer only after terminal and release.

## 2026-07-20 — live FP8 ownership still blocks launch

Question/action: read the named terminal once and accept the supplied inventory as the ownership observation. Evidence: FP8 is still `active` with `terminal: null`; its supplied heartbeat is fresh at `2026-07-19T23:16:35Z`. Interpretation/next move: `shared_bench_claimed`; preserve the durable owner. QKV remains unconsumed at `$0` and its bound outer starts only after terminal and release.

## 2026-07-20 — FP8 terminal still pending

Question/action: check the named terminal once against the supplied live claim. Evidence: FP8 remains `active` with `terminal: null`; claim heartbeat `2026-07-19T23:18:05Z` is fresh. Interpretation/next move: `shared_bench_claimed`; preserve the owner. QKV remains unconsumed at `$0` until terminal and release.

## 2026-07-20 — QKV owner_failure at a retained-diagnostic boundary

Question: does the one content-bound stock-versus-custom discriminator clear `0.045972869706` seconds/request on H200?

Action: after the FP8 release, patched the stale priority guard to admit active-but-offline lower-priority work and corrected the live ID-keyed pool parser before claim. Rebound all changed project-local hashes, then the outer claimed H200 at `23:30:20Z`, heartbeated, verified remote program bytes, and started the component. The first worker failed before candidate CUDA because pinned `get_rope()` required global scheduler args; initialized the minimal pinned scheduler context, rebound the candidate and component runner, and authorized only the same-claim component retry.

Evidence: the retry returned nonzero with empty outer-captured stdout/stderr and no compact `TERMINAL.json` or `RESULT.json`. The controller therefore emitted `owner_failure` and released to maintenance after `179.252043` seconds, conservatively `$0.122489`. Local terminal SHA-256 is `c45da933...d33bb`; events SHA-256 is `3ddc12de...7150`. The first traceback is retained and proves that failure pre-CUDA, but the retry's remote `benchmark.stderr` was not retrieved before release. Candidate-CUDA consumption and a scientific component classification are therefore unknown. No BF16 endpoint ran.

Interpretation and next move: this is `bench_maintenance_observability`, not `component_negative` or `path_unproven`. Do not claim or replay. The director must reconcile the maintenance bench and retrieve the retained remote component diagnostic and any compact terminal first; resume the same frozen arm only if that evidence proves an ordinary pre-CUDA defect and the director explicitly re-admits it.

## 2026-07-20 — fresh-run repair prepared; current primary owner is the boundary

Question/action: repair only the reconciled pre-CUDA output-directory collision and invoke the re-admitted first candidate.

Evidence: `remote_component.sh` is now SHA-256 `699364...5e15b`; it requires a unique `QKV_COMPONENT_RUN_ID`, rejects an existing directory, and invokes the unchanged candidate program SHA-256 `0f9c58...5b86d` under that path. The outer is SHA-256 `a85e38...5204`; it assigns a fresh run ID per worker attempt and retrieves `SCIENTIFIC_STARTED`, compact `TERMINAL.json`, and `RESULT.json` before release. The refreshed project-local manifest is `artifacts/retry-prep-20260719t2351z/INPUT_MANIFEST.json` SHA-256 `8456f4...7c90`, and the unchanged offline oracle passes. Its claim preflight then observed the live pool claim for `gemma4_h200_inmemory_fp8_endpoint` at `2026-07-19T23:47:29Z`, with durable owner `gemma4-inmemory-fp8-c32-20260720t2348z.service`. The controller raised `typed_shared_dependency:primary_fp8_project_still_active` before artifact-root creation, SSH, GPU use, or candidate start.

Interpretation/next move: `shared_bench_claimed` is a typed external boundary. The QKV arm remains unconsumed and has no new provider exposure. Preserve the active primary owner; after its typed terminal and ready release, use the bound fresh-run outer once without reopening preparation.

## 2026-07-20 — primary durable owner remains the typed boundary

Question/action: reconcile the named dependency once and launch QKV only if its terminal and pool release are present.

Evidence: `gemma4_h200_inmemory_fp8_endpoint` remains `active` with durable unit `gemma4-inmemory-fp8-c32-20260720t2348z.service`; its terminal is not yet recorded. The atomic pool view reports that project as the exclusive H200 claimant with a non-stale `2026-07-19T23:54:17.601624Z` heartbeat. No QKV artifact root, SSH session, CUDA call, or candidate marker was created.

Interpretation/next move: `shared_bench_claimed`; preserve the owner without guest/service polling. The first QKV candidate remains unconsumed at `$0.122489` prior measured exposure. Immediately after the primary typed terminal and ready release, run the already-bound fresh-run outer once.

## 2026-07-20 — launcher failure before QKV program start; maintenance boundary

Question/action: claim the released H200 and run the re-admitted first component candidate.

Evidence: the outer claimed at `00:19:44Z` and verified remote identities/input hashes. Attempt 1 exited `127` before remote execution because GNU `timeout` interpreted `QKV_COMPONENT_RUN_ID=...` as its executable. The same claimed controller accepted one ordinary repair; attempt 2 failed at `remote_component.sh: line 7` because its environment shim did not deliver `QKV_COMPONENT_RUN_ID`. Retrieved `component-SCIENTIFIC_STARTED`, `component-TERMINAL.json`, and `component-RESULT.json` are empty; bounded raw stderrs `331947...cd37` and `ffe66f...c0d3` are preserved under `artifacts/qkv-component-20260720t0019z/`. Thus neither the component program nor candidate CUDA began, and no BF16 endpoint ran. The controller emitted `owner_failure`, recorded `98.018598s` / `$0.066979`, and released the bench to maintenance. Cumulative project exposure is `$0.189468`.

Interpretation/next move: this is `bench_maintenance_observability`, not a scientific result; the frozen arm remains unconsumed. Patched the controller to invoke `timeout ... env QKV_COMPONENT_RUN_ID=... bash ...` (outer SHA-256 `15abc5...4031`); refreshed project-local manifest `artifacts/retry-prep-20260720t0022z/INPUT_MANIFEST.json` SHA-256 `7a5b54...2efb` passes the unchanged offline oracle. Do not reclaim maintenance without director reconciliation and explicit re-admission.

## 2026-07-20 — scientific component terminal: retain incremental gain

Question/action: run the re-admitted first QKV component candidate with the corrected env-prefixed outer and conditionally promote only on the frozen gate.

Evidence: one claimed H200 component invocation wrote `SCIENTIFIC_STARTED` (`625377...5e72`), compact terminal (`cd5b06...c970`), result (`21533b...2d91`), and hash-verified archive (`3116b...d8c9`) under `artifacts/qkv-component-20260720t0026z/` before ready release. Numerical and no-materialization oracles both pass. The candidate removes one stock Q/K normalization plus RoPE launch per exact case, has no dynamic live-byte increase, uses 22/26 registers per thread with no spills, and raises decode CTA coverage from the stock 24.24% per launch to at least 9.70 candidate waves. Its conservative occurrence-weighted saving is `0.019215718856250005 s/request` (`223.334ms` prefill plus `391.569ms` decode per c32 batch), below the required `0.04597286970625021 s/request`.

Interpretation: measured positive component evidence is retained, but it misses promotion by `0.02675715085 s/request`; `retain_incremental` is the preregistered terminal. The conditional BF16 c32 endpoint was correctly not invoked. The controller spent `39.774085s` / `$0.027179`, released the bench ready, and cumulative QKV exposure is `$0.216647`.
