# GLM inference co-design learning path

Retrieved: 2026-07-14

## Question and scope

Question: which primary resources best explain the architecture, representation, serving, kernel, memory, profiling, and economics concepts encountered in the GLM-4.7-Flash campaign?

Decision: prioritize material that helps a reader form and falsify optimization hypotheses from the campaign's measured traces. This is a study guide, not evidence that any technique will improve GLM or beat a provider. Vendor and paper performance claims do not transfer to the campaign without matched measurement.

## Recommended order

### 1. Build the systems vocabulary

Use Stanford CS336's resource-accounting, architecture/MoE, GPU, Triton, and inference lectures. The course connects tensor shapes to FLOPs, bytes moved, arithmetic intensity, parallelism, and serving behavior. Those concepts explain why a lower-precision model can fit a cheaper GPU without automatically running faster, and why prefill and decode have different bottlenecks.

Exercise: for the frozen 8,192-input/1,024-output workload, calculate the input/output ratio, output-token throughput, and derived GPU dollars per million output tokens from the V19 report before checking the recorded answers.

Then read Horace He's *Making Deep Learning Go Brrrr From First Principles*. Its compute-versus-bandwidth-versus-overhead framework is the shortest bridge from resource accounting to useful profiling hypotheses. Follow it with *How to Scale Your Model*, especially rooflines, Transformer math, inference, and the GPU chapter, to turn that intuition into quantitative latency and throughput bounds.

### 2. Understand GLM's architectural geometry

Read DeepSeek-V2 for Multi-head Latent Attention (MLA) and sparse MoE. GLM-4.7-Flash is not DeepSeek-V2, but the paper gives the architectural vocabulary needed to understand latent KV state, partial rotary dimensions, routed experts, and the compute-versus-memory trade. Follow with MegaBlocks for the systems problem created by dynamic expert routing and grouped sparse computation.

Campaign connection: V19's mixed prefill/decode trace attributes the largest named GPU-duration family to vLLM's Triton MLA grouped decode kernel. The local checkpoint declares 20 query heads, a 512-dimensional KV latent rank, 256-dimensional values, and 64 rotary dimensions. These identities make generic attention intuitions insufficient and motivate shape-specific kernel tests.

Exercise: inspect `experiments/glm47flash/campaign_100/allocations/nebius_l40s_vllm_awq_batch_v19/vllm-awq-batch.tar.gz`, find the trace hash in `allocation-result.json`, and compare the MLA kernel share with the MoE Marlin kernel families.

### 3. Learn representation and quantization

Read AWQ before GPTQ variants because the tested public checkpoint uses activation-aware weight-only INT4 and compressed-tensors metadata. Focus on why protecting salient channels can preserve quality, why weights and activations can have different dtypes, and why a smaller representation changes both memory capacity and kernel choice.

Campaign connection: V19's AWQ checkpoint is about 20.17 GB and passes the paired compact quality screen against the complete BF16 responses, but both fail the absolute compact quality gate. V20 then shows that changing only activation dtype from BF16 to FP16 regresses c8 throughput. Representation size, activation arithmetic, kernel implementation, and quality are separate causal variables.

Exercise: explain why “4-bit weights” does not mean every operation or cache entry is four bits, using the V19 server identity and trace families.

### 4. Learn serving as an operating system problem

Read the PagedAttention paper and current vLLM documentation for KV paging, continuous batching, chunked prefill, CUDA graphs, prefix caching, and scheduler token budgets. Read SGLang next for RadixAttention and structured-program execution.

Campaign connection: V19 disables prefix caching and measures exact c1/c8 geometry. V21 changes only `max_num_batched_tokens` from 32,768 to 65,536 to test whether eight simultaneous 8K prefills benefit from a single scheduler-budget wave. TTFT, TPOT, queue time, throughput, and failure rate must be read together.

Exercise: predict which metric should move first when the scheduler admits more prefill tokens—TTFT, TPOT, or single-request throughput—and write down what result would falsify the prediction.

### 5. Learn IO-aware kernels

Complete the Triton tutorials in order through fused softmax, matrix multiplication, fused attention, grouped GEMM, and persistent matmul. Then read FlashAttention for the IO-complexity argument: reducing HBM traffic through tiling and fusion can matter more than reducing arithmetic.

Campaign connection: the current trace-guided target is `_fwd_grouped_kernel_stage1` in vLLM's `triton_decode_attention.py`, not an unidentified “GPU bottleneck.” Candidate changes must be tied to GLM's exact head/value/latent geometry and compared against unchanged stock code.

Exercise: vary one Triton launch or tile parameter in a standalone kernel, check correctness, then use the same input shapes to compare latency and achieved bandwidth. Do not begin with an end-to-end server patch.

Use GPU MODE after the official Triton tutorials. Its lecture archive spans practical CUDA, Triton, CuTe, layout algebra, numerics, profiling, and increasingly specialized LLM kernels. Select lectures by the kernel currently under investigation rather than watching the archive chronologically.

### 6. Learn to profile before optimizing

Use the CUDA Programming Guide for thread hierarchy, warps, registers, shared/global memory, occupancy, and asynchronous execution. Use Nsight Systems to establish the CPU/GPU timeline and Nsight Compute to analyze a selected kernel with memory-workload, occupancy, and roofline views.

