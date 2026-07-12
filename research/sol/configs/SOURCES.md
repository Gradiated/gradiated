# Configuration sources

The Qwen3-8B model and tokenizer fixtures are pinned to Hugging Face revision `b968826d9c46dd6066d109eabc6255188de91218`, returned by the upstream model API on 2026-07-11. The checked architecture declares 8,190,735,360 BF16 parameters at that revision; the local analytical fixture rounds this to 8.2 billion parameters.

`qwen3-8b-agentic-h100.json` uses the official Qwen3-8B architecture: 8.2 billion parameters, 36 layers, 32 query heads, eight KV heads, and a native 32,768-token context. The H100 SXM baseline uses NVIDIA's published 80 GB memory, 3.35 TB/s HBM bandwidth, BF16 tensor throughput, 700 W maximum TDP, and 900 GB/s NVLink specifications.

The $7 accelerator-hour input matches Fireworks' public July 2026 on-demand H100 price. It is a customer-visible comparison value rather than an estimate of Fireworks' internal marginal cost.

The canonical `agentic-v1` request mix is a synthetic benchmark assumption, not a claim about private Claude Agent SDK traffic. It is held constant across all candidates and will be versioned when replaced by measured representative traces.

`aa-agentperf-public-proxy-v1.json` uses only publicly described AA-AgentPerf geometry: 5K–131K input lengths, approximately 27K mean input, interleaved tool work with a one-second median delay, dynamic prefixes, and concurrent sessions. The generator's eight-session layout, 64-request turn mix, output lengths, prefix ratios, detailed delays, arrival stagger, and SLO tiers are Foundry's synthetic controls. No private test data, prompts, outputs, scoring, AA-AgentPerf result, NVIDIA result, provider result, or cost result is imported.

`glm-5.2-agentic-mapping-screen-v1.json` retargets only those 64 exact input-token counts into the pinned GLM mapping/residency arithmetic at concurrency 1, 8, 16, 32, and 64. It does not claim tokenizer or prompt equivalence and deliberately excludes output work, arrivals, tool timing, prefix behavior, network timing, latency, throughput, quality, SLOs, and cost. The 90K mapping fixture remains a separate provider-inspired token-geometry anchor rather than a production-workload label.

The custom accelerator is a hypothesis, not a manufacturable design. Its compute, SRAM, HBM, network, power, yield, and NRE values exist to exercise sensitivity and co-design. No investor or tapeout conclusion may use it until independent simulator, physical-design, and cost validation replace those assumptions.

The Timeloop problem exporter targets the official v4 problem schema version `0.4` and its einsum-style `shape`, `data_spaces`, and `instance` contract. The first checked problem is only the BF16 Qwen3-0.6B attention output projection geometry (`M=1`, `N=1024`, `K=2048`, batch 1). TimeloopFE 0.4 at commit `5603893c0ff75183b5ffd6839aba33774fc3b6fe` parses and processes the exact YAML with an adapted official v4 architecture/mapper fixture. Native `timeloop-mapper` is absent and six probed build dependencies are missing, so mapping, cycles, utilization, energy, area, and cost remain false. Quantized tensors are rejected because `KernelProblem` does not yet carry code, scale, group, and metadata storage; emitting an INT4 problem as four bits per weight would undercount the quality-checked group-8 representation.

`qwen3-0.6b-int4-packed-kernel-smoke-v1.json` is pinned to Qwen3-0.6B revision `c1899de289a04d12100db370d81485cdf75e47ca` and checkpoint SHA-256 `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`. The executable smoke additionally verifies BLAKE3 identities for each measured layer-zero tensor before packing signed group-8 INT4 codes with BF16 scales. Its scalar Apple M4 Pro timing is a local kernel observation, not a tuned BF16, BLAS, vLLM, GPU, quality, energy, serving, or cost baseline.

`qwen3-0.6b-int4-packed-batch-frontier-v1.json` reuses and BLAKE3-pins that request, compiler/host boundary, and exact three tensors. Packed and f32-QDQ controls use identical group/pair/lane traversal at B=1, 4, 16, and 64. No point crosses to a packed win. Feature-major activation preparation, explicit SIMD, assembly inspection, hardware counters, tuned baselines, quality transfer, serving, energy, and cost remain outside its evidence scope.

