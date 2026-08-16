# In-memory FP8 linear endpoint

## Question

Can a model-specific loader turn the exact Gemma 4 31B checkpoint into a real Hopper FP8 linear execution path in memory, without depending on the failed ModelOpt export serializer, and reduce the exact c32 endpoint by at least 10% from the retained `0.9194573941250042` seconds/request baseline?

## Why this is open

Official ModelOpt 0.44 successfully loaded 1,188 tensors, inserted 2,154 FP8 quantizers, and completed calibration before Gemma 4 serialization failed. That terminal falsifies the exporter, not FP8 execution. Exact-shape E4M3 component evidence also passed numerical oracles. The reopened campaign explicitly admits one small model-specific in-memory loader or consumer path.

## Frozen identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Checkpoint: eight files, `62,578,655,208` bytes, local source under `../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint`; checkpoint terminal SHA-256 `5f0765fa37f308e21d665571a92c29ba1998b22b5ee67d1edbfac103dafec481`.
- Runtime: pinned SGLang v0.5.12 image `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`, BF16 attention/state, FP8-E5M2 KV, dynamic chunking 2,048, and stock fused QK normalization/RoPE.
- Comparator: `../gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`, SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`, `0.9194573941250042` seconds/request with 17,120 cached and 117,728 fresh prompt tokens.
- Runner: `../gemma4_background_serving_frontier/exact_mix_runner.py`, SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- Failed producer evidence: `../gemma4_modelopt_fp8_export_endpoint/artifacts/modelopt-fp8-export-c32-20260718t1900z/RESULT.json`, SHA-256 `8515b7aa2babc0a0a8255776e4523618fa4f27fa6c93586dfc718cdc455f3033`.

Do not substitute a revision, checkpoint, workload, cache mix, concurrency, KV precision, or comparator.

## Immediate experiment

Claim the lab H200 and use one durable owner. Stage the checkpoint and pinned image once, preserving both for the queued kernel project. Inspect the pinned SGLang linear loader and Hopper execution APIs, then implement exactly one source-justified model-specific path that converts the chosen dense Gemma linear weights once during load and executes them through native or fused FP8 GEMM. Do not serialize an export and do not materialize dequantized weights or activations through HBM between dequantization and GEMM. Record the exact included/excluded modules, scale granularity, accumulation type, weight bytes, peak memory, package/source identities, and runtime proof that BF16 fallback is not serving the measured requests.

Use a small deterministic exact-shape layer oracle before server launch. Then require 3/3 coherent smoke prompts, an idle queue, HTTP-200 cache flush, and one unchanged exact c32 invocation. Retrieve raw responses, request rows, cache accounting, phase/queue/GPU/power telemetry, logs, source patch, manifests, and a typed terminal. Ordinary loader/import/API defects may be repaired in place within the one implementation. Do not branch into a quantization recipe, scale, calibration, module-scope, or concurrency sweep.

## Gates and limits

- `frontier_pass`: intended FP8 path proven, numerical and 3/3 coherence gates pass, 32/32 exact-mix rows pass, cache accounting is exact, and service time is at most `0.7079821934762532` seconds/request (the current 23% cost-gap target).
- `useful_pass`: all identity and correctness gates pass and service time is at most `0.8275116547125038` seconds/request (10% improvement).
- `retain_incremental`: all gates pass and service time improves on `0.9194573941250042`; preserve a simple compatible gain without tuning.
- Otherwise emit one of `path_unproven`, `numeric_negative`, `coherence_negative`, `endpoint_negative`, `memory_failure`, `consumer_failure`, `timeout`, or `owner_failure` and close this implementation.

Maximum: 210 wall minutes, 165 H200 claim minutes, 140 GiB temporary storage, and `$14.00` provider exposure. Reserve 20 minutes for terminal retrieval and release. Release without teardown. Do not run broad quality, rerun ModelOpt calibration/export, test W4, change hardware, create provider resources, or run the queued QKV project inside this project.

## Director follow-up — 2026-07-20 semantic consumer schedule

The prior scheduler-side implementation stopped before FP8 module loading because exact source hashes for `DefaultModelLoader.load_weights_and_postprocess` and `Engine._launch_scheduler_processes` disagreed with the actual pinned image, while all five core FP8 method hashes matched. That is an orchestration-audit failure, not a low-precision result. Do not replay the failed seven-function source-hash schedule. Keep the same scientific project and immutable model, checkpoint, image, workload, BF16 state/attention, FP8-E5M2 KV, dynamic chunking, and c32 geometry.

Use one new semantic audit schedule on retained bench `h200-kernel-frontier-e00pfvrckjvwn7bhet`: validate the exact image digest and matched core FP8 functions, then require 240 scheduler-side quantized module rows and at least one observed real `fp8_scaled_mm` consumer invocation before coherence or timing. Wrapper source text is diagnostic only. Run the deterministic numerical oracle, 3/3 coherence prompts, and exactly one exact-distinct c32 endpoint arm; retrieve raw rows, audit events, logs, and the typed terminal before release.

The comparator is the scope-matched c32 row in `../gemma4_h200_critical_path_profile/artifacts/h200-saturation-20260720t0037z/TERMINAL.json` (terminal SHA-256 `88d1d6499656274cf05d00f9610425f3b7bf35b8f00161b4bfc43a0484a1ac07`): `29.697289871000066` batch seconds and `0.9280403084687521` service seconds/request with exact cache accounting and valid outputs. `frontier_pass` requires `<=0.7145910375209391`; `useful_pass` requires `<=0.8352362776218769`; retain a simple incremental only below `0.9280403084687521`. This is one implementation, not a source-hash, module-scope, scale, concurrency, or runtime sweep.

## Director follow-up — 2026-07-20 timing-first discovery schedule

The semantic schedule reached HTTP readiness but again allowed missing audit-file production to suppress coherence and endpoint timing. Close that audit-first schedule. The next and final discovery schedule must measure the actual endpoint first: claim the retained H200, probe and reuse the healthy FP8-configured server when possible, otherwise restart the same immutable configuration once, then run 3/3 coherence and exactly one exact-distinct c32 arm immediately. Audit-file presence, wrapper hashes, and operator provenance are not pre-create or pre-timing gates.

After the c32 artifacts are durable, capture one bounded post-hoc operator trace or equivalent runtime evidence for `fp8_scaled_mm`, module coverage, configured quantization, and memory residency. Provenance may upgrade a performance proxy to a deployable path, but missing provenance must not erase a valid endpoint measurement. Report `frontier_proxy_pass` at `<=0.7145910375209391`, `useful_proxy_pass` at `<=0.8352362776218769`, or `retain_incremental_proxy` below `0.9280403084687521`; keep the `proxy` label unless real FP8 consumption is proven. A non-improving endpoint, failed coherence, or failed accounting closes the line. No further audit repair, implementation branch, or replay is authorized.

## Director follow-up — 2026-07-20 endpoint-only gate reconciliation

The timing-first run produced `READY`, `4`, and a semantically correct `{"status":"ok"}` wrapped in a Markdown JSON fence. Under the campaign's exploration rule, that is a structured-format compliance caveat rather than obvious incoherence: two exact prompts passed, the third remained finite and parseable, `/v1/models` was healthy, and the exact-shape FP8 consumer oracle passed. Do not replay or weaken the recorded coherence test, and do not make a deployability or quality claim from it.

Use the same exact checkpoint, image, in-memory E4M3 linear configuration, BF16 state/attention, FP8-E5M2 KV, dynamic chunking 2,048, and content-bound exact-mix runner for one endpoint-only discovery arm on retained bench `h200-kernel-frontier-e00pfvrckjvwn7bhet`. Probe and reuse the retained server if healthy or restart that same immutable configuration once, then run exactly one exact-distinct c32 workload immediately. Require 32/32 finite nonempty responses, exact 4,214/358 token geometry, 17,120 cached and 117,728 fresh prompt tokens, bounded queueing, and durable raw rows before release. Do not rerun coherence, repair provenance, change the model or prompt path, tune quantization, or sweep concurrency.

Compare only with the scope-matched c32 control at `0.9280403084687521` seconds/request. Report `frontier_proxy_pass` at `<=0.7145910375209391`, `useful_proxy_pass` at `<=0.8352362776218769`, `retain_incremental_proxy` below the control, or `endpoint_negative` otherwise. Preserve the proxy label and the structured-output caveat unless existing bounded post-hoc evidence proves the actual FP8 path; provenance cannot suppress or invalidate a valid timing row. This endpoint arm is the terminal decision for this representation.

## Director follow-up — 2026-07-20 exact-container correction

The endpoint-only owner did not consume its c32 arm. Its preflight attached to the healthy container publishing port 30000, but the retained container was `gemma-critical-path-saturation`, the prior BF16 saturation server, not `gemma-inmemory-fp8-c32`. Its Prometheus gauges also proved both running and queued requests were `0.0`; the frozen parser rejected the labels between the metric name and value. The attempted sitecustomize repair did not alter that inline parser. Treat this as a pre-request container-identity and parser defect, not FP8 performance or quality evidence. The earlier fenced coherence response is BF16 evidence and must not be transferred to FP8.

Claim the same retained H200 once and make one bounded operational correction inside this project. Never reuse an arbitrary container merely because it publishes port 30000. Stop the conflicting retained BF16 saturation server under the claim, then launch the exact named `gemma-inmemory-fp8-c32` container from the pinned image with the bound checkpoint and the existing `--quantization fp8`, ignored-layer, BF16 state/attention, FP8-E5M2 KV, dynamic-chunking 2,048, and c32 settings. Persist `docker inspect` command, image digest, mounts, name, and container ID before the workload. Accept labeled Prometheus samples only when every `num_running_reqs` and `num_queue_reqs` value is zero; a missing metric or nonzero value remains a failure.

After exact identity and idle state are durable, run the same sole exact-distinct c32 arm without a coherence or provenance pre-gate. Retrieve 32/32 raw rows and exact token/cache accounting before release. Compare with `0.9280403084687521` seconds/request using the existing proxy ceilings. Do not replay the BF16 coherence artifacts, add another implementation, or sweep. The first representation-valid c32 terminal closes this FP8 line.
