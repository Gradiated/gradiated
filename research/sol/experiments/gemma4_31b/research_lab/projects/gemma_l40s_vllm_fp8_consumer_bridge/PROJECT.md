# Gemma 4 31B pinned-vLLM FP8 consumer bridge on L40S

## Decision question

Can the pinned vLLM online-FP8 and FP8-per-token-head runtime methods execute Gemma 4 31B's actual TP=1 sliding/global attention and dense-MLP shapes on one L40S with finite, bounded-error outputs and component timing that does not already falsify the campaign's L40S economics?

This is the shortest actual-consumer bridge after the generic CUDA microbenchmark. It is not an endpoint, checkpoint-quality, or sustainable-throughput result.

## Why now

The corrected predecessor is terminal and clean, but its “exact-shape” claim is invalid. Pinned vLLM source constructs fused QKV and merged gate/up modules whose dimensions are larger than the standalone matrices tested, and its KV result used a PyTorch conversion rather than the runtime cache writer. Another generic `torch._scaled_mm` repair would not close the consumer gap. Full checkpoint endpoint staging, meanwhile, has twice consumed roughly two hours without a request.

## Authoritative identities and evidence

Consume `IDENTITY_ASSERTION.json` in this project and exact-match it before provider creation. The contract is mechanically extracted from:

- `../exact_bf16_mtp_h100_frontier/artifacts/preflight-20260717T000000Z/hf-config.json`
- `../exact_geometry_runtime_opportunities/GEOMETRY.json`
- `../fp8_l40s_fit_economic_falsifier/FP8_L40S_PACKET.json`
- `../fp8_kv_contract_reconciliation/KV_CONTRACT.json`
- `../l40s_saturation_economic_gate/SATURATION_GATE.json`
- `../gemma_l40s_fp8_exact_shape_microbench/artifacts/gemma-l40s-fp8-corr-20260717t000000z/summary.json`
- pinned first-party source `vllm/model_executor/models/gemma4.py` at revision `ab0a20d15129b322f911db578b50c6b35b3167e7`

Bind the model to `google/gemma-4-31B-it` revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, runtime image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, amd64 manifest `sha256:8e86cb93b724092cd4dc892fb129a6c5538613b38a5cd34e40aab9e6aea72b03`, TP=1, and the campaign's 4,214-input/358-output primary plus 10K single-stream geometry. No checkpoint, tokenizer, or server is needed for this component experiment.

## Required experiment

Use `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py` directly with `gpu-l40s-a`, `1gpu-8vcpu-32gb`, a lowercase name, and the exact image above. Reuse its durable owner, watchdog, authenticated retrieval, and verified cleanup; do not create a project-local provider/SSH wrapper.

After one focused local typed preflight, run actual pinned-vLLM quantized linear modules/methods, not a direct `torch._scaled_mm` substitute. The researcher may choose the narrowest construction that truthfully exercises the installed runtime consumer. Record module class, quantization method/config, loaded weight layout, invoked symbol/kernel, input/output shapes, dtypes, seeds, warmups, iterations, numerical comparison, CUDA-event and wall timings, memory, and GPU telemetry.

Minimum TP=1 cases, derived from config plus pinned source:

- sliding QKV: `M x 5376` by `5376 x 16384`, where `16384 = 32*256 + 2*(16*256)`;
- full/global QKV: `M x 5376` by `5376 x 20480`, where `20480 = 32*512 + 2*(4*512)` even though checkpoint K is duplicated for V;
- sliding output: `M x 8192` by `8192 x 5376`;
- global output: `M x 16384` by `16384 x 5376`;
- merged gate/up: `M x 5376` by `5376 x 43008`;
- down: `M x 21504` by `21504 x 5376`.

Use `M=1,2,4,8,4214` where memory permits, and preregister any bounded tiling needed for the prefill case without changing the consumer or claiming a monolithic timing. Exercise the actual runtime FP8-per-token-head cache-write/read path for one source-derived local layer and one global layer at primary c8 geometry; record exact symbol, cache/scale layout, numerical error, and allocated/peak memory. A tensor conversion or `copy_` fallback is a failed consumer bridge, not a pass.

Independently persist each decision-bearing stage before optional work. Report useful-GPU seconds explicitly. Translate timings only into an optimistic component lower bound against 0.717061 completed requests/s planning-base and 1.158355 conservative; missing attention, scheduling, sampling, output-head, and endpoint work must remain explicit.

