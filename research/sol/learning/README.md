# Inference co-design learning library

This directory collects durable learning resources that explain the mechanisms encountered in the Sol inference experiments. Add new material only when it improves understanding of architecture, representation, kernels, serving, memory hierarchy, hardware, measurement, or inference economics. Keep paper and vendor claims separate from campaign measurements.

## Start here: Stanford CS336

[Stanford CS336: Language Modeling from Scratch](https://cs336.stanford.edu/) is the first track. For this research, prioritize:

1. Resource accounting: FLOPs, bytes moved, arithmetic intensity, and memory use.
2. Attention alternatives and mixture of experts.
3. GPUs and their memory/execution hierarchy.
4. Kernels and Triton.
5. Inference and serving.
6. Evaluation, especially why correctness and quality gate performance claims.

Keep notes in `CS336_NOTES.md` as you work through it. A useful format is: concept, your explanation, campaign example, open question, and a small calculation or experiment.

## Guides

- [GLM inference co-design learning path](GLM_INFERENCE_LEARNING_PATH.md) — ordered one-day and one-week routes, primary sources, hands-on exercises, and links to the V19/V20 evidence.
- `CS336_NOTES.md` — personal study notes and questions; intentionally starts as a template.

## Next tracks

### Horace He: performance from first principles

- [Making Deep Learning Go Brrrr From First Principles](https://horace.io/brrr_intro.html)
- Best for: classifying a workload as compute-, memory-bandwidth-, or overhead-bound before choosing an optimization.
- Campaign exercise: use V19's trace to separate Marlin matmul/MoE work, MLA attention, GEMV, and launch overhead; write one falsifiable intervention for the largest category.

### GPU MODE: practical kernel engineering

- [GPU MODE lecture materials](https://github.com/gpu-mode/lectures)
- [GPU MODE YouTube channel](https://www.youtube.com/@GPUMODE)
- Best for: CUDA/Triton/CuTe kernel implementation, profiling, layout algebra, numerics, and performance competitions.
- Campaign exercise: reproduce a tile-size sweep on a standalone grouped-attention shape before modifying the full GLM server.

### How to Scale Your Model: systems math

- [How to Scale Your Model](https://jax-ml.github.io/scaling-book/)
- Start with [rooflines](https://jax-ml.github.io/scaling-book/roofline/), [Transformer math](https://jax-ml.github.io/scaling-book/transformers/), [inference](https://jax-ml.github.io/scaling-book/inference/), and [GPUs](https://jax-ml.github.io/scaling-book/gpus/).
- Best for: deriving compute, memory, communication, KV-cache, latency, throughput, and parallelism bounds instead of guessing from GPU specifications.
- Campaign exercise: derive a lower bound for GLM decode step time from parameter bytes, batch size, KV state, and L40S bandwidth, then compare the prediction with V19 c1/c8 TPOT.

## Contribution rule

For each added resource, record the title, URL, publication or revision, retrieval date, evidence type, why it matters to the campaign, and one concrete exercise. Do not record credentials, private course material, or copied copyrighted text.
