# Exact Gemma 4 full-stack alternative prior

## Decision question

Is there one current, reproducible non-vLLM full-stack route for the exact Gemma 4 31B checkpoint that could reach a complete-request cost result materially faster or cheaper if the corrected vLLM W4 consumer fails?

## Scope

Search current primary evidence for exact-model support and measurements in SGLang, TensorRT-LLM, Transformers/Accelerate, llama.cpp-derived stacks, vendor recipes, or reproducible public studies. Bind checkpoint/revision, representation, tokenizer/chat template, runtime commit/image, hardware/topology, input/output geometry, concurrency, quality boundary, throughput/latency, and measurement date. Separate exact-model evidence from Gemma-family or hardware-only priors. Use the campaign's 4,214/358 plus 12.7% cache mix and separate 10K single-stream view to normalize any usable result; do not infer throughput from nominal hardware.

Return at most one alternative with an immediately executable component or endpoint falsifier, content-addressed inputs, an explicit comparator and market threshold, and a later raw-output/feature quality gate. Nominate only if it changes engine, representation, or hardware in a way plausibly worth at least 10% all-in cost or avoids the repeated vLLM consumer-binding failure. Otherwise emit typed `none`. Do not propose another source/admission project, and do not mutate or wait on the paid owner.

Shared accelerator prices are fresh; do not repeat their search. Search only stack/model evidence or a missing candidate-specific rate/topology when essential.

## Budgets and artifacts

- Wall clock: 45 minutes.
- Compute: 1.5 local CPU-hours; no GPU.
- Storage: 1 GiB project-local, including at most 128 MiB bounded public/source probes; no shared `/tmp`.
- Spend: `$0`; no provider mutation, full weights, compilation, or quality execution.

Write `ALTERNATIVE_PRIOR.json`, concise `DECISION.md`/`RESEARCH_LOG.md`, and terminal `STATUS.json`.
