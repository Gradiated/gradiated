# TensorRT-LLM current-AWQ runtime gate

## Question

Does one unchanged current TensorRT-LLM release admit the exact GLM-4.7-Flash AWQ checkpoint on L40S, with a model/representation/kernel path and conservative performance mechanism capable of reaching the campaign's robust `606.355`-tok/s nomination threshold?

## Why this matters

The valid vLLM r3 c16 endpoint is `552.171055` output tok/s, below the ordinary `594.466` economic gate. The pinned and current stable vLLM stacks have now closed full mixed-prefill/decode CUDA graphs for the selected SM89 MLA backend, while narrow split-MLA and forced-depth changes transferred too little endpoint gain. TensorRT-LLM is a materially different CUDA engine with its own model import, quantized MoE, attention, graph, and scheduling implementations. A source-only compatibility and mechanism gate is the cheapest way to decide whether it deserves one later exact endpoint measurement; generic TensorRT peak claims or support for a related GLM model are not admissible.

## Fixed evidence

- Exact checkpoint: `/root/.cache/glm47flash-awq-ab31d120`, `cyankiwi/GLM-4.7-Flash-AWQ-4bit@ab31d120fbe79988fe2a0259993cf3c222aa8881`, AWQ v1/group-32 compressed-tensors W4A16, manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`, approximately 20.2 GB. Do not substitute the newer external-scan revision.
- Exact architecture and workload: `Glm4MoeLiteForCausalLM`, 64 routed experts/top-4 plus shared expert and MLA geometry from the pinned config; cache-off 8,192 input/1,024 output, 32 complete requests, c16, 300-second envelope.
- Exact hardware/economics: one 48-GiB SM89 L40S at `$1.10/hour`; ordinary gate `594.466` and robust nomination gate `606.355` output tok/s.
- Valid reference endpoint: current-AWQ vLLM r3 c16 `552.1710554232396` output tok/s. Use its content-addressed archive and `hardware/L40S.md` only as scoped priors.
- Consume `../exact_model_external_scan/`, `../representation_runtime_bridge/`, `../vllm_release_delta_screen/`, and `../l40s_mla_full_graph_gate/` as fixed evidence. Do not repeat their broad searches, patch SGLang/vLLM, or reopen full-graph work inside vLLM.

## Scope and stop rule

Within 1,200 seconds, 12 GiB RSS, 96 MiB new artifacts, and `$0`, audit one official current stable TensorRT-LLM source release or container manifest. Bind source/release identities and decide, in fail-fast order:

1. whether the exact `Glm4MoeLiteForCausalLM` architecture has an official unchanged loader/import/conversion path, rather than only a related dense GLM or custom example;
2. whether the exact compressed-tensors AWQ group-32 checkpoint can be consumed without changing weights, quantization semantics, tokenizer, or model code;
3. whether SM89 has exact W4A16 kernels for the model's routed/shared MoE and MLA geometry, without dense/dequantized, BF16-weight, SM90+, source-patch, or custom-plugin fallback;
4. whether the admitted path preserves 32k context, cache-off benchmark semantics, c16 request correctness, and a plausible 48-GiB engine/runtime memory envelope; and
5. whether official exact-scope benchmarks or source-bound fused/graph/scheduler mechanisms support a conservative lower bound of at least `606.355` output tok/s against the r3 reference.

Do not transfer throughput across another model, representation, GPU, context, concurrency, or output length. Do not infer the gate from peak FLOPS/bandwidth, kernel availability, or a generic TensorRT-LLM speedup. If exact support survives but no scope-matched performance evidence exists, report the sole later measurement needed and close as `UNIDENTIFIABLE`; do not nominate on optimism.

Return exactly one terminal result:

- `NOMINATE_TRTLLM_L40S_AB`: the unchanged exact path exists and a conservative stress bound reaches `606.355` tok/s; state one later matched candidate-only endpoint spec but do not prepare it;
- `MODEL_CLOSE`: the exact architecture is unsupported without model/runtime source work;
- `REPRESENTATION_CLOSE`: the architecture exists but the exact AWQ/MoE/MLA/SM89 path does not;
- `ECONOMIC_CLOSE`: an exact path exists but conservative evidence misses `606.355` tok/s; or
- `UNIDENTIFIABLE`: exact admission survives but current evidence cannot establish a conservative economic path.

Do not use CUDA, download model weights, build an engine, convert a checkpoint, edit shared code, access credentials, mutate a provider, create a controller, or spend money. Produce one compact JSON, a bounded source audit if useful, and a concise research-log result.

## Available resources

Use official TensorRT-LLM source/release documentation, local source caches, the fixed project evidence above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
