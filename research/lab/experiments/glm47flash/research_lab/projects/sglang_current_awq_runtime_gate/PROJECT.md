# SGLang current-AWQ runtime gate

## Question

Does one unchanged current stable SGLang release admit the exact campaign GLM-4.7-Flash AWQ checkpoint on L40S, with a conservative path to at least `606.355` output tok/s on the cache-off 8K/1K c16 workload?

## Why this matters

The valid vLLM r3 c16 endpoint is `552.171055` output tok/s, below the ordinary `594.466` economic gate. TensorRT-LLM v1.2.1 closes at exact model registration, and the audited vLLM stacks have no exact SM89 mixed-prefill/decode full-graph route. SGLang is a materially different engine. Retained V14 evidence shows that a GLM-specific patched SGLang stack started this AWQ checkpoint on L40S and reported `18,587 MiB` loaded memory, but it produced no typed fixed-workload endpoint; that is compatibility evidence, not performance. Current exact-model documentation also names SGLang. A bounded source gate can decide whether an unchanged supported path now exists and whether it merits one later matched measurement.

## Fixed evidence

- Exact checkpoint: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`; do not substitute another revision or representation.
- Exact architecture/workload: `Glm4MoeLiteForCausalLM`, 64 routed experts/top-4 plus shared expert and MLA; cache off, 8,192 input/1,024 output, 32 complete requests, c16, 300-second background envelope, thinking disabled.
- Exact economics: one 48-GiB SM89 L40S at the fresh `$1.10/hour` planning rate; ordinary gate `594.466`, robust nomination gate `606.355` output tok/s.
- Valid denominator: current-AWQ vLLM r3 c16 `552.1710554232396` output tok/s with complete requests.
- Retained compatibility prior: `/root/workspace/research/lab/experiments/glm47flash/campaign_100/allocations/nebius_l40s_awq_smoke_v14/`; the patched SGLang server started and reported `18,587 MiB`, but its terminal artifact is invalid and has no fixed-workload or quality result.
- Consume `../representation_runtime_bridge/`, `../exact_model_external_scan/`, `../vllm_release_delta_screen/`, and `../trtllm_current_awq_runtime_gate/` as fixed evidence. Do not repeat a broad runtime survey or repair V14.

## Scope and stop rule

Within 1,200 seconds, 12 GiB RSS, 96 MiB new artifacts, and `$0`, bind one official current stable SGLang source release or immutable image manifest. Fail fast through:

1. exact `Glm4MoeLiteForCausalLM` model/config registration without remote custom model code or a campaign/source patch;
2. exact compressed-tensors AWQ v1/group-32 loading for routed experts, shared expert, attention, and head without conversion, dequantized/BF16-weight fallback, or a different checkpoint;
3. exact MLA, MoE/grouped-GEMM, and graph/scheduler support on SM89 without SM90+, eager-only, custom-kernel, or unsupported fallback;
4. preservation of the tokenizer, reasoning-off generation, cache-off semantics, 32k context, c16 correctness, and a plausible 48-GiB runtime envelope; and
5. official exact-scope benchmarks or source-bound mechanisms that support a conservative lower bound of at least `606.355` output tok/s against r3.

Related GLM models, generic SGLang speedups, the old patched smoke's memory value, and results on another representation, GPU, context, concurrency, or output length are priors only. If exact admission survives but performance is not conservatively identifiable, name the sole later matched measurement and close `UNIDENTIFIABLE`; do not nominate on expected engine quality.

Return exactly one terminal result:

- `NOMINATE_SGLANG_L40S_AB`: an unchanged exact path exists and conservative evidence reaches `606.355` tok/s; state one later candidate-only endpoint specification but do not prepare it;
- `MODEL_CLOSE`: exact architecture support still requires remote code, a source patch, or model implementation work;
- `REPRESENTATION_CLOSE`: model support exists but exact AWQ/MLA/MoE/SM89 execution does not;
- `ECONOMIC_CLOSE`: an exact path exists but conservative evidence misses `606.355` tok/s; or
- `UNIDENTIFIABLE`: exact admission survives but current evidence cannot establish the robust economic path.

Do not use CUDA, build an image, download or load model weights, edit shared code, access credentials, mutate a provider, prepare a controller, or spend money. Produce one compact JSON, a bounded source audit if useful, and a concise research-log result.

## Available resources

Use official SGLang source/release documentation, local source/image metadata caches, the fixed project and V14 evidence above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