Campaign connection: PyTorch trace duration identifies candidates but does not explain whether a kernel is bandwidth-, instruction-, occupancy-, or launch-limited. V19's whole-arm utilization average also includes hashing, load, quality, and idle phases, so it is not a serving utilization estimate.

Exercise: for one kernel, write a bottleneck claim in the form “metric X is near/far from ceiling Y; therefore intervention Z should change metric W.” Reject any optimization story that lacks this falsifiable link.

### 7. Learn inference economics and evidence discipline

For each serving point, distinguish steady-state accelerator cost from allocation setup, disks, networking, replicas, orchestration, and provider margin. Compare systems only at matched model/representation, workload geometry, quality, and SLO. Throughput alone is not goodput, and a component speedup is not a service cost reduction.

Exercise: reproduce `$0.692503/M` from V19's authenticated VM-plus-disk hourly rate and c8 throughput. Then list the missing evidence that prevents comparing it directly with Fireworks or Baseten.

## Short tracks

One day:

1. CS336 resource accounting, GPU, Triton, and inference lectures.
2. DeepSeek-V2's MLA and MoE sections.
3. Triton's fused-attention tutorial.
4. Read the V19/V20 report sections and predict V21.

One week:

1. Complete the CS336 systems assignment material.
2. Read AWQ, PagedAttention, FlashAttention, and SGLang.
3. Complete the core Triton tutorials.
4. Reproduce one campaign trace aggregation and one cost calculation.
5. Profile a small attention kernel with Nsight Systems and Nsight Compute.

## Primary source table

| Topic | Source | Publication/revision | Evidence type | Why it is here |
|---|---|---:|---|---|
| End-to-end LM systems | [Stanford CS336: Language Modeling from Scratch](https://cs336.stanford.edu/) | 2026 course | Official course | Resource accounting, architecture, GPUs, Triton, inference, evaluation |
| Performance reasoning | [Making Deep Learning Go Brrrr From First Principles](https://horace.io/brrr_intro.html) | 2022 | Author technical article | Compute, bandwidth, and framework-overhead bottleneck classification |
| Systems and scaling math | [How to Scale Your Model](https://jax-ml.github.io/scaling-book/) | Google DeepMind online book, 2025; retrieved 2026-07-14 | Technical book | Rooflines, exact Transformer math, inference, KV cache, parallelism, GPUs |
| Practical GPU kernels | [GPU MODE lecture materials](https://github.com/gpu-mode/lectures) | Living archive retrieved 2026-07-14 | Community technical lectures and code | CUDA, Triton, CuTe, profiling, layouts, numerics, LLM kernels |
| MLA and sparse MoE | [DeepSeek-V2](https://arxiv.org/abs/2405.04434) | 2024-05-07 | Research paper | Architectural basis for latent KV state and routed experts |
| Routed sparse kernels | [MegaBlocks](https://arxiv.org/abs/2211.15841) | 2022-11-29 | Research paper | Dynamic MoE routing mapped to block-sparse computation |
| Weight-only INT4 | [AWQ](https://proceedings.mlsys.org/paper_files/paper/2024/hash/42a452cbafa9dd64e9ba4aa95cc1ef21-Abstract-Conference.html) | MLSys 2024 | Peer-reviewed paper | Activation-aware weight quantization used by the tested representation |
| KV memory and scheduling | [PagedAttention](https://doi.org/10.1145/3600006.3613165) | SOSP 2023 | Peer-reviewed systems paper | Paging and continuous-batching foundations for vLLM |
| Current serving mechanisms | [vLLM documentation](https://docs.vllm.ai/en/stable/index.html) | Stable docs retrieved 2026-07-14 | Official documentation | Chunked prefill, caching, graphs, quantization, kernels, parallelism |
| Prefix-aware serving | [SGLang](https://arxiv.org/abs/2312.07104) | 2023-12-12 | Research paper | RadixAttention and structured inference programs |
| IO-aware attention | [FlashAttention](https://arxiv.org/abs/2205.14135) | 2022-05-27 | Research paper | Tiling and memory-traffic reasoning |
| Kernel implementation | [Triton tutorials](https://triton-lang.org/main/getting-started/tutorials/index.html) | Docs retrieved 2026-07-14 | Official documentation/tutorials | Practical fused operations, attention, grouped GEMM, persistent matmul |
| GPU execution model | [CUDA C++ Programming Guide](https://docs.nvidia.com/cuda/archive/13.0.0/cuda-c-programming-guide/index.html) | CUDA 13.0 | Official documentation | Warps, memory hierarchy, registers, occupancy, synchronization |
| Kernel bottleneck analysis | [Nsight Compute documentation](https://docs.nvidia.com/nsight-compute/NsightCompute/index.html) | 13.3 docs retrieved 2026-07-14 | Official documentation | Roofline, occupancy, and memory-workload analysis |

## Uncertainty and limits

- DeepSeek-V2 and MegaBlocks explain mechanisms but do not establish GLM-4.7-Flash performance.
- Paper speedups are author-reported on their own controls and workloads.
- Framework documentation changes; pin the version when reproducing campaign behavior.
- The campaign's compact quality suite is diagnostic and currently fails its absolute gate for both BF16 and AWQ.
- Provider competitiveness still requires matched external workload, quality, SLO, availability, and fully loaded price evidence.

Next action: use this path to interpret the trace-selected MLA decode-kernel experiment, and add only sources that change a concrete experiment choice or explain a measured result.