## One admitted shared-controller correction

`artifacts/preflight-20260717T045840Z.json` passed every immutable identity and shape check, then correctly stopped before provider creation because the named custom-input controller is foreground/single-arm and cannot evaluate the conditional retained arm. This is a controller-semantic blocker, not an FP8 result and not a reason to open a support successor.

The director authorizes one narrow reusable extension to `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py` within this project. Starting from recorded SHA-256 `354ee04bd4d98c39d0c39b159aa3bace2548bda4f3cb7653fa50d6762de70a68`, add only the semantics needed here:

- a real durable systemd owner gate for provider mutation and one absolute cleanup watchdog;
- ordered primary and conditional script inputs on one instance, with atomic retrieval and a typed primary terminal before trigger evaluation;
- the named `ParallelLMHead` true branch and immediate verified cleanup on the false branch;
- independently hashed stage artifacts, useful-GPU/setup timing, final typed summary, and zero-resource cleanup proof.

Add narrow shared behavioral tests for owner rejection, primary artifact preservation, true-branch sequencing, false-trigger cleanup, and unconditional cleanup on error. Do not create a project-local provider wrapper or general workflow framework. If implementation or deterministic tests outlive a response, run them under one bounded local systemd owner in this project with a 45-minute absolute deadline, no provider credentials/mutation, and terminal `artifacts/controller-terminal.json`; provider creation remains gated until that typed terminal and the refreshed immutable preflight both pass. Once they pass, continue directly to the already admitted GPU experiment under the same project and budgets—do not wait for another director turn.

## Adjacent retained-session arm

Measured image/bootstrap time is expected to exceed scored component time, so prepare one cross-project conditional arm from `../tied_vocab_projection_cost_bound/` offline while the owner runs. It must be launch-ready within ten minutes and use only the existing image-bound allocation plus the same sequential owner/watchdog.

The arm invokes pinned vLLM's actual BF16 `ParallelLMHead` consumer for the tied `5376→262144` projection at `M=1,2,4,8` (and `M=16` only if already within memory/time), recording the same symbols, shapes, timings, memory, and telemetry. The predecessor's generic M=1 row is only a prior: at 3.862 ms/token it would consume about 1.383 seconds across 358 decode tokens before any other work, so c8 amortization is a decision-relevant economic unknown despite the projection's small whole-request FLOP share.

Run this adjacent arm only if every primary actual FP8 linear/cache consumer passes and the primary component lower bound has not already falsified both economic envelopes. If the trigger is false, record it and tear down immediately. Do not retain for any other arm, download content, start a server, or create a successor owner.

## Decision and stop rules

- Pass only if every required runtime consumer is genuine, every required shape is correct, outputs are finite and within preregistered BF16-reference tolerances, and the optimistic component lower bound does not already exceed the economic service-time envelope.
- Any unsupported actual vLLM consumer, silent generic fallback, wrong shape, non-finite/error failure, or lower-bound economic miss is a scientific negative. Do not repair it with another generic matrix benchmark.
- If a genuine consumer requires deterministic local compilation/materialization longer than one response, keep one bounded durable local owner in this project and keep provider creation gated until its typed terminal passes. Do not kill correct work for turn cadence.
- No model download, endpoint, or quality claim. The only adjacent work is the named same-session BF16 `ParallelLMHead` arm above; it adds no allocation and must not be replaced. This project is scientifically different from the predecessor and must not be used to evade its no-third-allocation rule.
- On any terminal, retrieve typed artifacts and verify zero provider instances/disks.

Write `artifacts/summary.json` with the immutable identities, exact source-derived dimension audit, consumer symbols/classes, numerical/timing/memory rows, useful versus setup time, the tied-head trigger/disposition, economic lower-bound interpretation, spend, archive hashes, and cleanup proof.

## Budgets

- Wall clock: 75 minutes, including the one controller correction and any bounded local owner.
- Provider exposure: 20 minutes maximum under one sequential durable owner.
- Compute: at most 0.34 L40S GPU-hours and 3 local CPU-hours.
- Storage: 100 GiB provider boot disk; at most 4 GiB retained artifacts.
- Spend: at most `$0.50` including disk; record actual provider-metered rates separately from the `$1.10/GPU-hour` production planning rate.
