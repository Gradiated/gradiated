# Research log

## 2026-07-23 — director admission

Admitted one model/hardware co-design proxy after two exact local-attention kernel redesigns closed. The candidate changes only the 50 local layers' window from 1,024 to 512 and is explicitly barred from production promotion without separate quality validation or recovery. No GPU has been claimed.

## 2026-07-23 — offline path bound and typed H200 storage boundary

Question: can the exact 1,024→512 local-window proxy reach the endpoint gate, and is the retained H200 executable after the higher-priority n-gram lane?

Action: materialized the pinned model config, 62.58-GB checkpoint, current stacked-runtime inputs, Gemma4 source, and `_fwd_kernel` source under this project. `PATH_BINDING.json` binds `config.json`'s 50-local/10-global pattern through `Gemma4Attention.sliding_window`, `RadixAttention`, `TritonAttnBackend.forward_extend`, and `_fwd_kernel.SLIDING_WINDOW_SIZE`. Implemented the one-shot component/reference check, local-only source patch with 50/10 runtime audit, conditional exact c32 pair, and bounded pool owner. No GPU was claimed.

Evidence: `PHYSICAL_BOUND.json` counts the pinned kernel's non-skipped 64×64 QK/V tiles at the admitted boundary and observed grid-z2/grid-z32 shapes. Window 512 removes 42.857–47.059% of active tiles; the conservative value times the measured 15.312032% local-kernel wall fraction is a 6.562299% whole-request opportunity bound, or `0.630075 s/request` from the current `0.674326` control. This passes both the 5% and `0.6381105231 s/request` analytical gates but remains an analytical bound, not measured latency.

The higher-priority n-gram lane then produced new external evidence: its separate 62.58-GB remote immutable checkpoint staging failed with `ENOSPC` before CUDA and it released `h200-sync-linear-e00vhh6h29fj68x91g` to maintenance. `EXTERNAL_BLOCKER.json` records that the same snapshot rule applies here; bypassing it by mounting another project's remote checkpoint is forbidden. This project's candidate CUDA/scientific invocation did not start, its arm is unconsumed, and cumulative provider exposure remains `$0.00`.

Interpretation/next: the physical gate justifies measurement, but the sole admitted bench is not safely executable. Director disposition requires a compatible lab-owned H200 returned ready with at least 62.58 GB free for this project's immutable snapshot and at least 25 minutes of lifecycle after staging. Then run the already materialized component/path check and conditional sole c32 pair without changing geometry.

## 2026-07-23 — director resolves shared-checkpoint storage boundary

The director authorizes the same content-addressed resident checkpoint for read-only reuse after one full-manifest validation, with all candidate overlays and mutable outputs kept project-local. No second 62.58-GB copy is allowed. Since source/geometry binding and the 6.5623% physical bound are already complete, the project moves from `deep` to `execution` and waits behind the higher-priority n-gram arm on the retained H200.

## 2026-07-23 — stale MTP memory owner removed

Director maintenance stopped and removed the terminal MTP project's stale 123-GiB container and verified the H200 has no remaining compute process or used GPU memory. This project remains active and queued behind the now-reactivated n-gram diagnostic; its intervention, bound, component, and conditional endpoint are unchanged.

## 2026-07-23 — shared-resident execution deferred by live dependency claim

Action: verified the director disposition and exact manifest hash (`7ed5b04ef9c115a2cbba771df463ca0cacbfb87cfa298773e8b037d12bcea735`), patched the existing owner to validate all eight resident files before use, bind `/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint` read-only, and omit the local 62.58-GB checkpoint from staging. Python compilation passed; no GPU or scientific invocation began.

Evidence: the `$14` reservation is durable and the local-window owner observed the H200 claimed by `gemma4_h200_ngram_speculative_endpoint` at `08:04:28Z`, heartbeat through `08:07:17Z`, lease until `10:07:17Z`. Its repair artifacts show the first shared-manifest attempt failed before CUDA on a basename-manifest formatting defect; the second repair owner exited `137` without a release or typed scientific terminal. The local owner remained in dependency wait and was stopped without claiming the bench. Cumulative local-window exposure remains `$0.00`.

Interpretation/next: this is a typed cross-project claim/retrieval blocker, not a local-window result. After the n-gram project emits its compact terminal and releases the exact bench, rerun the patched owner once under the same bound component and conditional c32 contract; do not reclaim or release the n-gram lease here.

## 2026-07-23 — dependency cleanup verified; n-gram still active

