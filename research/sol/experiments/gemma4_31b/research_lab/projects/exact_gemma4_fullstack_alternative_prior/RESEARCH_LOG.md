# Research log

## 2026-07-17 — director delegation

Activated as independent `$0` current external evidence while the paid vLLM W4 line makes one material runtime correction. Find at most one exact-model non-vLLM stack with an immediately executable cost falsifier, or close typed none. Budgets are 45 wall minutes, 1.5 CPU-hours, 1 GiB/128 MiB probes, and `$0`; no provider, weights, compilation, quality execution, or owner polling.

## 2026-07-17 — SGLang alternative retained

Question: does current primary evidence expose a non-vLLM exact-model full stack worth measuring? Action: searched current official SGLang, Transformers, TensorRT-LLM, and llama.cpp sources, then inspected the named exact W4 route and campaign economic thresholds. Evidence: SGLang Gemma 4 support merged in PR #21952 at `2813cb6d9a5b6e8fb02435647917e6f1652d7940`; its current public report uses `google/gemma-4-31B-it`, `lmsysorg/sglang:dev-gemma4`, and shows a working 31B FP8-KV serving path. The report is H20 TP2/DP4 and does not bind the target revision, digest, 4214/358 mix, 10K arm, cost, or quality. Transformers documents the exact Gemma4 architecture; llama.cpp evidence remains bug-/fork-oriented and TensorRT-LLM evidence is usage/documentation support without an exact matched result.

Interpretation: retain exactly one conditional SGLang BF16+FP8-KV alternative because it changes engine and avoids the vLLM consumer-binding failure; do not transfer H20 performance. The immediate falsifier, content bindings, same-hardware comparator, `<=0.90x` cost gate, 1.825 req/s H100 market floor, and raw-output/feature quality gate are recorded in `ALTERNATIVE_PRIOR.json`. No GPU, provider, weights, compilation, or quality execution occurred. Next move: only a later authorized matched endpoint/component owner may execute this packet; otherwise its hard negative is typed `none`.
