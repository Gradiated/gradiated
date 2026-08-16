# Custom QKV epilogue fusion discriminator

## Question

Can a custom exact-shape Gemma 4 QKV projection epilogue fuse split, Q/K RMS normalization, partial RoPE, and layout/writeback closely enough to remove at least `0.04597286970625021` seconds/request from the canonical H200 endpoint before any server integration?

## Independence and evidence

This is a residual kernel/dataflow lane, independent of weight precision. The stock SGLang fused-QK flag is already retained and measured only `0.011981051969165213` seconds/request faster than its comparator; do not rerun or relabel that flag. The new hypothesis is a custom projection epilogue that eliminates intermediate global-memory traffic and launches at exact local/global Gemma shapes. Canonical profile evidence is `../gemma4_h200_critical_path_profile/PROFILE_SUMMARY.json`, SHA-256 `1979d50e96571982fe43d71071b34e3cad47602f2fd8dc0b94e722dd4043c779`.

Frozen model, runtime, checkpoint, comparator, runner, concurrency, token geometry, cache mix, and KV precision are identical to `gemma4_h200_inmemory_fp8_endpoint`. The endpoint comparator is SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3` at `0.9194573941250042` seconds/request.

## Immediate experiment

While the direct FP8 lane bootstraps and owns the H200, inspect the pinned source and exact Gemma geometry offline and prepare one content-bound CUDA/Triton program plus numerical oracle. Do not claim a GPU until the direct project releases the retained bench. Benchmark the existing stock fused-QK route and the one custom epilogue on the same H200 with exact local/global shapes, sequence/batch geometry, warmups, iteration count, clocks, and occurrence weighting. Prove that the custom path does not materialize the eliminated intermediates and report wall time, bytes, launches, occupancy/resource use, and conservative seconds/request saving. Do not use summed overlapping kernel times as wall time.

Only if the conservative saving is at least `0.04597286970625021` seconds/request and the numerical/no-materialization gates pass may the same owner integrate the custom epilogue into the pinned consumer and run one exact c32 endpoint. The endpoint must use BF16 weights; do not combine it with the FP8 project in this experiment. A smaller clean component gain is durable evidence but does not trigger endpoint integration.

## Gates and limits

- `endpoint_useful`: component gate passes and one exact c32 endpoint is at most `0.8275116547125038` seconds/request with 32/32 coherent rows and exact cache accounting.
- `component_pass`: numerical and no-materialization oracles pass with conservative saving at least `0.04597286970625021` seconds/request; one endpoint is permitted.
- `retain_incremental`: a positive, reproducible, simple component gain below the trigger; record and stop without endpoint integration.
- Otherwise emit `component_negative`, `numeric_negative`, `path_unproven`, `integration_failure`, `endpoint_negative`, `timeout`, or `owner_failure`.

Maximum: 180 wall minutes including offline preparation, 75 H200 claim minutes, 20 GiB temporary storage, and `$6.00` provider exposure. Reserve 10 minutes for retrieval and release. Use the same retained H200 after the direct lane; release without teardown. Do not create provider resources, transfer the checkpoint again, pull a second image, duplicate stock fused GQA/QK work, sweep kernels or launch configurations, change precision, or run broad quality.

## Director follow-up — 2026-07-20 FP8 stack endpoint

The direct in-memory FP8 endpoint is now a proven scheduler-side consumer at `0.748553484718741` seconds/request: 32/32 exact-mix rows, exact cache accounting, 240 quantized linear modules, and an observed scheduler `fp8_scaled_mm` call. Its terminal is `../gemma4_h200_inmemory_fp8_endpoint/artifacts/exact-container-fp8-c32-20260720t0131z/TERMINAL.json`, SHA-256 `619e8938959dc79cfb581330a8822b8261f5d8e4e1b4695915d4918707bd9faa`. This closes 19.34% of the scope-matched BF16 service time but remains `0.03396244719780195` seconds/request above the 23% frontier ceiling.

Re-admit the already measured QKV epilogue as a compatible stack, not a component replay. Its only component terminal and result remain authoritative: numerical and no-materialization oracles pass, and the conservative occurrence-weighted saving is `0.019215718856250005` seconds/request. The FP8 QKV projection emits BF16, which is the candidate epilogue's measured input boundary. Do not rerun the component or run the previously conditional BF16 endpoint.

Claim retained bench `h200-kernel-frontier-e00pfvrckjvwn7bhet` and use the exact checkpoint, pinned SGLang image, in-memory FP8 loader, FP8-E5M2 KV, dynamic chunking 2,048, c32 workload, and exact named-container identity from the FP8 terminal. Run one same-session FP8 control, integrate the existing QKV epilogue patch without changing its kernel, and run one FP8+QKV candidate. Require current-representation smoke outputs `READY`, `4`, and a semantically parseable `{"status":"ok"}` object (Markdown fencing is a recorded compliance caveat, not a pass/fail difference), plus 32/32 finite nonempty rows and exact cache accounting in both timing arms. Prove the candidate epilogue invocation and re-prove the FP8 consumer without placing either audit ahead of timing.

Promote `frontier_stack_pass` at `<=0.7145910375209391` seconds/request. Retain a simple positive stack below the same-session FP8 control even if it misses the frontier; drop a non-improving or unstable stack. The component estimate predicts `0.729337765862491` seconds/request, so this arm is an incremental-stack test, not a guaranteed frontier pass. Stop after the paired control/candidate; no kernel tuning, concurrency sweep, precision change, or broad quality run.

## Director follow-up — 2026-07-20 rebase onto the v0.5.13 FP8 frontier

The current-runtime MTP experiment produced a valid standalone v0.5.13 FP8 control before its candidate failed: `0.6979244359999939` seconds/request, 32/32 exact-mix rows, exact cache accounting, 240 target FP8 modules and consumers, and a real target-prefixed `fp8_scaled_mm` path. The reconciled terminal is `../sglang_v0512_h200_gemma4_mtp_endpoint/artifacts/fp8-mtp-v0513-20260720t0215z/RECONCILED_TERMINAL.json`, SHA-256 `804126d618182bff7e37a4b281969678bb77258cc6c09a6f7c16908f4f7d3711`; the raw control terminal is SHA-256 `ab69b55f328180716e637e0b1a3edfcbbf6f20b2a906f15445695663aca0296f`. This simpler control already beats the `0.7145910375209391` frontier and supersedes the v0.5.12 baseline for all new endpoint comparisons.

Run the same two endpoint arms against exact SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2` and linux/amd64 image `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`. Adapt only the existing endpoint patch to current source boundaries if required; do not alter or replay the persisted QKV component. Run one same-session v0.5.13 FP8 control and one FP8+QKV candidate with the identical workload, dynamic chunking, KV precision, and proof requirements. The additive component estimate predicts `0.6787087171437439` seconds/request, a `2.753%` incremental reduction. Retain any stable positive candidate below the same-session control; the frontier is already cleared, so simplicity and reproducibility now outrank a second threshold crossing. Use the durable repair handshake for ordinary defects proven before either endpoint timing arm starts, and never replay a consumed arm.