Rechecked the named dependency and current pool. Director cleanup verified `mtp-depth-candidate` stopped/removed, zero GPU processes, zero GPU memory, and an unchanged read-only resident checkpoint. The H200 is available, but n-gram remains `active` with no final typed project terminal; its latest worker terminal is `integration_failure` from the frozen runner path and its status still schedules the n-gram server startup/diagnostic. No local-window claim or scientific invocation was started, and exposure remains `$0.00`.

Next: remain queued until n-gram emits its typed terminal and releases the bench, then run the already patched owner once. Do not claim the currently available bench ahead of the higher-priority dependency.

## 2026-07-23 — NGRAM comparator bound prepared offline

The qualified NGRAM c32 control terminal is present and immutable at `0.5967508053124675 s/request`, with 32/32 requests and exact `117728` uncached plus `17120` cached prompt-token accounting. The production-validation project remains active without a typed terminal or bench release, so no claim or endpoint run is allowed yet.

Action: created `PHYSICAL_BOUND_NGRAM.json` by applying the existing conservative non-skipped tile reduction (`42.8571%`) and historical local-kernel fraction (`15.3120%`) to the persisted NGRAM control. The scope-matched analytical bound is `0.5575902305 s/request` (`6.5623%` opportunity), below the 5% threshold of `0.5669132650 s/request`; this authorizes measurement only after the dependency terminal/release and component/path gate. NGRAM is not replayed and the 512-window intervention is unchanged.

## 2026-07-23 — production-validation control repair still pending

Rechecked the priority-2200 dependency. Its token/tool suite is unconsumed; the matched control failed before model readiness because the launcher omitted the verified resident checkpoint bind. The director authorized one exact mount repair only. The H200 is available but not released to this project under the scheduled ordering, and the dependency remains `active` with no typed terminal. No local-window claim or scientific invocation began; local-window exposure remains `$0.00`.

Next: wait for the repaired validation control to reach a typed terminal and release. Then branch strictly on its result: reuse the persisted NGRAM c32 terminal only if validation passes, otherwise retain non-speculative scope. Do not claim ahead of the dependency or replay its work.
## 2026-07-23 — rebind endpoint comparison behind n-gram production validation

The frozen 512-window mechanism remains active, but its `6.5623%` bound was derived on the pre-NGRAM stack and is now historical. Native NGRAM measured `0.5967508053 s/request`, below the campaign ceiling, while a preliminary response reconstruction exposed an unresolved 19/32 deterministic text mismatch. Queue this project behind `gemma4_h200_ngram_production_validation`. If NGRAM qualifies, preserve that exact contract, reuse its persisted terminal as control, and measure only the stacked window candidate after a new scope-matched physical bound; otherwise retain the original non-speculative comparator. The 512-window change, quality-unsafe label, reservation, budgets, and no-sweep rule are unchanged.

## 2026-07-23 — resume the original non-speculative pair after NGRAM cleanup

NGRAM production validation closed under its preregistered final-repair rule: the explicit checkpoint bind reached model construction, but a co-resident control OOMed before readiness; no candidate request or quality suite ran. NGRAM therefore remains quality-unqualified and is not this project's comparator. Director maintenance claimed the available H200, removed terminal containers `gemma-ngram-pair` and `gemma-ngram-control`, verified them absent with zero GPU compute processes and zero MiB used, preserved the read-only checkpoint and caches, and returned the bench ready. `PHYSICAL_BOUND_NGRAM.json` is retained only as inapplicable interaction evidence. Run the already-implemented original non-speculative component and contemporaneous c32 control/window512 pair once under `PHYSICAL_BOUND.json`; no NGRAM replay or scope change is admitted.
## 2026-07-23 — 512-window component numerically rejected

Action: consumed `DIRECTOR_NGRAM_SERVER_CLEANUP.json`, claimed the retained H200, validated all eight resident checkpoint files against the bound manifest, and ran the existing non-speculative component/path check once. Two owner predicates that assumed an unclaimed/available bench were repaired inside the same retained claim before any CUDA invocation; no intervention, workload, or bound identity changed.

Measured evidence: the real candidate path executed with 50 local layers, 10 global layers, 32 query heads, 16 KV heads, head dimension 256, FP8 E5M2 KV, and no 1,024-token fallback. Component latency improved 32.21% call-weighted, but numerical agreement with the exact 512-window reference failed in all three cases: relative L2 `0.057275` / `0.056212` / `0.024240`, cosine `0.998463` / `0.998518` / `0.999710`. Output shapes and finiteness passed; the numerical gate was false.

Decision: terminal `numerical_negative`. The conditional c32 control/window512 endpoint pair was not invoked, NGRAM was not enabled or replayed, and the H200 was released ready. Conservative local-window exposure is `$0.065851`; the proxy is closed without promotion or further repair.
