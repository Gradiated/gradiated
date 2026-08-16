# GLM-5 / GLM-5.2 co-design evidence dossier

Status: research plan and source record, not a performance, provider-cost, or tapeout claim  
Evidence cut-off: 2026-07-12  
Target objective: minimum sustainable input- and output-token cost for one model-specific GLM-5.2 stack under a fixed agentic workload envelope and fixed quality/SLO contracts

## Executive conclusion

`GLM-5.2` is an actual released Z.ai model, not shorthand. Z.ai announced it on 2026-06-16, released BF16 and FP8 checkpoints, and identifies it as the current long-horizon GLM-5-series model. The official release adds a 1,048,576-token context, cross-layer DSA index sharing, and an improved shared-parameter MTP path. The release and exact model IDs are documented by the [Z.ai GLM-5.2 announcement](https://z.ai/blog/glm-5.2), the [official GLM-5 repository](https://github.com/zai-org/GLM-5), and the pinned [GLM-5.2 checkpoint](https://huggingface.co/zai-org/GLM-5.2/tree/b4734de4facf877f85769a911abafc5283eab3d9).

The model is materially different from the current Qwen3 target. It is a 78-layer sparse-attention MoE with 256 routed experts, eight selected experts per token, one shared expert, compressed MLA state, a content-dependent top-2048 DSA gather, 21 retained backbone indexers, and a recursively used MTP layer. Its BF16 tensor inventory is 753,329,940,480 parameters even though Z.ai's release name is `744B-A40B`. Those are different provenance claims: use the exact pinned tensor inventory for storage and use `approximately 40B active` only as a release-level compute description until an exact active-parameter ledger is generated.

This architecture makes four costs first-order:

1. Routed-expert weight capacity, bandwidth, batching, and all-to-all traffic.
2. Long-context DSA index scans, top-k selection, and irregular KV gathers.
3. KV and indexer-cache capacity, movement, prefix reuse, and lifecycle correctness.
4. MTP draft cost and acceptance under real coding-agent output, not random text.

The strongest near-term candidate is not an invented whole-model INT4 scheme. NVIDIA already publishes an expert-only GLM-5.2 NVFP4 checkpoint with selected benchmark parity, reducing stored checkpoint payload to about 465 GB. That checkpoint is an incumbent baseline we must beat, not a proprietary advantage. The most model-specific remaining opportunities are an IndexShare-aware DSA datapath, routing-aware MoE placement and interconnect, a cache hierarchy designed for MLA plus DSA indexer state, and joint scheduling of prefix reuse, long prefill, and MTP.

The original Inference Foundry schema could not represent this model faithfully because it assumed a dense decoder, GQA-style KV heads, and dense layer work. The structural contract now types MoE, MLA, DSA, IndexShare, and MTP, but important phase work, traffic, execution, quality, and calibration remain bounded or unknown. Encoding GLM-5.2 as either a 753B dense model or a 40B dense model would still be wrong, and the current contract does not authorize an economic conclusion.

The opportunity is credible enough to simulate, but not yet evidence for custom silicon. Z.ai and framework teams report meaningful full-stack gains on this model family, showing that co-design can matter in their measured systems without validating Foundry's simulator or business thesis. It also raises the competitive baseline: a proposed custom stack must beat current FP8/NVFP4, IndexShare, MTP, context parallelism, LayerSplit/HiCache, expert parallelism, and PD-disaggregated serving rather than compare against generic dense vLLM defaults.

The newest independent memory result is deliberately narrow. A pinned [`Ramulator2 HBM3 sweep`](../validation/results/qwen3-glm-ramulator2-hbm3-synthetic-irregular-v1.json) is patched-native and fully drained across 18 cases × two replays, with 1,363,968 callbacks and exact request/tick/latency conservation. Within its synthetic geometries, ascending logical-token order changes controller cycles by −27.744% for one 32-byte transaction per selected token but by +59.194% for a one-layer 1,152-byte record; cluster-64 changes by −50.569% and +2.709%. The reversal is evidence that geometry and bank parallelism matter, not evidence for a GLM optimization. The sweep is uncalibrated and permits no pristine-source, GLM trace/performance, GPU/kernel, wall-time, end-to-end serving, model-quality, energy, cost, provider, or tapeout claim.

The current [predictive-validity gate](../validation/results/simulator-predictive-validity-gate-2026-07-12.json) is **NOT_MET** with one admitted prospective component pair. The direction is correct but effect-size error is 44.7%; three interventions, two regimes, a predicted regression, rank correlation, and quality/SLO cost evidence remain missing. Simulator predictive validity and cost promotion therefore remain false. The [small-model proxy ladder](SMALL_MODEL_PROXY_SELECTION.md) keeps Qwen3-0.6B as the local quality-bearing plumbing proxy and NOSA-1B as a future single-CUDA-GPU sparse-locality/offload proxy; neither transfers GLM performance or cost approval.

## Evidence language

This dossier uses the following labels:

| Label | Meaning |
|---|---|
| **Released fact** | A field in a pinned official checkpoint/configuration or an official release artifact. |
| **Derived fact** | Deterministic arithmetic from released fields; the formula is shown. |
| **Vendor measurement** | A number reported by Z.ai, NVIDIA, vLLM, or SGLang on its own system. It is useful calibration evidence but is not independently reproduced here. |
| **Inference** | An engineering conclusion supported by released facts but not directly measured. |
| **Hypothesis** | A proposed intervention whose benefit and quality must be tested. |
| **Unknown** | A value that must not be filled with an attractive assumption. |

Official sources sometimes disagree because they count different objects. This document retains those disagreements rather than silently choosing a convenient number.

## Identity and release lineage

| Artifact | Status and date | Pinned revision | Role in this study |
|---|---|---|---|
| `zai-org/GLM-5` | Released 2026-02; BF16 | [`4e6698ba8e85059d749020e3c4d2123719f23926`](https://huggingface.co/zai-org/GLM-5/tree/4e6698ba8e85059d749020e3c4d2123719f23926) | Technical-report architecture and pre-IndexShare reference. |
| `zai-org/GLM-5-FP8` | Released 2026-02; native FP8 | [`4f96cc5eec29dcee5d6ded54f7ffe889438f9516`](https://huggingface.co/zai-org/GLM-5-FP8/tree/4f96cc5eec29dcee5d6ded54f7ffe889438f9516) | Earlier deployable precision reference. |
| `zai-org/GLM-5.1` | Released 2026-04; BF16 | [`26e1bd6e011feb778d25ae34b09b07074139d92d`](https://huggingface.co/zai-org/GLM-5.1/tree/26e1bd6e011feb778d25ae34b09b07074139d92d) | Immediate pre-5.2 quality and serving reference. Its released geometry matches GLM-5 on the fields used here. |
| `zai-org/GLM-5.2` | Released 2026-06-16; BF16 | [`b4734de4facf877f85769a911abafc5283eab3d9`](https://huggingface.co/zai-org/GLM-5.2/tree/b4734de4facf877f85769a911abafc5283eab3d9) | Canonical quality/reference checkpoint. |
| `zai-org/GLM-5.2-FP8` | Released 2026-06-16; block FP8 | [`ba978f7d347eaf65d22f1a86833408afdb953541`](https://huggingface.co/zai-org/GLM-5.2-FP8/tree/ba978f7d347eaf65d22f1a86833408afdb953541) | Practical provider-grade deployment baseline. |
| `nvidia/GLM-5.2-NVFP4` | Released 2026-06-25; selective NVFP4 | [`aec724e8c7b8ee9db3b48c01c320f63f9cdaf8aa`](https://huggingface.co/nvidia/GLM-5.2-NVFP4/tree/aec724e8c7b8ee9db3b48c01c320f63f9cdaf8aa) | Strongest public low-bit capacity/bandwidth baseline in this dossier. |

The Z.ai repository calls all three released generations `GLM-5`, `GLM-5.1`, and `GLM-5.2`. The 5.2 release is therefore neither a typo nor a speculative future name. The study should use the full model ID and revision in every artifact; `GLM-5` by itself is too ambiguous.

The model weights use the MIT license. The surrounding official GitHub repository uses Apache-2.0. Those licenses should not be conflated.

## Released architecture

### Checkpoint-level fields

The following fields come from the pinned [GLM-5.2 `config.json`](https://huggingface.co/zai-org/GLM-5.2/blob/b4734de4facf877f85769a911abafc5283eab3d9/config.json).

| Field | GLM-5.2 value | Evidence status | Simulation meaning |
|---|---:|---|---|
| Architecture | `GlmMoeDsaForCausalLM` / `glm_moe_dsa` | Released fact | A typed MoE+MLA+DSA model, not a dense surrogate. |
| Backbone layers | 78 | Released fact | Repeat count for attention and MLP lowering. |
| Hidden size | 6,144 | Released fact | Residual/activation width. |
| Vocabulary | 154,880 | Released fact | Embedding and LM-head geometry. |
| First dense layers | 3 | Released fact | Layers 0–2 have dense MLPs. |
| Dense intermediate size | 12,288 | Released fact | Dense gated-MLP width. |
| Sparse layers | 75 | Derived fact | `78 - 3`. |
| Routed experts per sparse layer | 256 | Released fact | Resident expert capacity and routing fan-out. |
| Selected routed experts per token | 8 | Released fact | Active expert compute and communication. |
| Shared experts per sparse layer | 1 | Released fact | Always-active expert work. |
| MoE expert intermediate size | 2,048 | Released fact | Each routed/shared expert's gated-MLP width. |
| Router scoring | sigmoid, normalized top-k, `noaux_tc` | Released fact | Routing semantics; distribution remains unknown. |
| Attention heads | 64 | Released fact | Query/output projection geometry. |
| Query low-rank dimension | 2,048 | Released fact | MLA query projection. |
| KV latent dimension | 512 | Released fact | Main compressed KV state. |
| QK dimensions | 192 NoPE + 64 RoPE = 256 | Released fact | MLA attention dot product. |
| Value dimension | 256 | Released fact | MLA value/output projection. |
| DSA index heads / dimension | 32 / 128 | Released fact | Lightning-indexer GEMM and scan shape. |
| DSA selected tokens | top 2,048 | Released fact | Sparse core-attention gather width. |
| Backbone indexer frequency | once per four-layer block | Released fact | 21 full indexers and 57 shared-index layers. |
| Indexer sharing offset | 3 | Released fact | Full indexers at layers 0, 1, 2, 6, 10, …, 74. |
| Maximum position | 1,048,576 | Released fact | Native one-million-token context envelope. |
| RoPE theta | 8,000,000 | Released fact | Positional configuration. |
| Next-token prediction layers | 1 | Released fact | One shared-parameter MTP module used recursively. |
| MTP index sharing | enabled | Released fact | Later draft iterations reuse first-step indices. |
| Base arithmetic dtype | BF16 | Released fact | Canonical checkpoint precision. |

The [GLM-5 technical report](https://arxiv.org/pdf/2602.15763) describes a 744B-total, 40B-active model with 256 experts and says layer count was reduced to 80. The released GLM-5, GLM-5.1, and GLM-5.2 configs declare 78 backbone layers. This dossier uses 78 for checkpoint simulation and retains 80 as a report-level description. It does not guess whether the report counted an embedding, output, or MTP stage.

### What changed from GLM-5 / GLM-5.1 to GLM-5.2

The pinned [GLM-5 config](https://huggingface.co/zai-org/GLM-5/blob/4e6698ba8e85059d749020e3c4d2123719f23926/config.json) and [GLM-5.1 config](https://huggingface.co/zai-org/GLM-5.1/blob/26e1bd6e011feb778d25ae34b09b07074139d92d/config.json) expose the same key MoE/MLA/DSA geometry as one another. GLM-5.2 retains that broad shape and makes these deployment-relevant changes:

| Field | GLM-5 / 5.1 | GLM-5.2 | Consequence |
|---|---:|---:|---|
| Maximum position | 202,752 | 1,048,576 | KV capacity and long-context execution become central. |
| RoPE theta | 1,000,000 | 8,000,000 | Position configuration changes; kernels must use the checkpoint value. |
| DSA indexer frequency | Every layer | One per four-layer block after the first three | Most indexer parameters and three quarters of backbone indexer execution are removed. |
| Indexer modules | 78 | 21 | Lower indexer weights, cache, FLOPs, and launches. |
| MTP index reuse | Not declared | Declared across draft iterations | Avoids repeated index scans in later MTP steps. |
| MTP training/verification | Earlier shared-parameter MTP | Adds IndexShare/KVShare, rejection sampling, and end-to-end TV loss | Vendor reports higher acceptance under coding prompts. |

Z.ai calls the 5.2 mechanism **IndexShare**. The related paper calls the general method **IndexCache**. They exploit the same cross-layer redundancy, but the names should remain source-specific.

### Exact indexer-removal reconciliation

The official Hugging Face snapshot inventories report:

- GLM-5 and GLM-5.1 BF16: 753,864,139,008 tensor parameters.
- GLM-5.2 BF16: 753,329,940,480 tensor parameters.
- Difference: 534,198,528 parameters.

One GLM indexer contains:

```text
query projection       = 2,048 × (32 × 128) = 8,388,608
key projection         = 6,144 × 128        =   786,432
per-head weight proj   = 6,144 × 32         =   196,608
key norm weight+bias                           =       256
total per indexer                              = 9,371,904
```

GLM-5.2 removes 57 indexers: `57 × 9,371,904 = 534,198,528`. This exactly reconciles the two released tensor inventories. It is strong evidence that 5.2 physically omits the shared layers' indexer weights rather than merely bypassing their execution.

### Weight inventory and storage

| Checkpoint | Tensor inventory | Exact tensor payload | Repository storage | Relative payload | Evidence |
|---|---:|---:|---:|---:|---|
| GLM-5.2 BF16 | 753,329,940,480 | 1,506,659,919,872 bytes | 1,506,687,604,850 bytes | 1.000 | Pinned official metadata. |
| GLM-5.2-FP8 | 753,375,793,584 | 755,617,140,416 bytes | 761,025,363,709 bytes | 0.502× BF16 | Pinned official metadata. |
| NVIDIA GLM-5.2-NVFP4 | Packed inventory is not a logical parameter count | 464,794,806,272 bytes | 464,865,454,030 bytes | 0.615× FP8; 0.308× BF16 | Pinned NVIDIA metadata. |

`Exact tensor payload` multiplies each published tensor count by its element bytes. `Repository storage` includes checkpoint metadata and ancillary files. Neither number is a runtime resident-memory guarantee: allocators, scales, graph capture, kernels, workspaces, and cache pools add memory.

The native FP8 config uses dynamic activation quantization, E4M3, and 128×128 weight blocks. It retains a substantial list of modules outside FP8, including embeddings, the LM head, norms, routers, and indexer components. It is not an all-parameter one-byte model.

NVIDIA's [GLM-5.2 NVFP4 model card](https://huggingface.co/nvidia/GLM-5.2-NVFP4) says only linear weights and activations inside routed MoE experts are converted to NVFP4; the shared expert is not. On NVIDIA's five reported evaluations, NVFP4 stays within 0.86 points of FP8 on every individual benchmark and improves three of the five point estimates. That is meaningful positive evidence for selective expert quantization, but it is not an agentic non-inferiority proof for our workload.

### Why experts dominate capacity

Assuming the standard three linear matrices in each gated expert, released dimensions imply:

```text
routed expert parameters
= 75 sparse layers × 256 experts × 3 matrices × 6,144 × 2,048
= 724,775,731,200 parameters
= 96.21% of the GLM-5.2 BF16 tensor inventory

shared expert parameters
= 75 × 1 × 3 × 6,144 × 2,048
= 2,831,155,200 parameters

first-three dense-MLP parameters
= 3 × 3 × 6,144 × 12,288
= 679,477,248 parameters
```

The 96.21% figure is a **derived architecture fact**, not a statement that every one of those weights is read for each token. Each token selects eight of 256 routed experts plus the shared expert. The exact active-parameter count also includes attention, embeddings/output, dense MLPs, routers, norms, and the retained indexers. Until the lowerer enumerates those tensors exactly, `40B active` remains an approximate official description rather than an exact simulator input.

The concentration of resident parameters in routed experts explains why NVIDIA can reduce checkpoint payload so much while preserving higher precision for attention, routers, shared experts, embeddings, and early dense layers. It also means any custom hardware that lacks efficient sparse-expert storage and movement is solving the wrong problem.

## Attention, cache, and phase work

### DSA is two different long-context operations

DSA should not be modeled as generic sparse attention with one efficiency coefficient. Each full-indexer layer performs at least two distinct operations:

1. A lightning indexer projects the query and scans prior-token index keys, scores them, and selects top 2,048 positions.
2. Core MLA attention gathers compressed KV state at those selected positions and computes sparse attention.

Shared-index layers skip the first operation and reuse the previous full layer's selected indices, but they still perform their own core attention. At one million tokens, the index scan remains proportional to context length while core attention is bounded by the selected width. The fixed 21-full/57-shared pattern creates an unusually stable target for a fused streaming dot-product/top-k engine and an index handoff kept on chip across four layers.

The [IndexCache paper](https://arxiv.org/html/2603.12201) reports that adjacent DSA layers have high top-k overlap and that a searched one-quarter-retention pattern on GLM-5 stayed within 0.4 points of its long-context average. GLM-5.2 goes further: it was trained with a uniform one-per-four IndexShare pattern from mid-training, according to the [official GLM-5.2 announcement](https://z.ai/blog/glm-5.2).

### Semantic MLA cache lower bound

The released MLA state has a 512-element latent KV vector and a 64-element RoPE key component. Before allocator padding, scales, indexer state, and MTP state:

```text
semantic main-cache elements per layer-token = 512 + 64 = 576

BF16 main cache per token across 78 layers
= 78 × 576 × 2 bytes
= 89,856 bytes

ideal one-byte main cache per token across 78 layers
= 78 × 576 × 1 byte
= 44,928 bytes
```

A single one-million-token sequence therefore has an 89.856 GB BF16 or 44.928 GB ideal one-byte main MLA cache per full cache copy. The official vLLM recipe says FP8 cache roughly halves the KV budget and is required to make the full window practical on 8×B200. Real runtimes can consume more because RoPE values, scales, alignment, block metadata, and the DSA indexer cache have different layouts. TP may replicate cache; context or layer parallelism may partition it. Those choices must be explicit simulator fields.

For comparison, the current Qwen3-8B fixture's GQA cache is `36 × 2 × 8 × 128 × 2 = 147,456` BF16 bytes per token. GLM's semantic MLA cache is smaller per token despite the much larger model, but its context envelope, depth, indexer cache, and distributed deployment make its serving regime harder. Qwen's `kv_head_count` is not a valid GLM cache parameter.

### MTP is workload-dependent

GLM-5.2 declares one next-token-prediction layer whose parameters are reused for multiple draft steps. Z.ai reports a seven-step coding-prompt ablation with mean accepted length rising from 4.56 to 5.47 after IndexShare/KVShare, rejection sampling, and end-to-end TV loss. The result is a **vendor measurement**, not a universal acceptance rate.

MTP can reduce output cost only when accepted tokens amortize the draft and verification work. The official vLLM recipe warns that random synthetic prompts tend to produce low acceptance and understate real performance. Our simulator must consume an acceptance-length distribution conditioned on model revision, prompt class, context, temperature, and draft depth. A hard-coded speedup is invalid.

## Deployment evidence

### Supported baseline stack

The official GLM repository currently lists SGLang 0.5.13.post1+, vLLM 0.23.0+, Transformers 5.12+, KTransformers, Unsloth, and Ascend-oriented engines. The practical comparison target is the native FP8 checkpoint, not BF16.

The official [vLLM GLM-5.2 recipe](https://recipes.vllm.ai/zai-org/GLM-5.2) documents:

- FP8 on a single 8×H200/H20 node with tensor parallelism 8.
- Full 1M context on 8×B200 with FP8 KV cache, subject to concurrency.
- MTP with five configured speculative tokens, with the caveat that draft count should follow observed acceptance.
- Expert parallelism for NVIDIA's NVFP4 checkpoint.
- BF16 as a roughly 1.5 TB deployment that generally requires larger or multi-node configurations.

The official [SGLang GLM-5.2 cookbook](https://docs.sglang.io/cookbook/autoregressive/GLM/GLM-5.2) documents a wider model-specific stack:

- DSA-specific prefill, decode, and top-k indexer kernels.
- FP8 DSA cache on Blackwell and BF16 cache on Hopper by default.
- MTP/EAGLE with index reuse across draft iterations.
- Attention context parallelism for long prefill.
- DP-attention and DeepEP for MoE routing.
- PD disaggregation and hierarchical KV caching.
- Regime-specific chunked-prefill and concurrency tuning.

KTransformers also publishes an [8-GPU CPU/GPU heterogeneous recipe](https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/kt-kernel/GLM-5.2-Tutorial.md) that offloads experts to CPU and dynamically changes which experts reside on GPU. It establishes expert tiering as a real deployment path, but does not publish enough end-to-end cost evidence to treat CPU offload as a winning baseline.

### Vendor measurements worth reproducing

These results are calibration targets, not values to insert directly into our economic report.

| Intervention | Reported result | Conditions and caveat | Primary source |
|---|---|---|---|
| GLM-5.2 IndexShare | 2.9× lower per-token FLOPs at 1M context | Architecture-level claim relative to the prior indexer path; not 2.9× end-to-end throughput. | [Z.ai GLM-5.2 announcement](https://z.ai/blog/glm-5.2) |
| Training-free IndexCache on GLM-5 | At least 1.3× prefill and decode improvement beyond 100K | Earlier GLM-5, one-quarter retained indexers, preliminary vendor-scale result. | [IndexCache paper](https://arxiv.org/html/2603.12201) |
| MTP changes | Acceptance length 4.56 → 5.47, +20% | GLM-5.1 backbone/data, coding scenarios, seven MTP steps. | [Z.ai GLM-5.2 announcement](https://z.ai/blog/glm-5.2) |
| SGLang attention CP | Roughly 2.5–2.8× prefill speedup at 64K | Framework team's supported hardware tests; CP can hurt decode and partitions KV capacity. | [SGLang GLM-5.2 cookbook](https://docs.sglang.io/cookbook/autoregressive/GLM/GLM-5.2) |
| Larger chunked prefill | +34–78% output throughput and −39–59% TTFT | 8K input/1K output balanced serving on 8×H200/B200; high-throughput point was decode-bound. | [SGLang GLM-5.2 cookbook](https://docs.sglang.io/cookbook/autoregressive/GLM/GLM-5.2) |
| LayerSplit | +10–132% throughput | GLM-5.1, 40K–120K requests, 90% cache hit; gain grew with context. | [Z.ai scaling post](https://z.ai/blog/scaling-pain) |
| NIC bandwidth | 100 → 200 Gbit/s gave about +19% throughput and −22% TTFT | 32-GPU GLM inference testbed; other details are incomplete. | [Z.ai ZCube post](https://z.ai/blog/zcube) |
| ZCube network | +15% average GPU throughput, −40.6% p99 TTFT, −33% switch/optics CapEx | Thousand-GPU GLM-5.1 production cluster; vendor-controlled before/after deployment. | [Z.ai ZCube post](https://z.ai/blog/zcube) |
| NVIDIA expert-only NVFP4 | Five selected quality scores remained close to FP8 | B200/B300 runtime support; not our task suite or a complete safety/quality evaluation. | [NVIDIA model card](https://huggingface.co/nvidia/GLM-5.2-NVFP4) |

The SGLang team also documents a real correctness failure on an older AMD gfx950 FP8 GEMM path: small per-layer errors compounded over 78 layers and destroyed long reasoning while short factual prompts appeared normal. This is direct evidence that kernel validation must include long-context, long-output behavior and cannot rely on a few plausible generations.

### Production workload evidence

Z.ai's [GLM-5 scaling post](https://z.ai/blog/scaling-pain) says its coding-agent inputs averaged more than 70K tokens and had high prefix reuse. Under high concurrency, prefill backlog and decode-side cache pressure exposed rare cache corruption that simple offline replay did not reproduce. Z.ai reports:

- PD-disaggregation abort/reclaim races that allowed late RDMA writes into reused cache slots.
- Hierarchical-cache read-before-ready races between load and forward streams.
- Indexer-cache state as well as main KV state needing correct movement and synchronization.
- Speculative acceptance metrics acting as anomaly indicators.

These are model-stack correctness requirements, not optional implementation details. A custom serving stack that is fast but corrupts one in ten thousand long agent requests can be economically worse once retries, failed tasks, and customer trust are counted.

## Economic boundary

Z.ai's official [pay-as-you-go price table](https://docs.z.ai/guides/overview/pricing) lists GLM-5.2 at $1.40 per million uncached input tokens, $0.26 per million cached input tokens, and $4.40 per million output tokens as of the evidence cut-off. These are retail prices, not Z.ai's marginal cost, and they do not reveal utilization, hardware, or gross margin.

The cached-input price is 81.43% below the uncached-input price. Even if our product exposes only one input price and one output price, the internal economics must keep cached and uncached input work separate. Otherwise a workload-mix change can look like a stack improvement or turn a low input price into an unmodeled subsidy.

Every GLM study should report:

- Internal cost per million uncached input tokens.
- Internal cost per million cache-hit input tokens, including lookup and retained-cache cost.
- Blended input cost under the frozen trace, with hit ratio stated.
- Internal cost per million output tokens.
- Cost per SLO- and quality-compliant output token.
- Cost per successful agent task and tokens per successful task.
- Separate compute, HBM/DRAM, interconnect, host, storage, energy, and amortized-capital allocations.

Reducing reasoning output length can lower cost per task while raising or lowering cost per output token. It is a product/quality trade, not automatically an inference-efficiency gain. Compare stack changes at fixed generated tokens and fixed quality first; report effort routing separately.

## Frozen model-level workload envelope

Hardware is customized once for GLM-5.2, not separately for each request class. One design must pass the complete envelope. The envelope below is an internal experiment contract, not a claim about all customers.

| Class | Input | Output | Prefix-hit sweep | Purpose and provenance |
|---|---:|---:|---:|---|
| Short tool turn | 8K | 512 | 0%, 40%, 80% | Exposes fixed overhead, batching, and MTP behavior. |
| Typical coding turn | 70K | 2K | 40%, 70%, 90% | Centered on Z.ai's reported >70K production average. |
| Long engineering turn | 200K | 8K | 70%, 90% | Matches the prior GLM context regime and LayerSplit evidence range. |
| Ultra-long turn | 1,048,576 | 16K | 90%, 98% | Capacity/stability stress at the released maximum, not assumed to dominate traffic. |

Each class must be evaluated in Max, High, and non-thinking modes only when the quality suite defines a comparable target for that mode. The primary business conclusion should use one frozen mode mix and arrival trace. Sensitivities can vary the mix but cannot silently select the cheapest mode per candidate.

The current Qwen trace tops out at 28,672 input tokens. It is not a representative GLM-5.2 capacity or networking test.

## Prioritized co-design hypotheses

### Ordered intervention table

| Priority | Intervention | Primary stack axes | Expected input-cost effect | Expected output-cost effect | Why it is model-specific | Falsifier |
|---|---|---|---|---|---|---|
| P0 | Expert-only NVFP4 or equivalent selective low-bit format | Model representation, expert GEMM, HBM, fleet sizing | Moderate; prefill is more compute-dense but capacity and expert bandwidth still fall | High when decode is expert-weight-bandwidth bound | 96.21% of parameters are routed-expert weights; public NVFP4 evidence exists | No fleet/device threshold changes, executable kernels lose the storage gain, or fixed agent quality fails |
| P0 | Fused IndexShare DSA scan/top-k/gather datapath | Kernel, SRAM, HBM, attention hardware | High at long prefill | High at long-context decode | Fixed 21-indexer pattern, 32×128 indexer, top-2048, reuse across four layers and MTP steps | Less than 10% wall-time share at representative contexts or gather stalls erase saved index scans |
| P0 | Prefix-stable tiered MLA+indexer cache with LayerSplit semantics | Serving, memory hierarchy, DMA, cache hardware | Potentially very high at 70K+ repeated prefixes | Indirect; frees HBM and decode capacity | Agent traces have long shared prefixes; DSA needs both main and indexer state; MLA cache geometry is fixed | Benefit requires an unrepresentative hit ratio, p95 TTFT fails, or any stale/read-before-ready corruption occurs |
| P1 | Routing-aware expert placement, replication, and interconnect | Serving, MoE kernel, NoC/fabric, memory | Moderate to high depending on batch and route distribution | High if batch-one expert reads or all-to-all dominate | 256 experts/top-8 across 75 layers produces a stable sparse-routing workload | Savings disappear under uniform/adversarial routes or p99 expert imbalance exceeds SLO |
| P1 | Acceptance-aware MTP depth and fused verification | Model, kernel, serving | Minimal | Moderate to high on natural coding output | Shared one-layer MTP, 5.2-specific IndexShare/KVShare, published high coding acceptance | Speedup <1.1× or joules/accepted token rise under the frozen agent corpus |
| P1 | Context-parallel prefill plus model-shaped PD/network topology | Mapping, serving, NIC/fabric, hardware | High for long prompts | Neutral or negative unless decode mapping is isolated | Long GLM contexts move replicated MLA/indexer state and produce asymmetric PD traffic | Network/collective overhead outweighs TTFT gain or tail latency worsens under mixed lengths |
| P2 | Adaptive DSA selected width or layer-specific indexer schedule | Model architecture, kernel | Potentially high | Potentially high at long context | Current top-2048 and one-in-four schedule are explicit model knobs | Long-context/agentic non-inferiority fails or savings are small after retraining cost |
| P2 | Reduce routed top-k, compress experts further, or co-train placement-aware experts | Model architecture, MoE hardware | High theoretical | High theoretical | Active expert count drives compute and traffic while total experts drive storage | Retraining/quality cost dominates or router collapse/imbalance violates quality and SLO |
| P2 | Cross-layer or lower-bit MLA/indexer cache | Model architecture, cache kernel, memory | High capacity potential | High at long context | Main MLA state is 576 semantic elements/layer-token; index selections already share across layers | Quality or long-retrieval degradation, dequant overhead, or no device-count threshold change |

### P0: selective expert quantization is the baseline, not the moat

NVIDIA has already validated the central intuition: quantize the dominant routed experts aggressively while keeping sensitive shared and non-expert paths at higher precision. A first co-design study should compare at least BF16, native block-FP8, NVIDIA NVFP4, and one proposed format using exact stored bytes and executable-kernel efficiency.

The key economic question is discontinuous: does lower expert storage remove a device, node, HBM stack, or replica at the frozen SLO? A nominal 38.5% payload reduction from FP8 to NVFP4 matters much more if it changes an 8-device layout to four or frees enough HBM for cache concurrency. If topology does not change and the workload is compute-bound, capacity savings alone may not lower output-token cost materially.

Model changes should start with expert-only formats because whole-model W4 would spend quality risk on the attention, router, indexer, embeddings, and shared expert that collectively hold only a small fraction of capacity. The failed Qwen3-0.6B naive W4 sweep is not evidence against NVIDIA's calibrated GLM expert-only NVFP4, but it is a warning against assuming low-bit quality.

### P0: specialize the DSA data movement, not only its FLOPs

A model-specific DSA block should stream index keys, fuse score and hierarchical top-k, emit compact indices once, and reuse them without HBM round trips across the three shared layers. The sparse core should coalesce the resulting top-2048 MLA gathers and prefetch selected blocks. Candidate hardware features include:

- A streaming dot-product/top-k reduction path sized to 32 heads × 128 dimensions.
- Small persistent SRAM for selected indices, metadata, and cross-layer handoff.
- Gather address generation and request coalescing for 2,048 irregular token positions.
- Separate bandwidth/queues for index scans and selected main-cache reads.
- Overlap between next-layer index work, selected-cache transfer, and MoE execution.

The design must count indexer scan bytes and sparse-gather bytes separately. A top-k accelerator that saves arithmetic but leaves random HBM reads serialized can lose to a tuned commodity kernel.

### P0: co-design cache hierarchy and correctness

The likely useful tiers are on-package HBM, host/CXL DRAM, and optional SSD for retained prefixes. The allocator must move a compound object: main MLA state, the subset of retained indexer keys, page tables, and lifecycle metadata. IndexShare lowers indexer state but does not eliminate it.

Prefix identity should be stabilized at the protocol boundary. SGLang's GLM-5.2 cookbook notes that a per-request attribution block prepended by an agent client can become the first differing token and destroy radix-prefix reuse. Canonical tool schemas, stable system-prefix ordering, and content-addressed cache identities may lower input cost without changing model numerics.

Correctness is a hard gate. Cache reuse must be generation-safe across aborts, RDMA completion, tier load completion, retries, and MTP target/draft state. The simulator should attach a generation number to every page and reject any read or late write whose generation does not match the request.

### P1: route experts around the actual model

The router distribution is currently unknown. Do not assume Zipf locality because it makes SRAM or CPU offload look good. Capture per-layer expert IDs from a real baseline when hardware becomes available. Until then, sweep:

- Uniform routes.
- Stable Zipf hotness.
- Prompt-class-correlated hotness.
- Adversarial bursts that move the hot set.
- Correlated routes across adjacent tokens and independent routes.

Search static placement, hot-expert replication, dynamic migration, CPU/CXL tiering, and combinations of tensor, expert, and data parallelism. The hardware objective is not maximum all-to-all bandwidth in isolation; it is lowest SLO-compliant cost after switch/NIC power and capital.

### P1: treat MTP as a controlled gamble

For each draft depth, the simulator must charge draft-layer weights/compute, target verification, rejected tokens, cache writes, and scheduling complexity. It must also account for fewer target-model synchronization rounds when drafts are accepted. Draft depth can be selected by a model-specific acceptance predictor, but the predictor cannot inspect future tokens or use quality labels unavailable online.

Speculative acceptance should also be monitored as a correctness signal. Sudden abnormally low or high acceptance under load can indicate target/draft cache divergence. A retry policy must include retry cost and failed-request denominators.

## CPU-only falsification program

These experiments require no model weights or GPUs unless explicitly marked as a later validation stage. The architecture simulators should be deterministic Rust components eventually; this dossier defines their contracts and rejection criteria without adding misleading Rust code in this turn.

### E0 — pinned snapshot and arithmetic audit

**Runnable now.** Fetch only official metadata and config files, never 1.5 TB of weights.

```sh
curl -L -sS https://huggingface.co/zai-org/GLM-5.2/resolve/b4734de4facf877f85769a911abafc5283eab3d9/config.json
curl -L -sS 'https://huggingface.co/api/models/zai-org/GLM-5.2?expand[]=sha&expand[]=safetensors&expand[]=usedStorage'
curl -L -sS 'https://huggingface.co/api/models/zai-org/GLM-5.2-FP8?expand[]=sha&expand[]=safetensors&expand[]=usedStorage'
curl -L -sS 'https://huggingface.co/api/models/nvidia/GLM-5.2-NVFP4?expand[]=sha&expand[]=safetensors&expand[]=usedStorage'
```

Pass conditions:

- Revisions equal the pins in this dossier.
- GLM-5.2 tensor total remains 753,329,940,480.
- Config retains 78 layers, 256 routed/top-8 experts, 21 `full` indexers, top-2048, and 1,048,576 positions.
- The 534,198,528-parameter GLM-5.1 → GLM-5.2 delta still reconciles to 57 removed indexers.

Any upstream change creates a new fixture revision; it must not silently mutate an existing report.

### E1 — GLM phase and storage ledger

**CPU analytical simulation; first implementation priority.** Extend the typed model lowerer before running economics.

For contexts `{8K, 32K, 70K, 128K, 200K, 400K, 1,048,576}`, batches `{1, 8, 32, 128}`, and BF16/FP8/NVFP4 weights, report per layer and phase:

- Dense, routed-expert, shared-expert, router, and attention operations.
- Unique and amortized expert-weight bytes.
- Router and all-to-all activation bytes.
- Indexer projection, scan, and top-k work on each full layer.
- Sparse top-2048 gather and MLA attention work on every layer.
- Main MLA, indexer, allocator, and MTP cache bytes.
- Collective, PD-transfer, and cache-tier bytes.

Falsifiable predictions:

1. Expert-only NVFP4 lowers resident tensor payload by about 38.49% versus native FP8 before runtime overhead.
2. IndexShare removes exactly 57 backbone indexer invocations and weight sets relative to GLM-5.1.
3. At sufficiently long context, index scan or cache movement overtakes dense arithmetic for at least one serving phase.

Reject the lowerer if it cannot reconcile official tensor/storage totals within documented exclusions or if it represents active experts by multiplying the whole 753B model per token.

### E2 — sparse-indexer and gather microbench

**CPU microbenchmark; algorithm/traffic evidence only.** Generate deterministic index-key arrays at context lengths through 1M with 128-byte keys, 32 query heads, and top-2048 output. Compare:

- Materialized scores plus full sort.
- Streaming exact top-k.
- Hierarchical tile top-k plus exact merge.
- One index calculation per layer versus reuse for four layers.
- Random selected positions versus clustered positions.
- AoS, SoA, blocked, and page-grouped MLA layouts.

Measure bytes read/written, allocations, comparisons, cache misses if available, and wall time. Verify identical top-k sets for exact algorithms. CPU speedup must not be reported as GPU speedup; it validates operation counts, reuse, and layout sensitivity.

Kill an on-chip index-handoff hypothesis if index storage/traffic is negligible relative to selected-cache gather under every representative context. Kill a gather layout if it helps clustered synthetic positions but regresses random positions enough to violate the robust case.

### E3 — MoE routing and placement simulator

**CPU discrete-event simulation.** Generate at least one million token-layer routing events with 256 experts, top-8 selection, one shared expert, and 75 sparse layers. Sweep route distributions, batch sizes, EP sizes, link bandwidth/latency, expert precision, memory tiers, and placement policies.

Required outputs:

- Expert utilization and p50/p95/p99 imbalance by device and layer.
- Unique expert weights read per batch.
- HBM/host/CXL bytes and energy.
- All-to-all bytes, queueing, and link hot spots.
- Tokens/s, TTFT/TPOT contribution, and device/fleet count.
- Migration churn and cold-miss rate for dynamic placement.

Falsifiable prediction: route-aware placement must lower total cost at fixed p95 SLO by at least 10% under the frozen mixture and remain non-regressive under uniform routes. Reject it if benefit depends on one unmeasured hotness distribution or if migration traffic erases HBM savings.

### E4 — prefix and hierarchical-cache trace simulation

**Runnable on the existing event-driven serving foundation after compound GLM cache pages are typed.** Replay the model-level workload envelope with stable and deliberately unstable prefixes. Sweep HBM/host/NVMe capacity, bandwidth, latency, admission, eviction, and prefetch policies.

Required experiments:

- Hit ratios from 0% to 98%, including the 90% point used in Z.ai's LayerSplit report.
- Stable system/tool prefixes versus a changing token at position zero.
- Main-cache-only tiering versus atomic main+indexer tiering.
- Load/forward overlap with and without explicit ready barriers.
- Abort during prefill, transfer, and decode; immediate slot reuse; late completion injection.

Pass conditions:

- Zero stale-generation reads and zero post-reclaim writes in exhaustive small state spaces and randomized stress runs.
- No excluded failed request in goodput or economic denominators.
- At least 10% blended input-cost reduction over HBM-only without violating class p95 TTFT.
- Benefit survives a 20-point lower prefix-hit sensitivity.

### E5 — MTP acceptance Monte Carlo

**CPU analytical simulation.** Use empirical or synthetic acceptance-length distributions with means `{1.0, 1.4, 2.0, 3.5, 4.56, 5.47}` and draft depths 1–7. Charge every draft, target verification, rejection, synchronization, and cache operation.

Falsifiable prediction: at the vendor-reported coding points, an optimal depth should reduce target synchronization rounds and output cost; at low-acceptance random points, deep MTP should regress. Reject a fixed depth if no setting stays within 5% of optimal across the frozen classes. Do not calibrate acceptance from random text alone.

### E6 — CP, LayerSplit, and PD mapping simulation

**CPU event/network simulation.** At 40K–120K and 90% prefix hit, reproduce the qualitative shape of Z.ai's LayerSplit result: gain should increase with context as cache pressure grows. At 64K, test whether attention CP can plausibly lower prefill time while adding decode overhead and reducing per-rank cache capacity.

The calibration is accepted when the model can cover the vendor ranges under a documented parameter interval, not when one hand-picked point exactly matches a headline. If matching requires impossible overlap or free communication, reject the mapping model.

### E7 — inference-network topology and failure simulation

**CPU packet/fluid simulation.** Model 32 GPUs first, then scale logically. Use asymmetric PD KV transfers and MoE all-to-all, comparing ROFT-like rail placement, flattened topology, and ideal nonblocking bounds at 100/200/400 Gbit/s.

Calibration targets from Z.ai are approximately +19% throughput and −22% TTFT for 100→200 Gbit/s on its 32-GPU testbed, plus +15% throughput and −40.6% p99 TTFT for its production ZCube migration. These are broad targets, not ground truth for our topology.

The simulator must also inject aborts and late transfers. Any design that increases throughput but permits a cache write after ownership changes fails regardless of average cost.

### E8 — quality and real-hardware promotion

No CPU-only surrogate can validate GLM-5.2 architecture changes. There is no checked-in small checkpoint with the same 78-layer, 256-expert, top-8, MLA+DSA+IndexShare+MTP stack. CPU-only experiments can reject performance ideas but cannot approve low-bit cache, fewer experts, smaller DSA top-k, or a changed index schedule.

Promotion eventually requires the exact pinned checkpoint or an explicitly scoped GLM-family proxy, a fixed agentic quality suite, long-context retrieval, coding/task success, tool-call validity, numerical comparisons, and load-induced corruption tests. NVIDIA's NVFP4 scores are baseline evidence, not transferable approval for another format.

## Required simulator contract before a GLM economic result

The model schema needs explicit fields for:

- Total tensor inventory and an exact precision/storage ledger by tensor class.
- Active parameter/work calculation separate from resident parameter count.
- Ordered dense and sparse MLP layer types.
- Routed and shared expert shapes, selection count, scoring, and route traces.
- MLA query/KV latent dimensions and semantic/runtime cache layouts.
- DSA indexer heads/dimension, selected width, full/shared layer pattern, and indexer cache.
- MTP parameter sharing, draft depth, acceptance distribution, and target verification.
- Tensor/expert/data/context/pipeline parallel mappings.
- MoE all-to-all, CP collectives, PD cache transfers, and topology contention.
- Compound cache-page ownership, readiness, generation, tier, and transfer state.

The original `dense_decoder`, `attention_head_count`, and `kv_head_count` fields were insufficient. The structural hybrid contract now exists, but a GLM economic run must still return unsupported until the remaining phase lowerers and measured calibration exist.

## Executable implementation status — 2026-07-12

| Contract slice | Status | Checked artifact | Claim boundary |
|---|---|---|---|
| Hybrid MoE/MLA/DSA/IndexShare/MTP model | Implemented | `glm_5_2_bf16_reference()` and Rust schema tests | Exact released structure and BF16 payload, not phase latency |
| Checkpoint, cache residency, and device floor | Implemented | [`storage-envelope-v1.json`](../experiments/glm-5.2/storage-envelope-v1.json) | Capacity and modeled bandwidth bounds; latency and cost/M remain null |
| NVFP4 + FP8-KV residency frontier | Implemented as exact conditional capacity arithmetic | [`nvfp4-fp8-kv-four-b200-frontier-v1.json`](../experiments/glm-5.2/nvfp4-fp8-kv-four-b200-frontier-v1.json), generated from its pinned [`request`](../configs/glm-5.2-nvfp4-fp8-kv-four-b200-frontier-v1.json) | Solves token, concurrency, fragmentation, runtime, and cache thresholds; does not establish TP4, kernel, allocation, serving, or cost support |
| Recursive MTP acceptance/work | Implemented | [`mtp-sweep-v1.json`](../experiments/glm-5.2/mtp-sweep-v1.json) | Synthetic acceptance and normalized work only |
| Canonical cross-backend action DAG | Implemented | [`glm-5.2-decode-ledger-v1.json`](../crates/foundry-core/tests/fixtures/glm-5.2-decode-ledger-v1.json) | Fixture accounting; calibrated latency, energy, and cost remain null |
| Whole-decode GLM lowering | Implemented with explicit work bounds | [`whole-decode-lowering-v1.json`](../experiments/glm-5.2/whole-decode-lowering-v1.json) | Exact FFN work/residency plus bounded attention, DSA, cache, routing, and MTP; all timing and cost claims locked |
| Public NVFP4 whole-decode lowering | Implemented with opaque correlated weight bounds | [`nvfp4-whole-decode-lowering-v1.json`](../experiments/glm-5.2/nvfp4-whole-decode-lowering-v1.json) | Exact compute and checkpoint identity; opaque selective layout/reuse, quality, timing, and cost remain blocked |
| Hardware critical-path roofline | Implemented | [`whole-decode-ledger-roofline-v1.json`](../experiments/glm-5.2/whole-decode-ledger-roofline-v1.json) | Same old profiles yield a 3.592× component-time ratio on whole-decode upper-bound work, not an end-to-end performance claim |
| Native-Blackwell NVFP4 roofline | Implemented with action-scoped engines and execution capability | [`lower-work`](../experiments/glm-5.2/nvfp4-blackwell-roofline-lower-v1.json) and [`upper-work`](../experiments/glm-5.2/nvfp4-blackwell-roofline-upper-v1.json) | B200/B300 native selective-NVFP4 counterfactual; nominal custom profile is explicitly non-executable and all performance/cost claims remain locked |
| Custom-hardware physical-feasibility audit | Implemented | [`CUSTOM_HARDWARE_FEASIBILITY.md`](CUSTOM_HARDWARE_FEASIBILITY.md) and [`custom-hardware-feasibility-2026-07-12.json`](../validation/results/custom-hardware-feasibility-2026-07-12.json) | Conditional software/model GO and tapeout NO-GO; no PPA, package, yield, cost, or residual silicon advantage proof |
| Native systolic-array mapping sweep | Implemented through pinned SCALE-Sim v3 | [`qwen3-glm-scalesim-v3-gemm-sweep-v1.json`](../validation/results/qwen3-glm-scalesim-v3-gemm-sweep-v1.json) | Exact Qwen/GLM GEMM shapes and native same-oracle cycles/accesses; dense elements are not BF16/NVFP4, GPU time, whole model, energy, area, or cost |
| Native irregular-memory sensitivity | Implemented through patched pinned Ramulator2 v2.1.0 with complete callback drain | [`qwen3-glm-ramulator2-hbm3-synthetic-irregular-v1.json`](../validation/results/qwen3-glm-ramulator2-hbm3-synthetic-irregular-v1.json) | Within-geometry synthetic single-channel HBM3 sensitivity only; uncalibrated and not GLM traffic, GPU time, serving, energy, cost, or provider evidence |
| Chakra compute/collective interchange | Implemented | [`chakra-decode-representable-v1.json`](../experiments/glm-5.2/chakra-decode-representable-v1.json) | Pinned v0.0.4 protobuf with no timing/rank assignment; unsupported actions reject |
| Compound prefix-cache lifecycle | Implemented | [`tiered-prefix-cache-v1.json`](../experiments/glm-5.2/tiered-prefix-cache-v1.json) | Synthetic whole-prefix trace, exclusive LRU, modeled tier links |
| Expert routing and placement | Implemented with synthetic distributions | [`moe-route-skew-v1.json`](../experiments/glm-5.2/moe-route-skew-v1.json) | Exact geometry/accounting; measured route histograms and link calibration are missing |
| DSA scan/top-k/gather phase model | Implemented analytically | [`dsa-indexshare-sweep-v1.json`](../experiments/glm-5.2/dsa-indexshare-sweep-v1.json) | Exact geometry/bytes and absorbed-MLA arithmetic; irregular gather, utilization, distributed mapping, and SRAM remain uncalibrated |
| Exact single-quantum serving replay | Implemented as a fail-closed counterfactual | [`exact-ledger-serving-v1.json`](../experiments/glm-5.2/exact-ledger-serving-v1.json), generated from the pinned [`manifest`](../configs/glm-5.2-exact-ledger-serving-v1.json), [`trace`](../configs/workloads/glm-5.2-exact-decode-trace-v1.json), and [`SLO contract`](../configs/workloads/glm-5.2-exact-decode-slo-v1.json) | Exact arrivals, batch/context shape, fair commit allocation, queue, TTFT/TPOT, and goodput mechanics for one fully reused quantum; all latency, SLO, and cost claims remain locked |
| Independent attention/expert mapping | Implemented with exact topology, network, and correlated residency bounds | [`16K control`](../experiments/glm-5.2/parallel-mapping-control-v1.json) and [`90K control`](../experiments/glm-5.2/parallel-mapping-90k-control-v1.json) | Compares coupled TP16 with DP-local attention plus local EP8; exact bytes/capacity bounds only, no latency, throughput, quality, SLO, or cost |
| Agentic token-geometry mapping screen | Implemented as request-weighted partial-residency and bounded full-capacity arithmetic | [`agentic-mapping-screen-v1.json`](../experiments/glm-5.2/agentic-mapping-screen-v1.json), generated from its pinned [`request`](../configs/glm-5.2-agentic-mapping-screen-v1.json) | Retargets token counts only; candidate full capacity is uncertain for all 64 requests at every concurrency, with no tokenizer, timing, network, quality, SLO, cost, or deployment claim |
| Fixed-budget aggregate versus P/D serving | Implemented as a deterministic event control | [`pd-serving-control-v1.json`](../experiments/glm-5.2/pd-serving-control-v1.json) | Explicit queues, prefix reuse, transfer bounds, phase effects, splits, and negative controls; rates are uncalibrated and all end-to-end claims remain false |
| Agent quality and exact-checkpoint measurement | Open | None | No local GLM checkpoint execution or quality approval |
| Predictive-validity promotion gate | Implemented fail closed; current status **NOT_MET** | [Gate machinery](../validation/predictive_validity/gate.py) and current [result](../validation/results/simulator-predictive-validity-gate-2026-07-12.json) | One prospective component pair admitted; direction correct, magnitude inaccurate, and no predictive, cost, custom-silicon, model-specific-advantage, or provider claim |
| Small-model proxy ladder | Qwen3-0.6B local; NOSA-1B future CUDA | [`SMALL_MODEL_PROXY_SELECTION.md`](SMALL_MODEL_PROXY_SELECTION.md) | Mechanism and tooling experiments only; no small-model performance or cost transfer to GLM-5.2 |

The original storage envelope's 64 × 32K-token scenario gives H200 total-residency floors of 16–17 devices for BF16, 9–10 for native FP8, and 6–7 for public expert-selective NVFP4, but it applies the model contract's BF16 semantic KV cache to every checkpoint variant. That NVFP4 row therefore does not represent NVIDIA's public FP8-KV launch configuration. The additive frontier keeps the source report pinned and makes the causal override explicit: ideal one-byte FP8 semantic KV reduces cache state by 94,220,845,056 bytes and lower-bound total residency by 108,353,971,814 bytes after fragmentation. Even then, the existing 64 × 32K, 16 GB runtime, zero-extra, 15%-fragmentation lower bound totals 661,267,999,028 bytes against 656,000,000,000 usable bytes on four modeled B200s, a 5,267,999,028-byte miss. Exactly 60 full 32K sequences fit while 61 do not; 1,408 fragmentation basis points fit while 1,409 do not. The upper cache bound misses by 104,052,246,836 bytes. These are aggregate-capacity thresholds only: four devices are not evidence for TP4, native kernel support, feasible placement, SLOs, or cost.

The independent-mapping controls now execute E6 at two exact context regimes. Each report uses two integer repetitions of a batch-8, 16-candidate lowerer; residency concurrency is a separate sweep dimension. At both 16,384 and 90,000 tokens, coupled TP16 attention-plus-MoE produces 1,804,861,440 hop bytes and 146,880 messages, including 225,607,680 cross-domain bytes. DP-local attention plus two topology-local EP8 routes produces 255,197,184–255,246,336 hop bytes and 130–132 messages with zero cross-domain bytes in the fixture. The 85.86% byte reduction is exact conditional accounting, not link latency.

Context changes the conditional residency arithmetic sharply. Ideal FP8 semantic MLA state grows from 736,100,352 bytes per 16,384-token request to 4,043,520,000 bytes per 90K request, exactly 5.493164×. At 16K, cluster-total partial residency robustly favors coupled mapping through concurrency 32, overlaps 33–42, and favors decoupled from 43. At 90K those regions become coupled 1–5, overlap 6–7, and decoupled from 8; the balanced max-device comparison switches from 9. Full 90K capacity remains uncertain at concurrency 16: coupled bounds are 108.958–176.788 GB/device and decoupled bounds 65.254–179.901 GB/device under the same 164 GB/device envelope. The missing public non-routed checkpoint mapping prevents a false winner. This demonstrates that context is a mapping-policy input inside the bounded model; it does not directly validate a deployment policy or provider advantage.

The additive [`parallel-mapping-context-frontier-v1.json`](../experiments/glm-5.2/parallel-mapping-context-frontier-v1.json) makes that policy searchable without running a new lowerer for every context. It first reproduces all nine stored 16K and twelve stored 90K residency points exactly, then sweeps only semantic KV because the two lowerers prove other context-dependent work is not safely interpolable. Strict combined cluster/max-device preference changes from coupled/unresolved/decoupled at `1–32 / 33–42 / 43+` for 16K to `1–16 / 17–21 / 22+` at 32K, `1–8 / 9–10 / 11+` at 65K, `1–5 / 6–8 / 9+` at 90K, and decoupled from concurrency 2 at 1M. Candidate full capacity remains uncertain across all concurrency through 262K because the checkpoint-common upper bound is opaque. The engine therefore returns a residency policy frontier, not a deployment winner.

The additive [`agentic-mapping-screen-v1.json`](../experiments/glm-5.2/agentic-mapping-screen-v1.json) applies only the public proxy's input-token counts to this bounded GLM capacity model. Across 64 requests, request-weighted partial-policy counts in coupled/overlap/decoupled order are `64/0/0` at C1, `63/0/1` at C8, `48/0/16` at C16, `24/0/40` at C32, and `8/8/48` at C64. The candidate full-capacity classification is uncertain for all `64/64` requests at every concurrency. Prompt text, tokenizer equivalence, output lengths, arrival timing, tool delays, dynamic-prefix behavior, context-dependent compute, network timing, quality, and SLOs are excluded. This is token-geometry screening, not an agentic serving replay or deployment winner.

The P/D control makes E6’s serving half similarly conditional. Holding fleet cost at eight $7/hour slots, neutral prefill-heavy P/D costs 5.18% more per raw modeled output token than aggregate. Only after explicitly imposing 25% aggregate phase interference and a 20% P/D specialization benefit does the same split become 35.22% cheaper. A congested full-KV transfer endpoint removes that advantage and worse splits regress further. The trace still fails class objectives, excludes continuous batching, and uses uncalibrated phase and transfer rates. The simulator therefore promotes phase-interference and transfer measurements; it does not promote P/D as a universal cost saving.

The MTP sweep turns E5 into a runnable calibration target. Under one illustrative work curve, homogeneous conditional acceptance must exceed 10.0%, 30.0%, 42.4%, and 51.0% at recursive depths one through four. Synthetic high acceptance selects depth two rather than the maximum depth. These thresholds have no performance authority until exact-checkpoint acceptance and draft/verify work are measured.

The tiered-cache experiment turns E4 into a runnable lifecycle model. On one synthetic 15-access agent trace, HBM/host/NVMe reduces recompute tokens from 249,856 to 94,208 but moves 40.562 GB across links. Promotion and demotion produce 2.658× transfer amplification relative to the state corresponding to avoided recompute. This falsifies treating hit ratio alone as the optimization objective; the event model must price recompute, movement, contention, and overlap together.

The whole-decode lowerer replaces the mechanism fixture with a 29-action bound for an eight-request, 16K-context step with 16 aggregate candidate and 12 committed tokens. It proves 837.116 billion exact FFN FLOPs and bounds total work at 837.116 billion to 3.387 trillion FLOPs; FFN HBM reads span 52.320 to 731.797 GB depending on unique routed experts. Attention, DSA, cache, route-residency, other non-FFN, and MTP work remain explicit assumptions, the approximately 40B whole-model active count remains approximate, and every action is uncalibrated. This is materially closer to whole-model work without converting unknowns into facts.

The public NVFP4 lowerer keeps that compute work unchanged while binding NVIDIA's exact 464,794,806,272-byte checkpoint payload and opaque expert-selective storage. Relative to BF16, checkpoint payload falls 69.15% and routed-expert resident bytes fall between 67.94% and 75.00%. The upper FFN read bound falls 36.49%, but its lower bound becomes zero because the public tensor allocation and reuse are opaque; zero is uncertainty, not a claimed eliminated read. The resulting whole-ledger memory upper bound falls only 6.96% because the independent non-FFN/cache envelopes remain conservative.

The fair native-Blackwell roofline makes the hardware ranking fail closed on that opacity. At the zero-FFN-read lower corner, B200 produces 32,344 modeled committed token/s while the nominal custom profile produces 25,046, so custom is only 0.774× B200. At the full-payload upper corner, B200 produces 131.21 and nominal custom 176.05 token/s, so the ratio reverses to 1.342× because 12 TB/s shortens the opaque weight read versus Blackwell's 8 TB/s. B300's higher NVFP4 arithmetic changes the upper result by only 0.03% because HBM and non-routed controls dominate. The custom profile has no native selective-expert-NVFP4 execution contract and is explicitly blocked. The valid conclusion is not that custom wins or loses; it is that exact traffic and a real precision implementation must precede hardware ranking.

The old hardware profiles yield a nominal 3.592× component-time ratio on the whole-decode upper-bound ledger, down from 5.38× on the 222.3M-FLOP mechanism fixture. The modeled H200-like critical path is 252.94 ms versus 70.41 ms for the aggressive profile, and the dominant action is now routed-expert weight traffic. This still is **not a performance claim**: the baseline assumes only 3.35 TB/s rather than a shipped H200's published 4.8 TB/s, the work bounds are not jointly calibrated, and there is no contention, serving, capacity-coupled deployment, energy, or cost result. The original fixture's throughput-only substitution remains 1.054× and its fixed/coordination-only substitution remains 4.079×; together the experiments show why results must be rerun as model coverage increases.

The checked [`whole-decode-throughput-counterfactual-v1.json`](../experiments/glm-5.2/whole-decode-throughput-counterfactual-v1.json) then removes the favorable control-latency comparison entirely. It holds top-k, elementwise, cache, scheduler, synchronization, and all fixed/message charges constant while substituting only headline matrix, HBM, and fabric rates. On the same upper-bound work, the original custom rates are 2.143× the published-peak H200 component baseline, but preliminary Rubin rates are 1.535× faster than custom. Peak rates, common fixed costs, and an aggregate action ledger do not predict deployment throughput; the result is a counterfactual ranking only. Its business consequence is nevertheless clear: 12 TB/s HBM and 2 PFLOP/s are not a future moat. A custom design needs model-specific work removal or a material residual advantage beyond the launch-date commodity stack.

The exact serving replay now connects that same upper-work ledger and roofline to one canonical batch without copying either artifact into each request. A byte-pinned path manifest binds the synthetic SLO contract, fully reused trace, whole-decode lowering, roofline, and ledger content identity before producing three independently content-addressed reports. Eight requests arrive over 7 ms, each starts with exactly 16,384 reused tokens, and the one quantum fairly allocates 12 aggregate commits. The H200, nominal custom, and preliminary Rubin selections produce atomic quantum durations of 183.123 ms, 85.434 ms, and 55.667 ms; including batch-fill time, the synthetic trace reports 63.117, 129.822, and 191.488 output token/s. Those are executable queueing calculations over optimistic component times, not performance measurements. Every synthetic request passes the deliberately loose assumed SLO fixture, and atomic visibility makes intra-quantum TPOT zero; neither result has SLO authority. Prefill, prefix restoration, shared-resource contention, a batch/context quantum table, repeated decoding after context changes, and intra-quantum token timing remain absent, so end-to-end latency, SLO, provider, and cost claims are explicitly false.

The first fail-closed deployment screen uses the lower-work rather than upper-work ledger, because only an optimistic work bound can reject a candidate safely. It then grants a BF16 public-price H200 deployment every remaining advantage: published peak rates, free input-prefill work, and perfectly linear multiplication of one component's output rate across 20 ranks. The result is 364,505 peak billable token/s against a 337,338 token/s hurdle, just 1.0805× headroom. It does not reject the candidate, and all business/cost/provider claims remain false. It does show that only a 7.45% loss from this impossible bound erases the margin, so BF16 public rental is too fragile to underwrite. Public NVFP4 is the next required screen.

The lower/upper comparison also sets the research order. Optimistic lower-work capacity is 17.98×, 20.56×, and 24.66× the upper-work capacity on the H200, nominal custom, and Rubin component profiles respectively. This uncertainty is far larger than their modeled separation. The simulator should therefore spend its next fidelity budget on measured expert reuse/locality, exact DSA and non-FFN work, and MTP behavior before refining hardware peak rates.

The DSA sweep makes a narrower architecture conclusion. Exact GLM-5.2 IndexShare removes 57 of 78 indexer executions, a 73.08% scan/weight-set reduction. Under the explicitly modeled serial component roofline, same-geometry every-layer indexing is 2.87–3.65× longer than IndexShare and dense-versus-sparse core attention crosses over between 2K and 8K context. These ratios describe only the DSA component and are an incumbent model benefit, not our speedup. More importantly, deleting every modeled HBM selected-index write/read changes component time by only 0.01–0.14%. That rejects selected-index SRAM handoff as a standalone cost lever; scan/top-k fusion, irregular compressed-cache gather, and MTP reuse remain the material hypotheses.

The physical-feasibility audit gives a **conditional GO for model/software co-design and a NO-GO for tapeout**. The profile's 12 TB/s HBM, 1.6 TB/s fabric, and 2 PFLOP/s engines are plausible, but do not exceed relevant current or announced commodity peaks. More importantly, the timing vector has no capacity, precision, power, area, package, yield, NRE, or landed-cost contract. Expert-selective NVFP4 still requires 3–4 devices at 288 GB for the modeled residency; a single-package target needs 17–19 future 48 GB HBM4E stacks and only arithmetically fits the announced 2028 20-stack envelope. Full active-work lowering, launch-date commodity baselines, quality/SLO measurement, PPA, supplier-backed packaging, and fully loaded economics are required before hardware commitment.

The first independent native array sweep reinforces the NO-GO. SCALE-Sim ranks OS32 first for both exact Qwen `o_proj` and the GLM routed-expert gate reference, with the same OS32→IS32→WS64→WS32→WS16 order. It exposes large mapping sensitivity inside the oracle—OS32 uses 2.925× fewer prefetch-inclusive cycles than WS32 on the GLM operator—but no model-specific ranking change. Increasing WS32 SRAM from 64 KiB to 4 MiB changes neither native filter reads nor core cycles and worsens the inclusive count. This does not prove the models want identical real hardware; the oracle lacks BF16/NVFP4, HBM calibration, full routing, and serving. It does falsify using model identity or “more SRAM” as sufficient evidence for a custom device.

The MoE route experiment makes E3 executable over exact 75-layer × 256-expert × top-8 geometry. A synthetic source-affine hotset lets traffic-aware primary placement reduce eight-device fully connected remote traffic 35.53% with no additional expert storage. Adding 1,024 replicas then costs 77.31 GB and reduces remote dispatch only another 4.12%; under uniform routing the same replication budget saves just 0.76%. The current hypothesis is therefore placement before replication, contingent on measured route stability. Even under ideal fixed-cost arithmetic, fully connected endpoint reduction cannot exceed a 1.551× overall speedup and ring hop reduction cannot exceed 2.641×, so route placement alone cannot explain 5×.

## Transfer risks from Qwen3-0.6B / Qwen3-8B

| Qwen assumption or evidence | GLM-5.2 difference | Transfer decision |
|---|---|---|
| Dense 0.6B/8B decoder | 753B resident MoE, about 40B active, sparse top-8 routing | Dense weight-bandwidth and batching conclusions do not transfer. |
| 36 layers, hidden 4,096 | 78 layers, hidden 6,144 | Tile, fusion, accumulated numerical error, and launch conclusions must be remeasured. |
| GQA with eight KV heads | MLA latent cache plus content-selected DSA and separate indexer state | `kv_head_count` interventions and cache formulas do not transfer. |
| 32,768 context and current trace ≤28,672 | 1,048,576 context; vendor coding average >70K | Long prefill, host/cache management, CP, PD, and network become first-order. |
| Single-device Qwen baseline | Practical GLM FP8 starts around TP8 and can require multi-node BF16 | Interconnect and expert parallelism cannot be treated as secondary overhead. |
| Repeated dense gated MLP | 75 sparse layers ×256 routed experts plus shared expert | Full-layer fusion must handle routing, all-to-all, irregular expert batches, and barriers. |
| No MTP in fixture | Shared recursive MTP is a main GLM decode mechanism | TPOT and output-cost models require acceptance/rejection work. |
| Naive symmetric W4 QDQ failed on Qwen3-0.6B | NVIDIA selectively quantizes GLM routed experts with NVFP4 and publishes positive benchmark evidence | Qwen failure neither validates nor invalidates GLM NVFP4; evidence scopes must remain separate. |
| Qwen FP8 KV / fewer KV-head hypotheses | GLM already compresses KV through MLA and sparsifies attention | Marginal cache changes may have different quality and cost leverage. |
| Qwen tokenizer/chat template | GLM has reasoning modes, `<think>` handling, `glm45` reasoning parsing, and `glm47` tool calls | Prefix identity, output accounting, and task quality need GLM-native traces. |
| Existing Qwen custom ASIC shape | GLM expert storage, random gather, top-k, and distributed fabric dominate different resources | Hardware must be re-synthesized from GLM phase work; no Qwen area/bandwidth point transfers. |

The frozen [proxy ladder](SMALL_MODEL_PROXY_SELECTION.md) keeps Qwen3-0.6B for local simulator invariants, quality-bearing model edits, dense accounting, trace replay, and evidence-gating plumbing. NOSA-1B is the next sparse-locality/offload proxy only after its pinned stack runs on a suitable CUDA GPU. Neither is a performance or cost proxy for GLM-5.2, and passing either ladder promotes only a GLM-specific experiment.

## Decision gates

### Continue to model-specific software experiments when

1. The GLM lowerer reconciles released tensor inventories and cache formulas.
2. At least two independent interventions show a robust analytical cost reduction above 10% across the frozen workload, uncertainty, and route distributions.
3. The predicted gain remains after comparing against native FP8 and NVIDIA NVFP4 rather than BF16 alone.
4. Cache correctness and failed-request accounting pass stress tests.

### Rent real hardware when

1. The simulator identifies a small set of candidate mappings with distinct falsifiable bottleneck predictions.
2. The benchmark plan pins model, revision, precision, engine, topology, parser, reasoning mode, MTP settings, trace, and quality suite.
3. The experiment records TTFT, TPOT, MTP acceptance, prefix hits, route imbalance, HBM, network, power, failures, and output correctness.
4. Exact-scope predictions are locked before blinded measurements, with calibration and holdout cases non-overlapping; the current predictive gate has one admitted but magnitude-inaccurate component pair.

### Do not start custom silicon unless

1. The best model-specific software/kernel stack achieves the repository's required measured 1.5× cost reduction over the best tuned incumbent baseline.
2. A second model retains at least 1.5× measured gain.
3. At least 30% residual benefit remains attributable to custom silicon after Rubin/MI450-class baselines, persistent kernels, and approved model changes.
4. The custom-hardware projection retains at least 4× launch-date advantage in the base case and 2× under pessimistic performance, utilization, yield, NRE, memory, network, and incumbent-improvement assumptions.
5. Expert quantization, DSA, cache hierarchy, and networking gains survive independent external simulation and physical feasibility review with supplier-backed capacity and package margins.
6. The predictive-validity gate is met on held-out hardware and exact quality/SLO evidence permits cost promotion.

### Stop or redirect the hardware thesis when

- Tuned NVFP4 plus current vLLM/SGLang sits within 20% of the modeled lower bound.
- The apparent win comes primarily from an unrealistic >90% prefix hit or >100K context share.
- Commodity network/cache improvements capture most of the benefit without model-specific silicon.
- The residual gain attributable to silicon is below 30% after launch-date commodity, persistent-kernel, and model-change baselines.
- Model changes needed for the remaining gain fail agentic non-inferiority or require prohibitive retraining.
- The design cannot amortize NRE while beating the official $1.40 input / $4.40 output retail price with a credible margin and downside case.

## Current unknowns

These values must remain explicit unknowns until measured or derived from a pinned tensor/trace artifact:

- Exact active parameter count and operations by tensor class for the released checkpoint.
- Per-layer expert routing distribution, temporal locality, and imbalance on our agent trace.
- MTP acceptance distribution for Max/High/non-think under our prompts and sampling settings.
- Exact engine-specific main and indexer-cache bytes, replication, padding, and fragmentation.
- Prefix-hit distribution after real client chat-template rendering.
- LayerSplit, CP, and PD benefit on the 5.2 checkpoint rather than 5.1/vendor setups.
- Power and energy by expert GEMM, index scan, sparse gather, collective, cache transfer, and idle state.
- Provider marginal cost, utilization, failure reserve, and gross margin.
- Wafer, package, HBM, NIC, host, yield, NRE, and deployment-volume inputs for custom hardware.
- Quality sensitivity to any new quantization, adaptive top-k, expert-count, index-pattern, or cache-sharing change.

## Primary-source ledger

All sources below are first-party model, framework, hardware-variant, or research artifacts. Accessed 2026-07-12.

- [Z.ai: GLM-5.2 release and architecture](https://z.ai/blog/glm-5.2)
- [Z.ai: GLM-5 release](https://z.ai/blog/glm-5)
- [Official GLM-5 series repository](https://github.com/zai-org/GLM-5)
- [GLM-5 technical report](https://arxiv.org/pdf/2602.15763)
- [IndexCache technical paper](https://arxiv.org/html/2603.12201)
- [Pinned GLM-5.2 BF16 checkpoint](https://huggingface.co/zai-org/GLM-5.2/tree/b4734de4facf877f85769a911abafc5283eab3d9)
- [Pinned GLM-5.2 FP8 checkpoint](https://huggingface.co/zai-org/GLM-5.2-FP8/tree/ba978f7d347eaf65d22f1a86833408afdb953541)
- [NVIDIA GLM-5.2 NVFP4 model card](https://huggingface.co/nvidia/GLM-5.2-NVFP4)
- [vLLM GLM-5.2 deployment recipe](https://recipes.vllm.ai/zai-org/GLM-5.2)
- [SGLang GLM-5.2 deployment cookbook](https://docs.sglang.io/cookbook/autoregressive/GLM/GLM-5.2)
- [KTransformers GLM-5.2 heterogeneous deployment tutorial](https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/kt-kernel/GLM-5.2-Tutorial.md)
- [Z.ai: GLM-5 coding-agent serving failures and LayerSplit](https://z.ai/blog/scaling-pain)
- [Z.ai: ZCube inference-network deployment](https://z.ai/blog/zcube)
- [Z.ai API pricing](https://docs.z.ai/guides/overview/pricing)

## Defensible conclusion today

GLM-5.2 is unusually suitable for a model-specific co-design test because the released architecture exposes stable, non-generic work: overwhelmingly expert-resident weights, sparse top-8 routing, compressed MLA cache, a top-2048 content index, an exact cross-layer index-sharing schedule, and a shared MTP path. Official deployments already demonstrate that changes spanning model training, kernels, caching, scheduling, and networking can materially move performance.

That evidence supports building a faithful GLM simulation and measuring whether the gains compound economically. It does not show that a new company can yet serve GLM-5.2 below incumbent cost, and it does not justify a chip. The first honest milestone is a GLM-aware analytical and event model that reconciles the released checkpoint, reproduces the direction and uncertainty of official deployment results, and compares proposed changes against FP8 and NVFP4 with cache correctness and agent quality held fixed.
