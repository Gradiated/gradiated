# Gemma 4 W4 Marlin component bridge on L40S

## Decision question

Does pinned first-party vLLM Marlin WNA16 on one L40S execute every active Gemma 4 31B TP=1 text-linear shape with finite oracle-matched outputs and reduce the architecture-weighted c16 decode component p50 by at least 25% versus a matched actual pinned-vLLM online-FP8 consumer?

This is the corrected W4 economic bound's cheapest direct falsifier. It is a checkpoint-free mechanism experiment, not an endpoint, exact-W4-checkpoint, or quality result.

## Authoritative contract

Mechanically exact-match before provider creation:

- `../gemma_l40s_w4_c16_economic_bound/W4_C16_BOUND_V2.json`, SHA-256 `b697e8c43bcdecac9b0261ab79e363b39e11e9c37a0be282d357a21c9e24fe9d`;
- `../gemma_l40s_w4_c16_economic_bound/W4_COMPONENT_PACKET.json`, SHA-256 `3ac9ff0868ed63bd06bb263c78576ba8d00c67244a1ca636e82f00be65ed8aad`;
- `../gemma_l40s_vllm_fp8_consumer_bridge/IDENTITY_ASSERTION.json`, SHA-256 `8fc4a47bcb5f09783385b90d92269f57fedae86fcf2bb32e51cef41c8f612c73`;
- `../fp8_kv_contract_reconciliation/KV_CONTRACT.json`, SHA-256 `d495553dab98eac4d101802e668469fea3758ba378a8bd89641075a277a07802`;
- `../l40s_saturation_economic_gate/SATURATION_GATE.json`, SHA-256 `690e0e457c6e8e9121b54fb7f88abc92c3dcc358e1d71accffddb083878d00d6`.

