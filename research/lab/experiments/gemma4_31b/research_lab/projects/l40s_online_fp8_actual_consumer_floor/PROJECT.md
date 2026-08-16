# L40S online-FP8 actual-consumer floor

## Decision question

At the exact Gemma 4 31B TP=1 shapes and campaign workload, do the actual pinned-vLLM online-FP8 linear producer/consumer, FP8 KV writer, and actual BF16 tied head on one L40S leave enough whole-request room to justify one later exact-revision quality/endpoint test?

This is the shortest missing scientific result after two earlier L40S consumer lineages ended before timing rows. It is checkpoint-free and cannot establish checkpoint quality, endpoint throughput, or production eligibility.

## Mechanically bound identity and evidence

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning, TP=1.
- Runtime: `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, observed vLLM `0.19.1.dev6+g6d4a8e6d2`.
- Primary workload: 4,214 input / 358 output with 12.7% cache reads and 3,678.822 fresh prompt tokens. Separate sensitivity: 10,000 input / 358 output at c1; it is not substituted into the primary market gate.
- Machine binding: `primary_input_tokens=4214`, `primary_output_tokens=358`, `aa_input_tokens=10000`.
- Exact six linears: sliding QKV `5376->16384` x50; global stock-runtime QKV `5376->20480` x10; sliding output `8192->5376` x50; global output `16384->5376` x10; merged gate/up `5376->43008` x60; down `21504->5376` x60.
- Primary consumer: exact-image `vllm.model_executor.layers.quantization.fp8.Fp8LinearMethod`, source SHA-256 `1d6ef3182fb5c72808414cdf14177131121f2b8fb6e94012696f0fdde4f74c48`, using its real `create_weights` / post-load processing / `apply` path with required current-vLLM config context. No direct `torch._scaled_mm` or generic fallback.
- Conditional consumer: exact-image `vllm.model_executor.layers.quantization.awq_marlin.AWQMarlinLinearMethod`, source SHA-256 `721bb23b98cd678232b87a24757317cc9066bfa13f983ca2bf71a3afbaf6ed97`.
- L40S planning-base hurdle `0.7170614380702235 completed requests/s`, whole-service ceiling `1.3945806410831811 seconds/request`; conservative hurdle `1.1583551336753017 requests/s` and ceiling `0.8632929962 seconds/request`.

The director-generated `artifacts/DIRECTOR_IDENTITY_ASSERTION.json` must pass before delegation and binds the authoritative source artifacts/hashes, including deduplication of the earlier repeated identical FP8 discovery record. No checkpoint or model weights are allowed.

## Immediate actual FP8 experiment

Use the proven shared Nebius `mla_microbench_control.py` lifecycle and the same lowercase L40S placement path that produced the valid actual `ParallelLMHead` rows. Do not add a project-specific provider framework. One user-systemd durable owner plus independent watchdog must own the allocation through typed retrieval and authenticated cleanup. A final behavioral audit must bind the exact bytes and transitive lifecycle dependencies the owner will consume, and mechanically reject placeholders, empty row loops, missing vLLM config context, generic fallbacks, disconnected producer/timer paths, absent oracle consumption, incorrect aggregation, and success around typed failure. Any pre-GPU or zero-row terminal closes without repair.

Sequentially create deterministic synthetic BF16 source weights for one exact shape at a time, let the actual online-FP8 method produce/process its consumed weights, and measure its actual `apply`. Use matched actual BF16 linear consumers with identical shapes/activations/order as the scientific comparator. Required geometries:

- decode M=12 and M=14 for all six shapes;
- fresh-prompt prefill M=3,679 for all six shapes, with bounded tiling only if the same actual consumer and exact total are preserved; M=8,730 is a separate 10K sensitivity;
- actual BF16 `ParallelLMHead` at M=12/M=14 for 358 logits;
- actual pinned-vLLM FP8 KV-cache writer at exact local/global head shapes and primary contexts, plus 10K c1 sensitivity.

Require preregistered BF16-reference tolerances that consume the timed output, finite/nontrivial tensors, concrete method/kernel/source identities, CUDA-event and synchronized-wall raw distributions, warmups/stability, allocator peaks, HBM/power/utilization telemetry, and exact stage manifests. Architecture-weight linears by 50/10/60 layer counts. Prefill work is seconds/request and is never divided by decode concurrency; decode batch work across 358 steps is divided by M once. Add only disjoint head and KV-write work. Name all omitted attention, norms/rotary/activation, sampling, scheduler, queue, reliability, and service overhead.

Classify c12/c14 against both L40S whole-service ceilings. `FP8_COMPONENT_ADMISSION` passes only if all required actual rows/oracles pass, measured allocator telemetry fits the 44.704-GiB envelope, and at least one fitting point leaves a positive named residual; a residual of at least 0.35 seconds/request under the planning ceiling is the strong pass that skips W4. A valid smaller residual is decision-relevant but triggers the adjacent comparison. No component pass is an endpoint or quality claim; a later endpoint would require exact-revision raw captures and the campaign quality consumer against BF16.

## Conditional same-session W4 arm

Prepare before provider create the actual W4 program for the same six shapes, deterministic group-128 asymmetric packed weights, dequantized BF16 oracle, M=14/M=16, identical timing/telemetry, and matched same-session FP8/BF16 comparators. `W4_RESIDUAL_TRIGGER` requires: a valid nonzero FP8 scientific terminal; FP8 either exceeds the planning ceiling or leaves under 0.35 seconds/request; W4 is start-ready within ten minutes; at least ten provider minutes remain; and the retained session/owner/watchdog are unchanged. Invalid/zero-row FP8, a strong FP8 pass, missed readiness/deadline, or any ownership mismatch forces immediate cleanup.

Run W4 sequentially on the retained allocation only. It is a semantics-changing mechanism proxy. Close it unless every actual Marlin row/oracle passes, its architecture-weighted component time is at least 20% below matched online FP8, and the c16 disjoint component floor is at most 0.60 seconds/request. Passing only nominates exact-revision producer/quality work. No second allocation, checkpoint, server, MTP, or other retained arm is authorized.

## Budgets and terminal

- Primary slice: 35 wall minutes, 25 provider minutes, 0.42 L40S GPU-hours, 2 local CPU-hours, `$0.40`.
- Conditional incremental slice: 12 wall minutes, 10 provider minutes, 0.17 L40S GPU-hours, `$0.17`.
- Combined hard caps: 50 wall minutes, 35 provider minutes, 0.59 L40S GPU-hours, 3 local CPU-hours, one 100-GiB disk, 768 MiB retained plus 3 GiB temporary, `$0.57`, one allocation, no paid repair.

Write the identity assertion, exact-image probe, final program audit, owner/watchdog snapshot, raw FP8/BF16 and conditional W4 rows, oracle/telemetry/manifests, typed triggers, provider/useful/cost accounting, `artifacts/SUMMARY.json`, concise log/status, and authenticated zero-resource cleanup.