`qwen3-0.6b-int4-aarch64-neon-v1.json` pins the same checkpoint, quality-evidence label, base request, and three tensor-byte identities. It requires AArch64 NEON, a release build, one thread, preallocated outputs, five warmups, 31 alternating-order samples, and immutable 1e−3 maximum-error/1e−4 RMSE gates. The implementation, config, and 1.75× prediction were committed before timing. Its measured 4.457× scalar-packed and 3.284× scalar-f32-QDQ component ratios are local intrinsic observations only; they do not establish tuned BF16, full-model, quality, serving, energy, or cost performance, and the 44.7% prediction error fails the predictive gate.

The selective-INT4 task bridge pins Qwen3-0.6B revision `c1899de289a04d12100db370d81485cdf75e47ca`, checkpoint SHA-256 `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`, PIQA revision `2e8ac2dffd59bac8c3c6714948f4c551a0848bb0`, and frozen config SHA-256 `8232110572bad06cc724af71308cff6da2f5f6d033e393ada8d34f3475ccfdbc`. The exact-source rerun preserves the official validation strings, including trailing whitespace, and binds all 1,838 rows with SHA-256 `fde850cdcace44f9cf4d4dbeaed6465f247f1b9aa6e1b84aabd73852d81f4993` plus the selected 256 rows with `459ed1c48bf77ba46b40e21fe1e3153a7f93ac9619aada736e116683e7de678f`. Its passing point gate is not a full-benchmark, confirmatory non-inferiority, decontamination, packed-kernel, serving, energy, or cost result.

The Qwen3-0.6B vLLM CPU repeatability contract pins config SHA-256 `68ff23fe9d5fe24547ee2c1fe944dc346dcb97a4f448180be8effefc723da4f7`, model/checkpoint identities, vLLM revision, prompt content, randomized schedule, host capture, performance-core binding, and the 20% unrelated-process rejection threshold. Its checked terminal content ID `7b71feaf1820b3c97756ac6d09e56f775ab1e40ab4ae7f6f35dae2af8699989e` records one accepted c8 cold/warm pair and a blocked resumed campaign: 355 samples over 1,802.79 seconds never formed the required three-sample clean streak. This supports a host-contamination classification only, not repeatability or performance.

The SCALE-Sim adapter pins the official MIT repository's `v3.0.0` tag at commit `7fd972e7c650e81c77294c9433143a282235c5e7` and separately records inspected current main `9f98c4371055a54c75209c2e02b640b897550532`. The release tag calls itself `2.0.2` in `setup.py`; this upstream inconsistency is preserved rather than normalized away. Native cycles, utilization, and access counts are permitted only within the exact pinned oracle. Dense elements are not BF16/NVFP4 arithmetic, CALC bandwidth is not calibrated HBM, and no frequency, GPU, energy, area, whole-model, serving, or cost mapping exists.

`glm-5.2-current-cost-claim-composition-v1.json` is an evidence-policy fixture, not a measurement. Its relative effects copy the declared boundaries of the pinned source artifacts solely to test scope, metric, intervention-set, evidence-class, and claim-permission gates. The evaluator never multiplies them. The request can permit output cost only when one measured end-to-end artifact exactly covers the requested model/workload/contracts/stacks/interventions.

## References

- Qwen3-8B: https://huggingface.co/Qwen/Qwen3-8B
- Qwen3 architecture and license: https://qwenlm.github.io/blog/qwen3/
- NVIDIA H100 specifications: https://www.nvidia.com/en-us/data-center/h100/
- Fireworks pricing: https://fireworks.ai/pricing
- Timeloop v4 input formats: https://timeloop.csail.mit.edu/v4/input-formats
- Timeloop v4 problem schema: https://timeloop.csail.mit.edu/v4/input-formats/problem
- SCALE-Sim official repository: https://github.com/scalesim-project/SCALE-Sim