## Director execution handoff — 2026-07-20 fresh controller thread

The scientific inputs are already present, but the durable v0.5.13 stack outer is not. The project contains `remote_fp8_stack.sh` at SHA-256 `c59116a381da19efaf6da1ad9c76ac11b55fc6dac5a88440730c03d7cf2afa5d` and `stack_sitecustomize.py` at SHA-256 `5791f6718b90b1ac555f7cb53179b18fd523ffb9f469d02582482431623d39fa`; the worker still names the obsolete v0.5.12 image digest. This is a controller implementation boundary, not a scientific blocker or a reason for another preparation-only turn.

In the fresh execution thread, first snapshot the exact proven v0.5.13 controller ingredients into this project before claiming: the prior durable outer at SHA-256 `13af7b53779966e5bdb893d039b5766517006f7b4f38dba9b3f3112edd1239f4`, endpoint entrypoint at `b4a43f799499b4624d448ff5a8ef52e88bd4c3544fd0878ee5adcd3a1926d6fc`, and paired runner at `df65b1e49c941c27a975ecb1f2d34041a0e63695c2e3515cf950406204f614f3`. Materialize project-local `run_fp8_qkv_stack_outer.py`, preserving the proven claim, heartbeat, immutable-checkpoint verification, content-addressed staging, compact retrieval, invocation-state accounting, repair handshake, spend accounting, and ready-release mechanics while substituting only the QKV control/candidate worker. Rebind the worker to the exact v0.5.13 image and entrypoint and persist the new hashes before claim.

Compilation, source-boundary, and hash checks are the first operation of the next execution, not a new terminal. Once they pass, claim and run the already-admitted paired arms in that same execution. Do not create a preparation, repair, audit, or successor project; do not replay the component or MTP; and do not claim before the local controller snapshot is complete.
