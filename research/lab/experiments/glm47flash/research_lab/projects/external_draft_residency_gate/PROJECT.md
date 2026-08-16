# External-draft residency and economics gate

## Question

Does an existing compact GLM-family draft checkpoint share the exact target token space, fit beside the full current-AWQ target on one L40S at c16, and have a conservative verified-decoding path to at least `606.355` output tok/s?

## Why this matters

The live n-gram arm proposes without draft weights, but it does not decide whether a learned external draft is viable. Target verification would preserve model quality if token identity and runtime semantics hold. The strongest current residency evidence is adverse: the exact native one-layer MTP payload is only `1.543 GiB`, yet target plus MTP reached `44.22 GiB` in use on a `44.39-GiB` visible device and failed the c16 workload while requesting another `562 MiB`; its observed acceptance was also only `0.0–2.1%`. An external draft is a materially different proposal model, but it deserves no GPU work unless a real tokenizer-compatible candidate survives a stricter combined weight/KV/activation/runtime memory bound and an evidence-backed acceptance/cost gate.

## Fixed evidence

- Exact target: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`.
- Workload: target-verified, cache-off 8,192 input/1,024 output, 32 complete requests, c16, 300-second envelope, thinking disabled.
- Economics: L40S planning rate `$1.10/hour`; ordinary `594.466` and robust nomination `606.355` output tok/s; r3 c16 denominator `552.1710554232396` output tok/s.
- Native-MTP terminal evidence: `../derived_runtime_mtp_binding/`, especially `artifacts/derived_runtime_native_mtp_2026-07-15-r1/reconciliation.json` and its archived server logs. Treat the `1.543-GiB` payload, `44.22-GiB` in-use state, `167.38-MiB` free state, failed `562-MiB` allocation, and near-zero acceptance as measured scope-specific constraints.
- Consume `../mtp_acceptance_bound/`, `../current_awq_mtp_layer/`, and `../ngram_speculative_c16_direct/` as fixed evidence. Do not reopen native MTP or tune the live n-gram arm.

## Scope and stop rule

Within 900 seconds, 8 GiB RSS, 64 MiB new artifacts, and `$0`, inspect at most two existing public compact GLM-family draft candidates, smallest credible candidate first. Use official repository metadata, configs, tokenizer assets, file manifests/headers, and pinned vLLM source; do not download full weights. Fail fast through:

1. exact token-ID compatibility with the target: vocabulary size and every available token/special-token mapping must bind, with no tokenizer translation or retokenization layer;
2. stock pinned-runtime support for target-plus-external-draft speculative decoding and the candidate architecture/representation, without source patches, training, conversion, CPU offload, or a second target copy;
3. a conservative c16 residency bound covering draft weight bytes, its KV state at the exact 9,216-token horizon, activations, graph/workspace/runtime allocations, and fragmentation/safety headroom, reconciled against the measured MTP OOM rather than nominal 48 GB;
4. proposal cost plus acceptance evidence strong enough to lower the r3 endpoint wall time conservatively and reach `606.355` output tok/s; and
5. target-verification, reasoning-off, deterministic/semantic, complete-request, and 300-second-envelope compatibility.

Do not transfer acceptance or speed from another target, tokenizer, workload, context, GPU, runtime, or draft representation. A shared tokenizer and physical fit are necessary but insufficient. If admission survives but no scope-matched acceptance evidence exists, return `UNIDENTIFIABLE` and state the sole later measurement; do not nominate from parameter count or generic speculative-decoding gains.

Return exactly one terminal result:

- `NOMINATE_EXTERNAL_DRAFT_AB`: one named unchanged candidate survives identity, runtime, robust residence, and conservative `606.355`-tok/s gates; state one later matched candidate-only endpoint but do not prepare it;
- `IDENTITY_CLOSE`: no inspected compact candidate has exact token-ID compatibility;
- `RUNTIME_CLOSE`: an identity-compatible candidate lacks an unchanged pinned-runtime path;
- `MEMORY_CLOSE`: every admitted candidate fails conservative target-plus-draft c16 residence;
- `ECONOMIC_CLOSE`: an executable resident candidate has conservative evidence below `606.355` tok/s; or
- `UNIDENTIFIABLE`: technical admission survives but acceptance/performance cannot be bounded conservatively.

Do not use CUDA, load or convert weights, edit shared code, access credentials, mutate a provider, prepare a controller, train a draft, or spend money. Produce one compact JSON and a concise research-log result.

## Available resources

Use official candidate repositories and pinned runtime source, the fixed project artifacts above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
