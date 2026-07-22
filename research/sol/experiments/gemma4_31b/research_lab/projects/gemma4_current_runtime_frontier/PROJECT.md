# Current full-stack runtime frontier

## Question

Does a current production runtime provide a faster exact Gemma 4 31B hybrid-attention FP8 endpoint than the retained SGLang v0.5.13 stack after matching model, workload, cache precision, and required semantics?

## Why this is independent

The current frontier is pinned to SGLang v0.5.13 plus local patches. Earlier vLLM and TensorRT-LLM attempts failed on the then-pinned FP8-E5M2 and head-dimension-512 support boundaries; those are historical runtime-scoped results, not evidence that current upstream implementations still lack support. A newer fused attention, FP8 loader, scheduler, or CUDA-graph path could produce a larger gain than another isolated kernel edit.

## Scope and immediate experiment

Start from the exact identities in `../gemma4_h200_v0513_fp8_qkv_residual_profile/BINDINGS.json`. Inspect current official source and release support for Gemma 4 hybrid local/global attention, dynamic or deployable FP8 weights, FP8 KV, TP=1 H200, prefix caching, and tool-compatible serving. Select the single strongest runnable candidate among current SGLang, vLLM, TensorRT-LLM, or another credible production runtime. Do not write a survey and do not retry an unchanged historical image.

Prepare a content-addressed runtime/image and go directly to a same-H200 exact endpoint comparison. Match 32 requests, 4,214 prompt tokens, 358 output tokens, and the recorded cached/fresh split. It is acceptable to establish a fresh control in the candidate runtime; label any representation difference. Patch ordinary support defects in place when the candidate implementation is the experiment. Stop the lane only on a measured endpoint result or a source/CUDA incompatibility that rules out the selected current candidate, then name the next runnable candidate rather than reopening preparation work.

Record runtime/source identities, representation, complete-request throughput, prefill/decode timing, memory, utilization, power, exact cache accounting, semantic smoke, useful GPU time, and cost. Promote a valid result that beats `0.6892200126 s/request`; the economic target remains `0.6381105231 s/request`.

## Resources

- Reuse a director-registered H200 when compatible; a second H200 may run concurrently if the director judges wall-clock gain worth the spend.
- Up to 180 H200 claim minutes and `$12.00` total authorized spend.
- No broad runtime matrix, quality campaign, or unchanged replay of old startup failures.
