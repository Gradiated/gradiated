# Research log

## 2026-07-19 — activated

The 2026-07-20 campaign phase reopens deployable low-precision execution. The prior official ModelOpt run completed quantization but failed Gemma 4 serialization before any consumer, while exact-shape E4M3 linears were numerically positive. Admit one in-memory H200 endpoint implementation against the canonical `0.9194573941250042` seconds/request comparator. Require a proven FP8 GEMM path, exact cache accounting, coherent output, and at least a clean measured improvement; do not sweep recipes or rerun the failed exporter.

## 2026-07-20 — content-bound loader ready; pre-invocation bench boundary

Question: can the exact BF16 checkpoint use a real in-memory Hopper FP8 path without ModelOpt serialization? Action: traced pinned SGLang v0.5.12 and selected its stock `Fp8Config(is_checkpoint_fp8_serialized=False)` path, limited by `SGLANG_FP8_IGNORED_LAYERS` to the 240 text-transformer linears. Materialized and independently hashed the complete 62,578,655,208-byte checkpoint under this project, plus the frozen exact-mix and coherence consumers. Implemented an exact `[32,5376] x [5376,43008]` gate/up oracle that requires an observed `sgl_kernel.fp8_scaled_mm` call, E4M3 weights, BF16 output, and a numerical gate. The resulting manifest passes at `artifacts/local-preparation/MANIFEST.json`; inferred resident candidate weights are 29,396,828,160 FP8 bytes plus 16,998,400 scale bytes.

The director then marked the H200 ready. The outer owner claimed it once, but the first SSH identity command failed because provider IP `89.169.121.209` had a stale fingerprint in the campaign known-hosts file. Measured evidence: claim-to-release was under one second; remote stdout was empty; no remote command, transfer, image pull, CUDA call, producer, server, or endpoint invocation occurred. This is an ordinary pre-invocation wiring failure, not a candidate result. The owner incorrectly released to maintenance and wrote optimistic resident contents; actual state remains the director's pre-claim empty bench. Patched the controller to remove only the provider-resolved IP entry before `accept-new`, preserve accurate contents, retain the same-claim repair window, and reserve the final 20 minutes. Next: director confirms the untouched provider and marks the bench ready; rerun the same frozen schedule with no arm change.

## 2026-07-20 — durable in-place rerun active

Action: after grouped local manifest and syntax checks, the repaired owner atomically claimed `h200-kernel-frontier-e00pfvrckjvwn7bhet`. It refreshed only the provider-resolved IP host key and completed authenticated identity (`NVIDIA H200`, expected guest hostname, Docker 29.5.3). The coordinator terminated its first ordinary background-process launch after that identity stage, before checkpoint staging, CUDA, or a scientific invocation; the unterminated owner was therefore resumed on the same idempotent claim using the controller-host user service `gemma4-inmemory-fp8-c32-20260719t2251z.service`. Evidence: service active, PID 2863753, recorded control group, and a successful pool heartbeat. The controller is transferring the content-bound eight-file checkpoint; its deadline is `2026-07-20T03:10:00Z`, reserving 20 minutes for retrieval/release. No candidate result yet.

## 2026-07-20 — manifest-aware checkpoint repair active

Action: replaced the all-files SCP retry with a remote size-and-SHA-256 comparison against the frozen eight-file project-local manifest, then claimed the ready H200 with `gemma4-inmemory-fp8-c32-20260719t230415z.service`. Measured remote matches: six metadata files and `model-00002-of-00002.safetensors` (12,761,549,884 bytes); the only mismatch was the partial `model-00001-of-00002.safetensors` (previously 38,906,880 bytes). The owner removed that file and is transferring only its immutable 49,784,788,364-byte source. A pool heartbeat succeeded after staging began. It will rehash all eight files before image pull/CUDA and then continue the one frozen schedule; no scientific invocation has been replayed.

## 2026-07-20 — scheduler-side audit repair prepared behind QKV

