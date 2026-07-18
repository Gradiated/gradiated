# H200 c32 prefill peak-compute floor

## Decision question

At the campaign workload and exact Gemma 4 geometry, how much of the c32 whole-service budget is consumed by compulsory fresh-prompt prefill arithmetic even if one H200 sustains its full dense BF16 tensor-core peak? Combine only this disjoint prefill floor with the measured c32 decode linears plus head, and determine whether c32 is already closed or how little budget remains for decode attention, prefill attention, residual operators, scheduling, and service overhead.

This is an independent `$0` analytical project. It must not poll, edit, or delay `h200_c32_actual_attention_residual_floor`, and it has no provider authority.

## Bound scope

- Exact model/revision: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, TP=1, BF16, stock pinned-vLLM geometry.
- Campaign request: 4,214 prompt tokens, 358 output tokens, authoritative 12.7% prompt-cache fraction, hence 3,678.822 fresh prompt tokens/request. Preserve a separate exact-block-cache sensitivity at 528/4,214 only; do not silently replace the campaign mix.
- Exact executed transformer linears per prompt token: 50 sliding layers with QKV `5376->16384`, output `8192->5376`, gate/up `5376->43008`, down `21504->5376`; 10 global layers with stock-runtime QKV `5376->20480`, output `16384->5376`, and the same MLP shapes. Use two FLOPs per dense multiply-accumulate and show integer parameter/FLOP totals.
- Reconcile geometry against `../exact_geometry_runtime_opportunities/GEOMETRY.json` and the executed shapes in `../h200_bf16_exact_linear_floor/artifacts/RECONCILED_TERMINAL.json`; bind hashes in the terminal.
- Bind the current H200 SXM dense BF16 peak from the repository accelerator inventory or an already content-bound primary artifact. Do not use a structured-sparsity peak. Report both the chosen peak and evidence path/hash. This peak is an optimistic analytical denominator, not a throughput transfer.
- Disjoint measured decode linears+head c32 total: `0.22476958992984145 seconds/request`. Whole-service ceilings: strict `0.47201182295214134`, lenient `0.47751364375858635` seconds/request.

## Required analysis

1. Compute exact compulsory transformer-linear FLOPs for 3,678.822 fresh prompt tokens and the resulting optimistic H200 seconds/request. Do not divide per-request work by 32 a second time: batching changes elapsed batch time, while sustainable request throughput already amortizes that batch over its 32 requests.
2. Add this prefill-linear floor to the disjoint measured decode linears+head total and classify against both service ceilings. Emit strict and lenient residual seconds/request and the residual as a percentage of each ceiling.
3. As a separately labeled sensitivity, derive compulsory fresh-query prefill QK/AV FLOPs for the 50 sliding-window and 10 causal-global layers, correctly accounting for cached-prefix keys/values, the 1,024 local window, GQA query-head work, and causal positions. Combine it with linear FLOPs under the same impossible-ideal peak only if the no-overlap arithmetic argument is valid. Exclude softmax/norm/rotary/KV writes unless independently proven lower bounds; list omissions.
4. Reconcile the conclusion with the live project's actual decode-attention result only if that project has already written a typed terminal while this work is active. Never poll or wait for it. Otherwise emit an explicit merge formula and threshold: the maximum actual decode-attention seconds/request that would preserve each ceiling after the prefill floor.
5. Return one typed decision: `c32_closed_by_disjoint_prefill_plus_decode_floor`, `c32_preserved_with_attention_threshold`, or `none_due_to_identity_or_arithmetic_failure`. This is a floor, not endpoint or quality evidence.

## Budgets and terminal

- Wall clock: 30 minutes.
- Compute: 1.5 local CPU-hours; no GPU.
- Storage: 384 MiB retained plus 128 MiB temporary, project-local only.
- Spend: `$0`; no provider queries, mutation, image pull, checkpoint read, compilation, or endpoint.

Write a reproducible calculator, source/hash manifest, `PREFILL_COMPUTE_FLOOR.json`, concise `RESEARCH_LOG.md`, and terminal `STATUS.json`. Fail closed on any identity mismatch or ambiguous double count.
