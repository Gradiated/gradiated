# Workload-grounded vocabulary-shortlist gate

## Question

Do the retained raw responses from the valid current-AWQ target identity supply representative token-usage evidence for a small output-vocabulary shortlist whose recoverable head-cost mechanism can conservatively bridge `552.171055` to `594.466` output tok/s on L40S?

## Why this matters

The output-head project explicitly closed pending a usage-grounded shortlist. Its exact 154,880-by-2,048 BF16 head has diffuse singular energy, but the retained c8 trace assigns a `14.09%` interval-union ceiling to vocabulary projection. Since then, the lab retained request-complete current-AWQ archives and raw quality/semantic responses. A real workload token distribution could reopen a static or hierarchical shortlist; conversely, discovering that only hashes/timing rows exist for the 1,024-token performance streams would close this condition without GPU spend.

## Fixed evidence

- Current denominator and target: r3 c16 `552.1710554232396` output tok/s versus `594.466`, requiring `7.1148%` non-overlapped wall-time removal at `$1.10/hour` and `$0.514/M`.
- Prior head evidence: `../output_head_architecture/HEAD_SPECTRUM_PROXY.json`, `DECISION_2026-07-15.json`, and the exact BF16 head/index binding. Factorization and norm-ranked shortlists remain closed.
- Candidate raw-response sources are limited to valid stock current-AWQ archives, beginning with `../near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/vllm-awq-batch.tar.gz` and `../nebius_current_awq_c16_direct/artifacts/nebius_current_awq_c16_direct_2026-07-15-r2/vllm-awq-batch.tar.gz`. Exclude exit-35 and other semantics-changing candidates from stock token usage. Hash-only streams are not token evidence.
- Bind the exact tokenizer bytes and distinguish target 8K/1K performance traffic from development-quality, semantic, and methodology prompts. Deduplicate repeated prompts/responses before reporting coverage.
- The old `14.09%` head interval is from a different c8/128 trace and is an optimistic ceiling, not a c16/1,024 wall-time share.

## Scope and stop rule

Within 900 seconds, 10 GiB RSS, 64 MiB new artifacts, and `$0`, inventory all retained stock current-AWQ artifacts that actually contain raw response text or output token IDs. Tokenize only those responses with the content-bound tokenizer, report unique prompts/responses, total/unique tokens, source/category weights, and missingness relative to the authoritative target workload. Build frequency-ranked shortlist curves at practical tensor-friendly sizes and stress them with leave-one-prompt and leave-one-category-out coverage. Do not treat development-suite outputs or repeated methodology prompts as representative target traffic without evidence.

For the smallest defensible candidate, quantify changed head rows/bytes/FLOPs, exact L40S GEMM shapes, memory effect, ideal component reduction, the endpoint reduction required, and recovery/runtime burden. A static shortlist is semantics-changing unless an exact fallback is defined; do not claim exactness from observed coverage. Do not reuse row norms, run broad evaluation, train, download data, inspect unrelated providers, or invent unretained performance tokens.

Return exactly one terminal result:

- `NOMINATE_SHORTLIST_PROXY`: a target-representative, deduplicated corpus supports at least `99.9%` leave-one-group-out coverage, an exact source-bound tensor/runtime representation exists, and a conservative endpoint-transfer stress still reaches the 2%-margin threshold `606.355` tok/s;
- `CORPUS_CLOSE`: retained raw outputs are too small, biased, duplicated, or mismatched to support the target workload; or
- `ECONOMIC_CLOSE`: coverage/representation is adequate, but the conservative cost path misses the gate.

Do not use CUDA, network/provider resources, mutate checkpoints or shared launchers, prepare a controller, or run a paid experiment. Produce one compact machine-readable inventory/decision artifact, any focused local script, and a concise research-log entry.

