# Current-AWQ native MTP layer

## Question

Does the current AWQ checkpoint's exact one-layer MTP payload have a supported vLLM execution path and a plausible acceptance/overhead regime that can reduce c16 L40S cost by at least 10%?

## Why it matters

The checkpoint config declares `num_hidden_layers=47` and `num_nextn_predict_layers=1`; tensors under `model.layers.47.*` include `eh_proj`, a shared head, embeddings, attention, 64 routed experts, and a shared expert. The pinned vLLM 0.15.0 GLM-Lite source explicitly constructs configured next-token-prediction layers, and its speculative decoder contains MTP detection. This is materially different evidence from the completed `mtp_acceptance_bound`, which audited a failed complete-BF16/SGLang c8 lineage and never established current-AWQ/vLLM execution.

## Scope

At zero provider spend, bind and hash the exact config, layer-47 tensor set, dtypes/quantization, bytes, source loader, model registry, speculative-decoder selection, and CLI/config contract in the pinned vLLM image. Determine whether stock serving currently ignores the MTP payload and whether an MTP configuration can load it from the same current checkpoint without a second full model copy or an unsupported model-class substitution. Use local container/source execution and the smallest fail-closed configuration/loader fixture; do not run a GPU, edit the shared provider launcher, or repair the historical SGLang route.

Recalculate the acceptance and overhead thresholds for the measured 535.286-output-tok/s c16 8,192-input/1,024-output background workload and the campaign's 10% committed-cost gate. Use the retained c16/c8 prefill/decode evidence where scope matches. Sweep only the actual draft width exposed by one MTP layer and a few explicit draft/verify overhead cases. Report required accepted draft tokens, target throughput, memory/KV overhead, and the minimal later counters: proposal tokens, accepted tokens per round, draft/verify wall time, fallback/errors, output identity, endpoint wall time, and memory.

Do not claim speed from source support, repeat the old 5% c8 simulation, train a new head, inspect broad speculative methods, or open provider work. A source path that parses but cannot bind this exact layer-47 payload is a closure result.

## Resources

- Exact current AWQ checkpoint: `/root/.cache/glm47flash-awq-ab31d120`.
- Pinned runtime image: `vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`.
- Current c16 control: `../nebius_current_awq_c16_direct/`.
- Prior scope-mismatched MTP bound: `../mtp_acceptance_bound/`.
- Current-AWQ traces and runtime sources: `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.

## Portfolio-changing result

Nominate at most one exact current-AWQ MTP configuration only if the content-bound loader/planner fixture passes and conservative c16 accounting supports a realistic 10% path. State the one later matched off/on L40S experiment without implementing it. Unsupported exact loading, implausible acceptance, or a below-gate bound closes the current-AWQ MTP route. This project has no provider authority or spend.
