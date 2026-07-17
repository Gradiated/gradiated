# SGLang exact Gemma 4 pre-create binding

## Decision question

Can the completed conditional SGLang prior be converted at `$0` into one content-bound, locally validated paid falsifier for the exact Gemma 4 31B checkpoint, or should the alternative close before GPU spend?

This is independent successor planning while the vLLM tied-head owner runs. It cannot poll, delay, mutate, or spend on that owner. It is not an endpoint result and must not repeat a broad stack search.

## Authoritative inputs

- `../exact_gemma4_fullstack_alternative_prior/ALTERNATIVE_PRIOR.json` and `DECISION.md`.
- Exact checkpoint `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning.
- Primary workload 4,214 input / 358 output with 12.7% prompt-cache reads; separate 10K-input single-stream arm.
- Current market hurdle `$0.000614–$0.000621` per request and packet gates of at least 1.825 completed requests/s on the H100 planning case plus SGLang cost/request `<=0.90x` a matched same-hardware vLLM control.
- Candidate source support commit `2813cb6d9a5b6e8fb02435647917e6f1652d7940` and candidate image tag `lmsysorg/sglang:dev-gemma4`.

## Required `$0` work

Resolve and retain the current immutable image manifest/digest without pulling full layers. Bind either the named support commit or one later immutable SGLang commit that contains Gemma 4 tests, and mechanically inspect the exact model/config path, shared-KV handling, BF16 weight loading, FP8-E5M2 KV option, tokenizer/chat-template path, reasoning-off behavior, TP=1 H100 fit assumptions, request identity/served-model alias, raw-output capture, telemetry hooks, and both workload geometries. Bind the exact Hugging Face revision plus tokenizer/config file hashes with metadata/manifests only; do not download weights.

Use a bounded source checkout or registry/source API probes as needed. Run only CPU-safe import/config/CLI validation that fits the storage cap; no container-layer pull, compilation, model materialization, CUDA, endpoint, or quality execution. Compare the resulting command and artifact contract mechanically with the matched pinned-vLLM control and the prior's economic/quality gates.

Return exactly one of:

- `START_PACKET.json`: immutable engine/image/model/tokenizer identities, exact commands/configs for both SGLang arms and matched vLLM control on one H100 80GB topology, 1,200-second allocation deadline per sequential arm or a stricter justified bound, telemetry/raw-output/cleanup contract, current experiment-rate source, explicit wall/compute/storage/spend proposal, and typed pre-create negative gates; or
- `NONE.json`: the first exact incompatibility or missing immutable binding that makes a paid comparison premature.

Do not nominate L40S or transfer the public H20 performance. Do not create another discovery or readiness successor. No provider mutation is authorized.

## Budgets

- Wall clock: 50 minutes.
- Compute: 2 local CPU-hours; no GPU.
- Storage: 2 GiB project-local, including at most 512 MiB bounded source/metadata probes; no shared `/tmp`.
- Spend: `$0`; no provider, full weights, full image layers, compilation, or quality execution.

Write the one typed terminal, concise `DECISION.md`/`RESEARCH_LOG.md`, and terminal `STATUS.json`.
