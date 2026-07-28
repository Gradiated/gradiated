# Research log

## 2026-07-18 — content-bound pre-create runner passes locally

Question: can the admitted five-case greedy-generation discriminator be made execution-ready without changing the frozen safe-code request, adapter, or strict scorer?

Action: added `generation_equivalence_runner.py`. Its `generate` mode tokenizes each transformed request once, feeds those exact IDs to direct BF16 Transformers and SGLang's `prompt: list[int]` path with `add_special_tokens:false`, persists each raw request/response plus output IDs/text/finish reason, runs the bound adapter and strict executable scorer, and records the first generated-token divergence. Its local mode validates all frozen source identities and exercises the same five-case adapter/scorer boundary with typed token-ID records.

Evidence: `artifacts/precreate-terminal/LOCAL_VALIDATION.json` passes all five fixture rows with equal token IDs and strict scores of 1.0 for both consumers. `artifacts/precreate-terminal/TERMINAL.json` is a typed `ready_for_director_bench_request` terminal with zero provider spend; `artifacts/director-bench/BENCH_REQUEST.json` requests one director-owned H200 bench, 250 GiB disk, and no researcher provider mutation. The shared pool was checked and has zero benches.

Interpretation: local preparation is complete, but this is not a model-quality result: the local outputs are explicitly fixtures. The next decision-bearing action is one bounded H200 execution using the exact checkpoint/image.

## 2026-07-18 — final SGLang endpoint-stall terminal

Measured: the final SGLang-only consumer used the pinned image and content-validated checkpoint with `context_length=5000`, `max_total_tokens=1024`, one request, BF16 KV, `mem_fraction_static=0.85`, CUDA graphs enabled, and only `--skip-server-warmup` added. It reached `/v1/models` successfully, but the first frozen `input_ids` `/generate` call produced no response or SGLang row artifact and remained in-flight until cancelled. The retained server logged the disconnected-request abort. This satisfies the director's final endpoint-stall stop rule; no further repair, setup replay, or direct rerun is admitted.

The preserved direct capture has five rows: `heldout_ordering` strict score 0 and each code control score 1. Because no SGLang generation completed, this closes the runtime-quality route without a model-quality conclusion. Evidence: `artifacts/h200-generation-equivalence-20260718t1318z/FINAL_SGLANG_ENDPOINT_STALL_TERMINAL.json`, `transformers_raw.json`, and `final_sglang_endpoint_stall.log`.