Question: why did the exact-shape FP8 oracle pass and the FP8-configured server load 33.58 GiB, capture c32 graphs, and reach `/v1/models`, yet emit no module audit? Source-backed diagnosis: pinned SGLang commit `127b9e3283f7c2a43234b852ff5c9f1796d53624` forces multiprocessing `spawn`, launches model loading in a scheduler subprocess, and calls `quant_method.process_weights_after_loading` there. The original entrypoint patched `Fp8Config`/`Fp8LinearMethod` only in the HTTP parent, so the fresh scheduler never inherited the monkeypatch. The missing JSONL is therefore an observability defect, not negative evidence about the FP8 producer or consumer.

Action: changed the same entrypoint to pass an `audited_run_scheduler_process` target into the pinned HTTP launcher and install the hooks inside that worker. The repair binds seven loader/launch/FP8 function bodies to the exact commit, requires 240 post-load module rows, and records the scheduler PID plus the first real `fp8_utils.fp8_scaled_mm` call in separate runtime and consumer artifacts before endpoint timing. Measured offline checks reproduced `parent_monkeypatch_survives_spawn=false`, proved `scheduler_target_install_survives_spawn=true`, and matched all seven source hashes plus six staged program hashes. Evidence: `artifacts/offline-audit-repair-20260719t2335z/RESULT.json`.

Next: no GPU was claimed and incremental spend was zero. At the dependency check QKV remained active without a terminal and the shared H200 was in maintenance, so do not claim or restart it. After QKV emits its terminal and the pool releases the bench ready, run the unchanged schedule once with the repaired content-bound audit and continue through endpoint measurement or a typed target-runtime failure.

## 2026-07-20 — frozen FP8 schedule executing

The persisted QKV terminal and pool-ready state cleared the dependency; the H200 was atomically claimed at `2026-07-19T23:47:29Z`. The first owner launch failed before claim/SSH/CUDA because the launcher pre-created the fresh artifact directory; removing only that empty directory and retrying the same claim/session repaired the ordinary wiring defect. The durable owner `gemma4-inmemory-fp8-c32-20260720t2348z.service` (PID 2896573) authenticated the H200, matched all eight remote checkpoint files, and staged the bound inputs. Heartbeats continue while the single remote schedule runs; no terminal or candidate-start marker has yet been retrieved.

## 2026-07-20 — typed consumer failure; close implementation

The durable owner persisted `TERMINAL.json` classification `consumer_failure` and released the H200 ready at `2026-07-20T00:15:37Z`. The bounded diagnostic is retained at `artifacts/inmemory-fp8-c32-20260720t2348z/repair-diagnostic.stdout`; terminal archive SHA-256 is `87bdc35de1d90d6544236f3b7a586697e26aa1cdcb9f9b88171bd6b6c8419d60`.

Measured execution evidence: the pinned image started and launched its scheduler, but `endpoint_entrypoint.py` aborted before FP8 module loading because its frozen seven-function source contract observed `DefaultModelLoader.load_weights_and_postprocess=f023f35ac4ce273a166f337170fd4afe8e4082d1c1caf68bddc023b02be2ce31` instead of the bound `34bf1153…`, and `Engine._launch_scheduler_processes=5463dd9831c7c00012ae4d4429eebf31db3b4312e17a7ae0e432a49643b961bd` instead of `2c1f9296…`. The other five functions matched. The scheduler died with exit code 1.

No 240 scheduler-side module rows, real `fp8_scaled_mm` consumer row, coherence rows, or exact c32 endpoint rows were produced. The repair handshake expired without a request; because the owner is terminal and released, no retry or replay is authorized. This is an integration/contract failure, not evidence for or against FP8 endpoint quality.

## 2026-07-20 — semantic schedule path unproven; close arm

Action: replaced only the failed orchestration-wrapper source gate with five core FP8 source checks, retained wrapper hashes as diagnostics, regenerated the immutable input manifest, claimed the retained H200, and ran the one admitted semantic consumer schedule with the unchanged checkpoint/image/c32 workload.

