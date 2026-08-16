# Exact Gemma 4 SGLang versus vLLM on H200

## Decision question

Can the content-bound SGLang BF16 plus FP8-E5M2-KV route beat a matched pinned-vLLM BF16 control by at least 10% in sustainable completed-request cost on one H200 while also clearing the campaign market hurdle with valid raw outputs and reliability?

The immutable one-H100 SGLang command is closed: its source-defined multimodal static pool is 2.399 GiB below the exact checkpoint before c1 KV. H200's 141-GB memory is the shortest full-stack route that removes that capacity failure. The L40S tied-head result separately closes single-stream economics but preserves c8-c32 background batching; it is not a full endpoint or a throughput transfer.

## Mechanically bound identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning.
- Exact config/tokenizer/template hashes: consume `../sglang_gemma4_exact_precreate_binding/START_PACKET.json`; exact-match every listed file before provider create.
- Candidate source commit `2813cb6d9a5b6e8fb02435647917e6f1652d7940` and image `docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427`, amd64 child `sha256:93379b0bc29b5724c6b5b787020eb9803d80e4ce17fabbccad62108c4164e318`.
- Control image `vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`; target BF16 weights and default control KV are the comparator, while SGLang FP8-E5M2 KV is part of the candidate intervention.
- Workloads: primary 4,214 input / 358 output with 12.7% prompt-cache reads under simultaneous background concurrency, plus 10K-input/358-output single stream kept separate.
- Hardware: Nebius `gpu-h200-sxm`, `1gpu-16vcpu-200gb`, one H200 141GB, one 250-GiB disk, lowercase RFC-1123 name, preemptible when the authenticated catalog/rate permits.
- Production H200 planning rate `$3.25/GPU-hour` with `$2.925-$3.60` range; experiment accounting uses the authenticated current meter. Shared prices are fresh.

Before activation, mechanically compare this brief to the two named JSON packets and emit `artifacts/IDENTITY_ASSERTION.json`; any mismatch is resolved in this project before provider creation, never by weakening a gate.

## Bounded local materialization and owner

Materialize or reuse the exact checkpoint/tokenizer locally with immutable revision and shard/header hashes. If correct local work outlives a response, use one no-provider user-systemd owner in this project with a 70-minute deadline, 90-GiB project-local storage cap, and terminal `artifacts/CHECKPOINT_TERMINAL.json`. Provider creation remains gated until that terminal, the identity assertion, a final rendered-program audit, authenticated empty inventory, H200 placement/rate, and both image manifests pass. Do not kill or restart correct staging for turn cadence.

Use one narrow scientific owner that calls the proven shared Nebius lifecycle primitives in `placement_control.py`, `vllm_smoke_control.py`, and `stock_control.py`: `VerifiedRetainedOwner`, diagnostic-bearing create reconciliation, SSH/transfer, one independent cleanup watchdog, typed retrieval, and authenticated cleanup. Adapt only placement plus the two content-bound runtime commands; do not build a general controller framework or duplicate lifecycle logic.

## One paid matched experiment

Reuse one resident checkpoint and allocation sequentially. Run:

1. SGLang candidate at primary c1/c4/c8/c16, adding c32 only if allocator and deadline headroom remain valid; preserve true simultaneous requests.
2. SGLang 10K/358 single stream.
3. Matched vLLM control at the same primary ladder and 10K/358 single stream, with identical model/tokenizer/template, prompt bytes, stop IDs, seed/sampling, hardware, and completion accounting.

For each arm retain raw submitted bytes/token IDs/hashes, serialized responses and output IDs where exposed, served-model identity, complete requests/failures/reloads, prefill/decode/request wall time, TTFT, inter-token latency, queueing, effective cache-read tokens, HBM/allocator state, GPU utilization/power, provider-active and useful-GPU seconds, and actual GPU/disk cost. Persist and retrieve each engine's decision-bearing artifacts before starting the next runtime.

Promotion requires all of:

- SGLang sustainable cost/request `<=0.90x` matched vLLM at a valid saturation point;
- campaign-mix market cost no worse than the strict `$0.000614-$0.000621` frontier under the `$3.25/hour` planning case and the measured all-in factors, interpreted through the corrected identity-bound `../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json`; the inherited `1.825` requests/s value is not an H200 market gate;
- deterministic raw-output IDs match where exact greedy equivalence applies, with no worse parser/stop behavior, failures, or reloads;
- primary and 10K views remain separately reported.

Otherwise the candidate is a typed negative. Do not claim H100 or H200-vs-H100 throughput, production quality, vision, or reasoning support.

## Adjacent conditional prefix arm

Because checkpoint/image setup will dominate scored work, prepare the already ranked `../prefix_cache_primary_mix_bound/PREFIX_ARM_PACKET.json` while the owner runs. It may execute only after the mandatory vLLM control is healthy, its exact baseline reports prefill wall share `>=0.393755`, every packet raw metric is available, and the final on/off program is audited/start-ready within ten minutes without extending the absolute owner deadline. Use the same vLLM runtime, checkpoint, allocation, sequential owner, and watchdog. If any trigger is false, record it and clean up immediately. No other retained arm is authorized.

## Budgets

- Wall clock: 150 minutes including bounded local materialization and cleanup.
- Provider exposure: 90 minutes maximum under one sequential owner.
- Compute: 1.5 H200 GPU-hours and 3 local CPU-hours.
- Storage: one 250-GiB provider disk; 90 GiB local checkpoint/temp and 10 GiB retained artifacts; no shared `/tmp`.
- Spend: `$5.00` maximum including disk/IPv4; one allocation.

Write the identity/checkpoint/final-program terminals, engine artifacts, prefix trigger/disposition, `artifacts/SUMMARY.json`, concise log, and terminal status.