Bind `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, vLLM `ab0a20d15129b322f911db578b50c6b35b3167e7`, image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, amd64 manifest `sha256:8e86cb93b724092cd4dc892fb129a6c5538613b38a5cd34e40aab9e6aea72b03`, TP=1, group size 128, BF16 activations, and one L40S SM89. No checkpoint or tokenizer download is allowed.

## Required paid experiment

Use the shared `mla_microbench_control.py` through its durable owner, absolute watchdog, typed stages, and verified cleanup. Do not add a provider/SSH wrapper. The prior controller SHA is `1c7448d956d9c65eaf64494bf3bbd16afcf813e30f57604a36affc873d23af2b`; exact-match or explain a shared upstream change before launch. The remote wrapper must emit the controller-required internal manifest as well as a typed stage terminal.

Exercise the actual installed first-party AutoAWQ/AutoGPTQ Marlin WNA16 linear method, using deterministic synthetic packed uint4 weights, group-128 scales/zero-points, and BF16 activations. In the same process and configuration context, exercise the actual installed online-FP8 linear method as the matched comparator. Direct `torch._scaled_mm`, direct Marlin extension calls that bypass the vLLM method, import/constructor-only probes, generic tensor copies, and silent fallbacks fail the bridge.

Run all six shapes at M=1/2/4/8/16, allocating and releasing one case at a time:

- `5376→16384` sliding QKV, architecture multiplicity 50;
- `5376→20480` global QKV, multiplicity 10;
- `8192→5376` sliding output, multiplicity 50;
- `16384→5376` global output, multiplicity 10;
- `5376→43008` merged gate/up, multiplicity 60;
- `21504→5376` down projection, multiplicity 60.

For each representation and case, record the concrete vLLM class/method, invoked kernel/symbol, packed layout, shapes/dtypes, deterministic seed, warmups/iterations, finite-output check, an oracle comparison against the same dequantized synthetic weights, CUDA-event and wall p50/p95, peak allocated/reserved memory, and raw GPU telemetry. Pre-register tolerances before running. Persist nonempty typed rows, identities, telemetry interval, useful-GPU seconds, and archive hashes atomically before any conditional work.

Compute the c16 active-text aggregate from measured M=16 p50s and the stated layer multiplicities. The primary mechanism gate passes only if every genuine consumer/oracle case passes and `W4 aggregate p50 <= 0.75 * matched FP8 aggregate p50`. Reconcile the measured maximum transient/allocator reserve with the corrected W4 c16 logical total of 31.158265 GiB and the 44.704-GiB envelope; label this a component fit bound, not full-model residency evidence. Translate results against the 0.717061 and 1.158355 requests/s hurdles while leaving attention, KV operations, head, scheduler, sampling, reliability, and endpoint overhead explicit.

## Final-staged-program gate

Before provider creation, audit the exact bytes that will be staged, after wrapper integration. Fail closed locally if any required shape/representation lacks a reachable execution loop, if a vLLM configuration context is absent, if placeholder or unconditional exceptions remain, if success can exit zero around a typed failure, or if result rows, stage terminal, internal manifest, telemetry, and useful-GPU fields are not mechanically required. A source/constructor smoke may support this audit but cannot replace it. Record one typed preflight artifact; do not open a readiness successor.

If correct deterministic local compilation/materialization outlives a response, keep one bounded no-provider systemd owner in this project with a 45-minute absolute deadline and typed terminal. Provider creation stays gated until it passes. Do not kill or restart correct bounded work for turn cadence.

## Adjacent retained-session arm

Image/bootstrap time has already measured roughly 531 seconds versus tens of scored seconds. Prepare one conditional BF16 `ParallelLMHead` arm from `../tied_vocab_projection_cost_bound/` while the primary owner runs, launch-ready within ten minutes. It must invoke the actual pinned vLLM tied `5376→262144` consumer at M=1/2/4/8/16 on the existing image/allocation through the same sequential owner/watchdog, with the same oracle/timing/memory/telemetry contract.

Run it only when the W4 primary mechanism gate passes and the component fit bound has not already falsified both economic envelopes. Otherwise persist the false trigger and tear down immediately. No other retention, content download, server, or successor owner is allowed.

## Stop rules and artifacts

- Any unsupported/false consumer, wrong layout/shape, nonfinite or oracle failure, under-25% aggregate reduction, or component-fit miss is a typed scientific negative and closes the line after cleanup.
- A pass only admits later consideration of one exact-producer/quality experiment; it establishes neither checkpoint quality nor endpoint economics.
- Retrieve typed primary and conditional artifacts before cleanup. Verify authenticated zero instances/disks and record actual exposure/rates/spend.
- Write `artifacts/summary.json` with identities, audit result, all rows, architecture-weighted comparison, fit/economic interpretation, useful/setup time, conditional disposition, archive hashes, spend, and cleanup proof.

## Budgets

- Wall clock: 90 minutes.
- Provider exposure: 20 minutes maximum under one sequential durable owner.
- Compute: at most 0.34 L40S GPU-hours and 4 local CPU-hours.
- Storage: one 100-GiB provider boot disk; at most 6 GiB project artifacts and temporary files, using project-local temporary storage because shared `/tmp` is full.
- Spend: at most `$0.50`, including disk. One paid allocation maximum.

## One material runtime-identity correction after the first allocation

The first allocation is terminal and clean, not a W4 result. Its content-addressed archive and summary are:

- `artifacts/gemma-w4-marlin-20260717t054054z/summary.json`, SHA-256 `97b76d3796743a32a59f48ac00b993b40f1f28387563a8caed2ec177ae00df0d`;
- `artifacts/gemma-w4-marlin-20260717t054054z/primary-w4-fp8.tar.gz`, SHA-256 `4ce13e0c208bf9b486abb4e34b416d9cfb1eac848cda1a078f68ae77d1247d20`;
- `artifacts/gemma-w4-marlin-20260717t054054z/cleanup.json`, SHA-256 `fb0dc1cf893ecba8d0719c12f24e4fb55cfb7ae22ff493f4698e62a4e0b747cd`.

The exact image reported `vllm 0.19.1.dev6+g6d4a8e6d2`, not the source revision assumed by the brief, and the hard-coded `vllm.model_executor.layers.quantization.auto_awq` module was absent. Zero case rows executed. Freeze the old source assertion as non-transferable and use the immutable image plus its observed runtime string as the corrected control; both W4 and FP8 remain contemporaneous inside that same image, so no cross-runtime delta is claimed.

Make one correction in this project. Before provider creation, interrogate the exact image in a no-GPU local container (or an equally content-bound source mechanism) to enumerate the installed quantization registry/modules, resolve the genuine supported W4 Marlin method, record its source path/hash/signatures, and execute a CPU-safe import/construction smoke. Do not assume a filename from another revision and do not add a generic fallback. Emit `artifacts/runtime-correction-terminal.json` containing the image identities, observed runtime, resolved consumer, benchmark/wrapper hashes, required nonempty-row assertions, and a typed pass/fail. If image materialization outlives a response, use one bounded no-provider systemd owner in this project with a 45-minute deadline and 50-GiB project-local temporary cap; provider create remains gated until its typed terminal passes. Do not kill or restart correct local work for turn cadence.

After that terminal passes, launch one final corrected allocation directly through the same shared controller. Keep all original six-shape, matched FP8, oracle, timing, telemetry, artifact, economic, cleanup, and conditional BF16-head requirements. This is the sole material correction: any further pre-row failure closes the lineage. The first allocation consumed 661.545 provider seconds and `$0.139462` derived cost; authenticated cleanup and a fresh director inventory are empty.

The amended total budgets supersede only the numerical limits above: 150 wall minutes, at most 40 provider minutes total with no more than 20 additional minutes, 0.68 L40S GPU-hours, 6 local CPU-hours, one provider allocation at a time and two total, one 100-GiB provider disk, 50 GiB bounded project-local temporary image storage plus 6 GiB retained artifacts, and the same `$0.50` total spend cap.

The first local correction terminal falsely classified resolution as failed because its parser stored the successful probe JSON in `raw_stdout_tail` instead of decoding the final JSON object. Preserve that failed terminal. Its content-bound `exact-image-inspection.json` (SHA-256 `62d4a8937df225c7a0c45f24c879ac3ae1c6643f950beecf7a9a31c3147d30fd`) nevertheless records the exact runtime and concrete candidates, including `vllm.model_executor.layers.quantization.awq_marlin.AWQMarlinLinearMethod` and `vllm.model_executor.layers.quantization.fp8.Fp8LinearMethod` with source hashes. Regenerate the typed terminal from the already materialized exact image with a strict final-JSON parser, require those source-bound classes plus the staged nonempty-row assertions, and patch the benchmark import. This is completion of the admitted local correction, not permission to weaken the gate or add a provider attempt. If the regenerated terminal is not a genuine pass, or the final allocation fails before nonempty rows, close the lineage immediately.