Measured execution evidence: the pinned container launched and `/v1/models` returned HTTP success, but `server-fp8-modules.jsonl` was absent. The retrieved worker diagnostic is `FileNotFoundError: /home/glmrunner/gemma-kernel-frontier/artifacts/inmemory-fp8/server-fp8-modules.jsonl`; the terminal classified `path_unproven`. No 240 scheduler-side quantized module rows, real `fp8_scaled_mm` row, coherence rows, or exact c32 endpoint row were produced. The H200 was released `available` after archive retrieval; terminal archive SHA-256 is `f74ebbb31d89610b45eac1368e449828572b36989d55ef770612f0c146a11c28`.

Interpretation: this is a decision-bearing runtime/audit observability failure for the one admitted semantic arm, not a measured FP8 quality result. Do not replay the consumed schedule under the current reservation.

## 2026-07-20 — timing-first discovery coherence negative

Action: removed audit-file presence from server readiness and deferred provenance capture until after the real consumer schedule. The runner reused or restarted only the pinned immutable configuration, then invoked the exact three coherence prompts before any c32 timing.

Measured evidence: the H200 owner completed all three prompts and released ready. Instruction passed with exact `READY`; arithmetic passed with exact `4`; structured output failed because the response was fenced JSON (` ```json {"status":"ok"} ``` `) rather than the preregistered bare JSON object. Terminal classification is `coherence_negative`; archive SHA-256 is `fa3e10ff480ea78a788444cb0512bd56dbce576e44ddc9f8aaea739c08fa3197`.

No exact-distinct c32 endpoint arm or post-timing provenance capture ran because the 3/3 coherence gate failed. This is a coherence/consumer result, not an FP8 endpoint timing result; do not replay the final admitted schedule.

## 2026-07-20 — endpoint-only arm closed at repeated parser boundary

Action: removed coherence invocation and coherence gating only; retained the unchanged exact c32 workload, server configuration, cache flush, and 32-request accounting. The H200 owner claimed the bench and reached the existing server.

The first endpoint-only attempt stopped before c32 with `consumer_failure: queue_not_idle`. Retrieved metrics prove both labeled gauges were zero: `num_running_reqs=0.0` and `num_queue_reqs=0.0`; the frozen regex failed because it did not accept Prometheus labels. A same-claim repair installed a temporary parser shim and retried once, but the owner produced the same queue parser terminal before any request. The shim was removed and the original Python startup file restored after release.

No 32/32 raw rows, exact token/cache accounting, or endpoint timing exists. Terminal archive SHA-256: `f09a7718e89eb5f7e21766bed41668e0bf48590db381ce2805bac9b7a402a973`. This is a repeated harness consumer failure, not an FP8 performance result; do not replay the endpoint arm.

## 2026-07-20 — exact-container FP8 endpoint measured useful_pass

Action: claimed the retained H200 once, stopped the conflicting `gemma-critical-path-saturation` BF16 container, and launched only the named `gemma-inmemory-fp8-c32` container with the pinned image, immutable checkpoint mount, BF16 state/attention, FP8-E5M2 KV, dynamic chunking 2,048, and c32 configuration. The first in-claim retry was limited to an ordinary Docker identity assertion defect: Docker's standard NVIDIA entrypoint was valid but not admitted by the assertion. Full `docker inspect` identity was persisted before continuing.

Measured evidence: the corrected server reached HTTP readiness and labeled Prometheus queue gauges were accepted only with all values zero. The sole exact-distinct c32 arm produced 32/32 complete rows, each with 4,214 prompt and 358 completion tokens. Cache accounting was exact: 134,848 total prompt tokens, 117,728 fresh, and 17,120 cached. Service time was `0.748553484718741` seconds/request, a measured 19.3404% reduction from the `0.9280403084687521` comparator and below the `0.8352362776218769` useful ceiling, yielding `useful_pass`.

Runtime provenance is also valid: 240 FP8 module rows and one scheduler-side `sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm` row were retrieved, with FP8 E4M3 inputs/weights and BF16 output. Terminal: `artifacts/exact-container-fp8-c32-20260720t0131z/TERMINAL.json`; terminal SHA-256 `619e8938959dc79cfb581330a8822b8261f5d8e4e1b4695915d4918707bd9faa`; archive SHA-256 `b7a65e7a646b001af58d63376395b5b67db76a5a092368e739e7a7ab4c6e4f0f`. The H200 was released ready. This closes the representation; do not replay or sweep.
