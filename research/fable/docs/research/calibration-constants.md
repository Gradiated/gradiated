# Calibration Constants for the Sartor Simulator

Compiled 2026-07-11 from an 8-agent web research workflow. Every constant carries value, unit, source URL, as-of date, and confidence. Numbers marked **CONFLICT** have disagreeing sources — both values are given; do not silently pick one.

Companion synthesis: [strategy.md](strategy.md).

---

## 1. Model Architectures

All parameters below were read from the primary `config.json` on Hugging Face, fetched 2026-07-11 unless noted. Confidence: **high** for every row sourced from a config.json.

### 1.1 Frontier MoE targets

| Model | Total / active params | Layers | Hidden | Attention | KV scheme | Experts (routed top-k + shared) | moe_intermediate | Dense layers (intermediate) | Vocab | Max ctx | MTP | Native precision | Source |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GLM-4.5 | 355B / 32B | 92 | 5120 | GQA 96Q/8KV, head_dim 128, partial_rotary 0.5 | GQA | 160 top-8 + 1 | 1536 | first 3 (12288) | 151552 | 131072 | 1 | bf16 (+ official FP8 repo) | [config.json](https://huggingface.co/zai-org/GLM-4.5/resolve/main/config.json) |
| GLM-4.5-Air | 106B / 12B | 46 | 4096 | GQA 96Q/8KV, head_dim 128 | GQA | 128 top-8 + 1 | 1408 | first 1 (10944) | 151552 | 131072 | 1 | bf16 (+ FP8 repo) | [config.json](https://huggingface.co/zai-org/GLM-4.5-Air/resolve/main/config.json) |
| GLM-4.6 | 355B / 32B | 92 | 5120 | identical to GLM-4.5 | GQA | 160 top-8 + 1 | 1536 | first 3 | 151552 | 202752 | 1 | bf16 (+ FP8 repo) | [config.json](https://huggingface.co/zai-org/GLM-4.6/resolve/main/config.json) |
| GLM-5 (Feb 2026) | 744B / 40B (see CONFLICT below) | 78 | 6144 | MLA, 64 heads: kv_lora_rank 512, q_lora_rank 2048, qk_rope 64, qk_nope 192, v_head_dim 256 | MLA + DSA (indexer 32 heads x 128, top-k 2048) | 256 top-8 + 1 | 2048 | first 3 (12288) | 154880 | 202752 | 1 | bf16 (+ FP8 repo) | [config.json](https://huggingface.co/zai-org/GLM-5/resolve/main/config.json) |
| GLM-5.1 (Apr 2026) | shape-identical to GLM-5 | 78 | 6144 | same | MLA + DSA | 256 top-8 + 1 | 2048 | first 3 | 154880 | 202752 | 1 | bf16 | [config.json](https://huggingface.co/zai-org/GLM-5.2/resolve/main/config.json) |
| GLM-5.2 (Jun 2026) | shape-identical to GLM-5 | 78 | 6144 | same | MLA + DSA | 256 top-8 + 1 | 2048 | first 3 | 154880 | **1048576** (1M) | 1 | bf16 | [config.json](https://huggingface.co/zai-org/GLM-5.2/resolve/main/config.json) |
| DeepSeek-V3 / R1 | 671B / 37B | 61 | 7168 | MLA, 128 heads: kv_lora_rank 512, q_lora_rank 1536, qk_rope 64, qk_nope 128, v_head_dim 128 | MLA (576-dim cached latent) | 256 top-8 + 1 | 2048 | first 3 (18432) | 129280 | 163840 | 1 | FP8 e4m3, 128x128 block-scaled | [config.json](https://huggingface.co/deepseek-ai/DeepSeek-V3/resolve/main/config.json) |
| DeepSeek-V3.2 (Dec 2025) | 671B / 37B (V3 body exactly) | 61 | 7168 | same as V3 | MLA + DSA (indexer 64 heads x 128, top-k 2048) | 256 top-8 + 1 | 2048 | first 3 | 129280 | 163840 | 1 | FP8 native | [config.json](https://huggingface.co/deepseek-ai/DeepSeek-V3.2/resolve/main/config.json) |
| Kimi-K2 | 1T / 32B | 61 | 7168 | MLA, 64 heads (vs DS 128), same 512+64 latent | MLA | 384 top-8 + 1 | 2048 | first 1 | 163840 | 131072 (Thinking: 262144) | **0** | K2-Thinking: **INT4 group-32 weight-only** | [config.json](https://huggingface.co/moonshotai/Kimi-K2-Instruct/resolve/main/config.json), [K2-Thinking](https://huggingface.co/moonshotai/Kimi-K2-Thinking/resolve/main/config.json) |
| Qwen3-30B-A3B | 30.5B / 3.3B | 48 | 2048 | GQA 32Q/4KV, head_dim 128 | GQA | 128 top-8, **no shared** | 768 | none | 151936 | 40960 | — | bf16 | [config.json](https://huggingface.co/Qwen/Qwen3-30B-A3B/resolve/main/config.json) |
| Qwen3-235B-A22B | 235B / 22B | 94 | 4096 | GQA 64Q/4KV, head_dim 128 | GQA | 128 top-8, no shared | 1536 | none | 151936 | 40960 | — | bf16 | [config.json](https://huggingface.co/Qwen/Qwen3-235B-A22B/resolve/main/config.json) |
| MiniMax-M1-80k | 456B / 45.9B | 80 | 6144 | hybrid: 7/8 layers lightning (linear) attn; 10/80 softmax GQA 64Q/8KV head_dim 128, rotary 64 | hybrid | 32 top-2 | — | — | 200064 | 10240000 | — | bf16 | [config.json](https://huggingface.co/MiniMaxAI/MiniMax-M1-80k/resolve/main/config.json) |
| MiniMax-M2 / M2.1 | 230B / 10B | 62 | 3072 | full softmax GQA 48Q/8KV head_dim 128 (linear attention **abandoned**) | GQA | 256 top-8 | 1536 | — | 200064 | 196608 | — | FP8 e4m3 block 128x128 | [config.json](https://huggingface.co/MiniMaxAI/MiniMax-M2/resolve/main/config.json) |

**CONFLICT — GLM-5.x total parameters:** zai's own model card says 744B; media reports say 753–754B for 5.1/5.2. Configs are shape-identical across 5.0/5.1/5.2, so the discrepancy is unexplained. Recompute from the safetensors index if precision matters. Source: [zai-org/GLM-5](https://huggingface.co/zai-org/GLM-5/resolve/main/config.json), as of 2026-07-11.

**Unverified — DeepSeek-V4** (media: Apr 2026, ~1.6T MoE / ~49B active, 1M ctx, hybrid CSA+HCA attention, claimed ~27% of V3.2 per-token FLOPs and ~10% KV at 1M ctx): config.json is gated (HTTP 401). All V4 numbers are secondary reporting only ([morphllm.com/deepseek-v4](https://www.morphllm.com/deepseek-v4)). Confidence: **low**. Do not encode in the simulator until the tech report is obtained.

**Convergence fact (high confidence):** Chinese frontier labs have converged on one serving recipe — MLA 576-dim latent KV + 256–384 fine-grained experts top-8 + 1 shared + MTP head + native FP8, and since late 2025 a top-k=2048 DSA sparse-attention indexer shared by DeepSeek-V3.2 and GLM-5.x. Cross-checked across [DeepSeek-V3.2](https://huggingface.co/deepseek-ai/DeepSeek-V3.2/resolve/main/config.json), [GLM-5](https://huggingface.co/zai-org/GLM-5/resolve/main/config.json), [Kimi-K2](https://huggingface.co/moonshotai/Kimi-K2-Instruct/resolve/main/config.json). One kernel/silicon suite covers most of the family, and shapes are stable across point releases (GLM 5.0→5.2 and MiniMax M2→M2.1 tensor-identical).

### 1.2 Local lab models

All from HF config.json, fetched 2026-07-11, confidence high.

| Model | Arch | Hidden | Layers | Heads (Q/KV, head_dim) | Intermediate | Vocab | Ctx | Embeddings | Notes | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| SmolLM2-135M-Instruct | Llama | 576 | 30 | 9/3, 64 | 1536 | 49152 | 8192 | tied | rope_theta 100000 | [config.json](https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct/resolve/main/config.json) |
| SmolLM2-360M-Instruct | Llama | 960 | 32 | 15/5, 64 | 2560 | 49152 | 8192 | tied | rope_theta 100000 | [config.json](https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct/resolve/main/config.json) |
| SmolLM2-1.7B-Instruct | Llama | 2048 | 24 | 32/32 (**full MHA**), 64 | 8192 | 49152 | 8192 | tied | unusually KV-heavy (8 KB/token/layer) | [config.json](https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct/resolve/main/config.json) |
| Qwen2.5-0.5B-Instruct | Qwen2 | 896 | 24 | 14/2, 64 | 4864 | 151936 (embedding-dominated) | 32768 | tied | rope_theta 1e6 | [config.json](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/main/config.json) |
| Qwen3-0.6B | Qwen3 | 1024 | 28 | 16/8, explicit head_dim 128 (Q proj 2048-dim, wider than hidden) | 3072 | 151936 | 40960 | tied | QK-norm | [config.json](https://huggingface.co/Qwen/Qwen3-0.6B/resolve/main/config.json) |
| granite-3.1-1b-a400m-instruct | GraniteMoe | 1024 | 24 | 16/8, 64 | 32 experts top-8, per-expert 512 | 49155 | 131072 | tied | **Multipliers must be honored or outputs are garbage:** embedding 12, residual 0.22, attention 0.0078125, logits_scaling 6.0; rope_theta 1.5e6 | [config.json](https://huggingface.co/ibm-granite/granite-3.1-1b-a400m-instruct/resolve/main/config.json) |

Small-model regime note: Qwen2.5-0.5B / Qwen3-0.6B are embedding-dominated (vocab 151936 vs hidden ~1K, tied embeddings) — small-model $/token is lm_head-bound, unlike frontier models.

### 1.3 Derived per-model constants (computed from configs, as-of 2026-07-11)

KV cache bytes/token, bf16 (2 × kv_heads × head_dim × 2B × layers; halve for FP8 cache):

| Model | B/token/layer | B/token total | Scheme |
|---|---|---|---|
| GLM-4.5 / 4.6 | 4096 | 376,832 (92L) | GQA |
| GLM-4.5-Air | 4096 | 188,416 (46L) | GQA |
| DeepSeek-V3/R1/V3.2, Kimi-K2 | 1152 | 70,272 (61L) | MLA latent (512+64=576 dims) |
| GLM-5 / 5.1 / 5.2 | 1152 | 89,856 (78L) | MLA latent |
| Qwen3-235B-A22B | 2048 | 192,512 (94L) | GQA |
| Qwen3-30B-A3B | 2048 | 98,304 (48L) | GQA |
| MiniMax-M2 / M2.1 | 4096 | 253,952 (62L) | GQA, all layers |
| MiniMax-M1-80k | — | 40,960 (10 softmax layers only, + O(1) linear-attn state × 70 layers) | hybrid |
| SmolLM2-135M / 360M / 1.7B | — | 23,040 / 40,960 / 196,608 | GQA / GQA / MHA |
| Qwen2.5-0.5B / Qwen3-0.6B / granite-1b-a400m | — | 12,288 / 114,688 / 49,152 | GQA |

Caveat: DSA models' figures are the stored latent cache only; the DSA indexer's own key cache (index_head_dim 128/token) adds a small unaccounted footprint — measure from a running engine.

Other derived constants:

| Constant | Value | Unit | Source | As-of | Confidence |
|---|---|---|---|---|---|
| DSA sparse attention top-k (DeepSeek-V3.2, GLM-5.x) | 2048 tokens attended per query; indexer 64×128 (DS) / 32×128 (GLM) | tokens | `index_topk` in both config.json | 2026-07-11 | high |
| Active params per decoded token (weight-stream bandwidth floor = active params × bytes/param) | GLM-5 40B; DeepSeek-V3.x 37B; Kimi-K2 32B; Qwen3-235B 22B; MiniMax-M2 10B | params | HF model cards + configs | 2026-07-11 | high |
| Experts loaded per token per MoE layer | 8 routed + 0–1 shared (8–9), from pools of 32–384 | experts | `num_experts_per_tok` + `n_shared_experts` | 2026-07-11 | high |
| Expert FFN GEMM shapes (hidden × moe_intermediate) | GLM-4.5 5120×1536; GLM-5 6144×2048; DeepSeek/Kimi 7168×2048; Qwen3-235B 4096×1536; Qwen3-30B 2048×768; MiniMax-M2 3072×1536 | dims | HF configs | 2026-07-11 | high |
| MTP heads shipped in weights | `num_nextn_predict_layers=1` on GLM-4.5/4.6/5.x and DeepSeek-V3.x; 0 on Kimi-K2 | heads | HF configs | 2026-07-11 | high |
| MTP self-speculative decode gain | ~1.5–2x decode | x | inferred from MTP configs + engine reports — acceptance rates need primary measurement | 2026 | medium |

---

## 2. Hardware Economics

### 2.1 GPU rental prices

| Metric | Value | Unit | Source | As-of | Confidence |
|---|---|---|---|---|---|
| H100 SXM rental (neocloud floor / median) | 1.49–1.68 / 2.29–2.45 | $/GPU-hr | [intuitionlabs.ai](https://intuitionlabs.ai/articles/h100-rental-prices-cloud-comparison), [thundercompute.com](https://www.thundercompute.com/blog/nvidia-h100-pricing) | 2026-07 | high |
| H200 rental on-demand | 3.89–4.54 (CoreWeave 3.89, RunPod 4.39, Lambda 4.49) | $/GPU-hr | [spheron.network](https://www.spheron.network/blog/gpu-cloud-pricing-comparison-2026/) | 2026-H1 | high |
| B200 rental (on-demand / spot) | 3.99–5.89 / 2.12 | $/GPU-hr | [spheron.network](https://www.spheron.network/blog/gpu-cloud-pricing-comparison-2026/) | 2026-H1 | high |
| GB200 NVL72 rental | 10.5–18+ per GPU (rack $756–1,944/hr) | $/GPU-hr | [getdeploying.com](https://getdeploying.com/gpus/nvidia-gb200), [spheron.network](https://www.spheron.network/blog/nvidia-gb200-nvl72-guide/) | 2026-05 | medium (wide spread; reserved rates much lower, private) |
| MI300X rental (floor / median) | 1.99 / 2.72 — cheapest $/GB-HBM in market | $/GPU-hr | [getdeploying.com](https://getdeploying.com/gpus/amd-mi300x), [thundercompute.com](https://www.thundercompute.com/blog/amd-mi300x-pricing) | 2026-07 | medium |
| MI355X rental | 2.59–8.60 (highly dispersed) | $/GPU-hr | [getdeploying.com](https://getdeploying.com/gpus/amd-mi355x) | 2026-07 | medium |
| Baseten dedicated H100 / B200 (active-time billed, scale-to-zero) | 6.50 / 9.98 | $/GPU-hr | [baseten.co/pricing](https://www.baseten.co/pricing/) | 2026-07-11 | medium |
| Cloud accelerator list: TPU v6e / B200 / Trainium 3 | 2.7 / 5.5 / ~1.0 | $/chip-hr | [spheron.network hyperscaler chips](https://www.spheron.network/blog/hyperscaler-custom-ai-chips-2026-trainium-tpu-maia-mtia-vs-nvidia-gpu/), [oplexa.com](https://oplexa.com/amazon-trainium-3-vs-nvidia-blackwell/) | 2026-H1 | medium |

### 2.2 GPU purchase prices and power

| Metric | Value | Unit | Source | As-of | Confidence |
|---|---|---|---|---|---|
| H100 unit price | 25,000–40,000 (trending toward ~20,000) | $ | [siliconanalysts.com](https://siliconanalysts.com/analysis/nvidia-gpu-prices-double-as-ai-demand-overwhelms-supply-chain) | 2026-H1 | high |
| B200 unit price | 30,000–50,000 | $ | [intuitionlabs.ai](https://intuitionlabs.ai/articles/nvidia-ai-gpu-pricing-guide) | 2026-H1 | high |
| GB200 superchip ASP | 60,000–70,000 | $ | [siliconanalysts.com](https://siliconanalysts.com/analysis/nvidia-gpu-prices-double-as-ai-demand-overwhelms-supply-chain) | 2026-H1 | high |
| GB200 NVL72 rack | ~3,000,000 (HSBC est.) | $/rack (72 GPUs) | [x.com/firstadopter](https://x.com/firstadopter/status/1940792115124228482) | 2025-07, still current mid-2026 | high |
| Vera Rubin NVL72 rack (quoted) | up to 8,800,000 | $/rack | [tomshardware.com](https://www.tomshardware.com/tech-industry/artificial-intelligence/price-of-nvidias-vera-rubin-nvl72-racks-skyrockets-to-as-much-as-usd8-8-million-apiece-but-server-makers-margins-will-be-tight-nvidia-is-moving-closer-to-shipping-entire-full-scale-systems) | 2026 | medium |
| TPU v7 Ironwood per chip | 4.6 PFLOPS FP8, 192GB HBM3e @ 7.4 TB/s, ~1000W, est. **$15K unit cost (secondhand analyst estimate)** | mixed | [SemiAnalysis TPUv7](https://newsletter.semianalysis.com/p/tpuv7-google-takes-a-swing-at-the) | 2025-11–2026 | medium |
| TDP: H100 / H200 / B200 / GB200-per-GPU / MI300X / MI355X | 700 / 700 / 1000 / ~1200 / 750 / 1400 | W | vendor datasheets via [trgdatacenters.com](https://www.trgdatacenters.com/resource/nvidia-h100-power-consumption/), [spheron.network](https://www.spheron.network/blog/nvidia-gb200-nvl72-guide/) | 2026 | high |
| Real inference draw vs TDP (decode-heavy / prefill-heavy) | 0.5–0.6 / 0.85–0.95 (8xH100 node ~10 kW under load) | × TDP | [spheron.network power](https://www.spheron.network/blog/ai-inference-power-electricity-cost-2026/) | 2026 | medium — **not measured on B200/GB200/MI355X; needs primary measurement** |

### 2.3 Memory prices and bandwidth

| Metric | Value | Unit | Source | As-of | Confidence |
|---|---|---|---|---|---|
| HBM3e contract price | 13–17 (**CONFLICT:** cost-optimized quotes 8–10 exist; +20% QoQ hike announced for 2026 supply; H1'25 peak 17–20) | $/GB | [siliconanalysts.com/data/hbm-pricing](https://siliconanalysts.com/data/hbm-pricing), [trendforce.com](https://www.trendforce.com/news/2025/12/24/news-samsung-sk-hynix-reportedly-plan-20-hbm3e-price-hike-for-2026-as-nvidia-h200-asic-demand-rises/) | 2026-H1 | medium |
| HBM4 price (initial) | ~14 (~$500 per 36GB-class stack) | $/GB | [siliconanalysts.com/data/hbm-pricing](https://siliconanalysts.com/data/hbm-pricing) | 2026-07 | medium |
| DDR5 street price | 12–16, rising (record up-cycle: +90–95% QoQ 1Q26 contract, +58–63% QoQ forecast 2Q26) | $/GB | [tomshardware.com RAM index](https://www.tomshardware.com/pc-components/ram/ram-price-index-2026-lowest-price-on-ddr5-and-ddr4-memory-of-all-capacities), [siliconanalysts.com](https://siliconanalysts.com/market-data) | 2026-07 | high |
| LPDDR5X / GDDR7 $/GB | **GAP — no reliable public per-GB contract number.** Directional: NVIDIA LPDDR5X pull may double server DRAM/LPDDR5X prices in 2026 | $/GB | [tomshardware.com](https://www.tomshardware.com/pc-components/dram/nvidias-demand-for-lpddr5x-could-double-smartphone-and-server-memory-prices-in-2026-seismic-shift-means-even-smartphone-class-memory-isnt-safe-from-ai-induced-crunch) | 2026 | low |
| Bandwidth per package: HBM3e / HBM4 / GDDR7 / LPDDR5X-x64 | 1200 / 2000 (up to 3300 advanced) / 128 (32 GT/s device) / 68 (8.533 Gb/s) | GB/s | [Siemens packaging blog](https://blogs.sw.siemens.com/semiconductor-packaging/2026/04/24/hbm3e-hbm4-ic-design-guide/), [JEDEC](https://www.jedec.org/sites/default/files/Final_Kos_Gitchev_LPDDR_GDDR_HBM_Auto_AI_Applications_v3.pdf) | 2026 | high |

### 2.4 Silicon: wafers, NRE, packaging

| Metric | Value | Unit | Source | As-of | Confidence |
|---|---|---|---|---|---|
| TSMC 300mm wafer: N3/N3E / N5-N4 / N7 | ~19,500 ($17–22K) / ~18,500 ($16–21.3K) / ~10,000; +5–10% hikes announced for 2026; low-volume/spot +20–40% | $/wafer | [siliconanalysts.com/data/wafer-pricing](https://siliconanalysts.com/data/wafer-pricing), [tomshardware.com](https://www.tomshardware.com/tech-industry/tsmcs-wafer-pricing-now-usd18-000-for-a-3nm-wafer-increased-by-over-3x-in-10-years-analyst), [semiwiki.com](https://semiwiki.com/forum/threads/tsmc-to-raise-foundry-prices-by-5-10-across-advanced-nodes-in-2026.23508/) | 2026 | high |
| Mask set: N5 / N3 | 5–8M / 10–20M (complex designs toward 40M) | $ | [siliconanalysts.com fabless guide](https://siliconanalysts.com/analysis/fabless-startup-tapeout-cost-guide), [SemiAnalysis](https://newsletter.semianalysis.com/p/the-dark-side-of-the-semiconductor) | 2025–2026 | medium |
| Full tapeout (masks + shuttle + eng) | ~40–50M at 5nm; ~100M at 2nm | $ | [siliconanalysts.com](https://siliconanalysts.com/analysis/fabless-startup-tapeout-cost-guide) | 2026 | medium |
| Full-chip design NRE | **CONFLICT / assumption-laden:** analyst full-chip 200–400M (N5) / 400–600M+ (N3) all-in; lean IP-reuse inference ASIC on N4 plausibly 50–150M. The reuse assumption is load-bearing. | $ | [siliconanalysts.com](https://siliconanalysts.com/guide/semiconductor-costs), [granitefirm.com](https://www.granitefirm.com/blog/us/2023/04/29/cost-of-chip-foundry/) | 2026 | medium |
| CoWoS package: H100-class S / B200-class L | 750 / 1000–1100 (≈$300–500 interposer + $200–400 assembly + $100–200 test); capacity ~120–130K wpm by end 2026 | $/package | [siliconanalysts.com/tools/packaging](https://siliconanalysts.com/tools/packaging), [trendforce.com](https://www.trendforce.com/news/2026/04/28/news-tsmc-cowos-wafer-asp-reportedly-nears-7nm-levels-advanced-packaging-poised-to-become-a-key-profit-driver/) | 2026 | medium |
| N3/N4 defect density (yield model) | **GAP** — no dated open source; TSMC mature N5 reportedly ~0.05–0.1 def/cm² (uncited). Treat as assumption. | def/cm² | — | 2026 | low |

### 2.5 Energy

| Metric | Value | Unit | Source | As-of | Confidence |
|---|---|---|---|---|---|
| Memory access energy: SRAM / HBM3 / HBM4 (est.) / GDDR6-6X / LPDDR5-DDR5 system / HBM2 / DDR3 | 0.1–0.4 / 2.5 / ~1.5 / 4.2–5.5 / ~15 / 3.9–4.0 / ~20 (**CONFLICT:** LPDDR5 device-level ~4–6 vs 15 system-level — pin vs system definitions vary) | pJ/bit | [wevolver HBM3 guide](https://www.wevolver.com/article/what-is-high-bandwidth-memory-3-hbm3-complete-engineering-guide-2025), [NVIDIA Fine-Grained DRAM, MICRO 2017](https://research.nvidia.com/sites/default/files/pubs/2017-10_Fine-Grained-DRAM:-Energy-Efficient/oconnor_and_chatterjee.micro2017.pdf), [emergentmind](https://www.emergentmind.com/topics/ai-and-ml-accelerators) | 2025–2026 | medium |
| Whole-chip compute energy (dense, at TDP): H100 FP8 / B200 FP8 / B200 FP4 | 0.35 / 0.22 / 0.11 | pJ/FLOP | derived from NVIDIA datasheet TFLOPS ÷ TDP (H100 1979 TF @700W; B200 4.5 PF @~1000W, FP4 9 PF) | 2026 | medium |
| Academic MAC energy (older node) | BF16 MAC ~5.35 pJ; FP32 MAC ~26.8 pJ. Raw MAC-array energy on N4/N3 is ~10x below whole-chip pJ/FLOP — the gap is data movement (this is the co-design lever). Modern-node FP8/FP4 MAC table is a **GAP** (needs ISSCC 2024–26). | pJ/op | [emergentmind](https://www.emergentmind.com/topics/ai-and-ml-accelerators) | 2025 | medium |
| PUE: industry avg / public cloud / hyperscale best / on-prem enterprise | 1.56 / 1.25 / 1.09–1.14 (AWS fleet 1.14 in 2025) / 1.63 | ratio | [thenetworkinstallers.com](https://thenetworkinstallers.com/blog/data-center-energy-consumption-statistics/) | 2026 | high |
| Industrial electricity: US avg / TX / CA / cheap states / EU / Asia | 0.08–0.09 / 0.081 / 0.176 / 0.047 / ~0.22 (EUR 0.199) / 0.107 | $/kWh | [electricchoice.com](https://www.electricchoice.com/electricity-prices-by-state/), [businesseurope.eu](https://www.businesseurope.eu/media-room/data-hub/high-cost-of-energy/), [globalpetrolprices.com](https://www.globalpetrolprices.com/electricity_prices/) | 2026-H1 | medium |
| Electricity share of GPU-hour cost | <5% at $1.50/hr rental (~$0.06–0.07/hr for H100 at 420W chip, PUE 1.25, $0.09/kWh). Capex depreciation dominates $/token. | % | derived from rows above | 2026 | high |

### 2.6 Owned-hardware TCO anchor (simulator default)

Owned $/hr = unit price / (3yr × 8760 × utilization) + power × PUE × $/kWh.
Worked example: **B200 at $40K, 70% util, 850W avg, PUE 1.25, $0.09/kWh ≈ $2.17 + $0.10 ≈ $2.3/GPU-hr** — roughly 2x cheaper than on-demand rental ($4.5–6). Derived from constants above; confidence high (arithmetic), inputs medium.

---

## 3. SOTA Serving Performance Anchors (calibration targets)

The simulator should reproduce each anchor within ~20%. Fix the interactivity SLA before comparing — per-GPU throughput swings 5–10x across the (throughput, tok/s/user) frontier on identical hardware.

### 3.1 Primary anchors

| # | Anchor | Config | Value | Unit | Source | As-of | Confidence |
|---|---|---|---|---|---|---|---|
| A1 | **DeepSeek V3/R1 production prefill** | 8xH800 nodes, EP32/EP144-style wide EP, PD disaggregation; incl. cache hits | ~9,200 (73.7k/node) | tok/s/GPU | [deepseek-ai/open-infra-index day 6](https://github.com/deepseek-ai/open-infra-index/blob/main/202502OpenSourceWeek/day_6_one_more_thing_deepseekV3R1_inference_system_overview.md) | 2025-02-28 | high — **the canonical production-economics anchor; no 2026 update exists** |
| A2 | **DeepSeek V3/R1 production decode** | same fleet | ~1,850 (14.8k/node) | tok/s/GPU | same | 2025-02-28 | high |
| A3 | DeepSeek fleet economics | avg 226.75 nodes (peak 278), $2/GPU-hr H800; 608B in (56.3% cache hit) / 168B out tokens/day | $87,072 cost / $562,027 theoretical revenue per day; 545% theoretical cost-profit margin (≈84.5% gross); implied ~$0.35–0.45/M output-equiv tokens fully loaded | USD/day | same + [KV-cache guide](https://api-docs.deepseek.com/guides/kv_cache/) | 2025-02-28 | high (actual margin far lower: V3 cheaper, web/app free, night discounts) |
| A4 | SGLang DeepSeek-R1, 96xH100 | 12 nodes (3 prefill + 9 decode), PD disagg, large-scale EP, 2000-token inputs | 6,540 prefill / 2,790 decode; **$0.20/M output tokens** at max throughput | tok/s/GPU | [lmsys.org 2025-05-05](https://www.lmsys.org/blog/2025-05-05-large-scale-ep/) | 2025-05-05 | high — open source matched DeepSeek's stack ~3 months after disclosure |
| A5 | SGLang DeepSeek, GB200 NVL72 | FP8 attention + NVFP4 MoE, 2k ISL, decode batch 1408, EP48 decode | 26,156 prefill / 13,386 decode (BF16-attn+FP8-MoE variant: 18,471 / 9,087) | tok/s/GPU | [lmsys.org 2025-09-25](https://www.lmsys.org/blog/2025-09-25-gb200-part-2/) | 2025-09-25 | high — max-throughput regime, low per-user speed |
| A6 | vLLM wide-EP DeepSeek decode | CoreWeave H200 multi-node + InfiniBand, production-like, Dual Batch Overlap | 2,200 (up from ~1.5k earlier in 2025) | tok/s/GPU | [vllm.ai 2025-12-17](https://vllm.ai/blog/2025-12-17-large-scale-serving) | 2025-12-17 | high |
| A7 | InferenceMAX DeepSeek-R1 @ 59 tok/s/user | nightly, SemiAnalysis TCO assumptions | B200 2,701 ($0.20/M) vs H200 422 ($0.93/M); at ~100 tok/s/user: 521 vs 152 | tok/s/GPU | [inferencex.semianalysis.com](https://inferencex.semianalysis.com/compare/deepseek-r1-b200-vs-h200) | 2026-07 nightly | high |
| A8 | InferenceMAX gpt-oss-120b, B200 + TRT-LLM | max batch | ~60,000 tok/s/GPU aggregate; ~$0.02/M tokens floor; a 5x $/token cut from ~2 months of software optimization alone | mixed | [developer.nvidia.com](https://developer.nvidia.com/blog/nvidia-blackwell-leads-on-new-semianalysis-inferencemax-benchmarks/) | 2025-10 | medium (vendor framing of InferenceMAX v1) |
| A9 | InferenceMAX Llama-3.3-70B (1K/1K) @ 50 tok/s/user | Blackwell | ~10,000 (>4x H200) | tok/s/GPU | [blogs.nvidia.com](https://blogs.nvidia.com/blog/blackwell-inferencemax-benchmark-results/) | 2025-10 | medium |
| A10 | GB200 NVL72 vs B200 (DeepSeek R1 FP4, TRT/Dynamo disagg) | @125 tok/s/user | up to 4.4x throughput/GPU | ratio | [inferencex.semianalysis.com](https://inferencex.semianalysis.com/blog/gb200-nvl72-vs-b200-disagg-deepseek-r1-fp4-dynamo-trt) | 2026 | medium |

### 3.2 Utilization, overhead, and architecture-level gains

| Metric | Value | Unit | Source | As-of | Confidence |
|---|---|---|---|---|---|
| Decode MFU / prefill MFU (production) | 5–15 / 30–45 | % | [zettabyte.space](https://www.zettabyte.space/blog/gpu-utilization-mfu-mbu), [databricks.com](https://www.databricks.com/blog/llm-inference-performance-engineering-best-practices) | 2025–2026 | medium |
| Well-tuned decode MBU | ~60 (**CAVEAT: 2023-era small-batch H100 figure; large-batch wide-EP MBU unpublished — open question**) | % | [databricks.com](https://www.databricks.com/blog/llm-inference-performance-engineering-best-practices) | 2023-10, still cited | medium |
| vLLM host overhead | HTTP API server ~33% of exec time (Llama-3-8B, 1xH100); scheduling ~6%; CPU orchestration up to ~50% of e2e latency multi-GPU; v0.6.0 CPU fix alone = 2.7x throughput / 5x latency | % | [arxiv 2604.07609 (Blink)](https://arxiv.org/pdf/2604.07609), [arxiv 2603.22774](https://arxiv.org/pdf/2603.22774), [arxiv 2603.12465 (TaxBreak)](https://arxiv.org/pdf/2603.12465), [vLLM postmortem](https://blog.vllm.ai/2024/09/05/perf-update.html) | 2026 | medium |
| Mooncake KV-centric disaggregation gains | up to 525% throughput (simulated long-context); +75% real Kimi capacity; 59–498% under SLOs on real traces; >100B tokens/day production | % | [arxiv 2407.00079](https://arxiv.org/abs/2407.00079) | 2024-07, deployed through 2025–26 | high |
| NVFP4/FP8 precision co-design speedup (GB200) | 1.8x attention / up to 1.9x GEMM kernels | x | [lmsys.org 2025-09-25](https://www.lmsys.org/blog/2025-09-25-gb200-part-2/) | 2025-09-25 | high |
| Engine choice, small dense models (Llama-3.1-8B BF16, H100) | SGLang/LMDeploy ~29% over tuned vLLM | % | [aimultiple.com](https://aimultiple.com/inference-engines) | 2026 | medium |
| Day-0 engine gap on new MoE (Qwen3.5-35B-A3B, SGLang vs vLLM) | 3.1–5.3x (transient, closes in weeks–months) | ratio | [vllm issue #36215](https://github.com/vllm-project/vllm/issues/36215) | 2026 | medium |

### 3.3 Simulator accuracy and pitfall constants (from prior art)

| Metric | Value | Unit | Source | As-of | Confidence |
|---|---|---|---|---|---|
| Achievable throughput/$-per-token simulator error | <5% demonstrated: KernelSight-LM 2.7–3.0% median, Frontier <4%, LLMServingSim 2.0 0.95% (self-reported); TTFT stays ~14% — pitch cost claims on throughput, not tail latency | % | [arxiv 2606.28565](https://arxiv.org/html/2606.28565v2), [arxiv 2605.21312](https://arxiv.org/html/2605.21312), [arxiv 2602.23036](https://arxiv.org/abs/2602.23036) | 2026 | high |
| Unmodeled CUDA-Graph/launch overhead | misses 32.3–46.5% (co-location) / 37.1–59.7% (disagg) of speedups | % | [Frontier, arxiv 2605.21312](https://arxiv.org/html/2605.21312) | 2026-05 | high |
| Token-count proxies vs per-request length distributions | 32.6% error (FlashAttention) / 21.0% (MoE GroupedGEMM) | % | same | 2026-05 | high |
| Analytical "total-minus-weights" KV budget | +27.2% overestimate → +32.4% throughput inflation | % | same | 2026-05 | high |
| Decode at large batch | stays memory-bound — controllers saturate below spec bandwidth; use measured achievable-bandwidth curves, not datasheets | — | [Mind the Memory Gap, arxiv 2503.08311](https://arxiv.org/pdf/2503.08311) | 2025 | high |
| Key prior-art accuracy: LLMCompass / Vidur / GenZ / NeuSight | 4.1% e2e (0.69 prefill / 7.5 decode) / <9% / 5.82% geomean / 2.3% unseen-H100 | % | [arxiv 2312.03134](https://arxiv.org/abs/2312.03134), [arxiv 2405.05465](https://arxiv.org/abs/2405.05465), [arxiv 2406.01698](https://arxiv.org/abs/2406.01698), [arxiv 2407.13853](https://arxiv.org/abs/2407.13853) | 2024–2025 | high |
| Vidur-Search economics | 1 CPU-hour replaced ~42,000 GPU-hours (~$218K) of config search | — | [arxiv 2405.05465](https://arxiv.org/abs/2405.05465) | 2024 | high |

### 3.4 Model-side lever constants (accuracy vs cost)

| Metric | Value | Unit | Source | As-of | Confidence |
|---|---|---|---|---|---|
| NVFP4 PTQ, DeepSeek-R1 MMLU | 90.8 → 90.7 (−0.1 pt vs FP8); ~2.3x throughput vs FP8 on Blackwell; ~3.5x memory vs FP16; **sub-2B results unpublished** | pts / x | [NVIDIA NVFP4 blog](https://developer.nvidia.com/blog/introducing-nvfp4-for-efficient-and-accurate-low-precision-inference/), [medium/DSC](https://medium.com/data-science-collective/nvfp4-same-accuracy-with-2-3x-higher-throughput-for-4-bit-llms-03518ecba108) | 2025, fetched 2026-07-11 | high |
| W4 PTQ degradation by scale (Qwen-2.5, no QAT) | 7B −6.8% / 32B −2.0% / 72B +0.7% avg accuracy | % | [IJCAI 2025](https://www.ijcai.org/proceedings/2025/0902.pdf) | 2025 | medium |
| QAT frontier at small scale (ParetoQ) | 2–3 bit ties/beats 4-bit at iso-(size×bits); ternary 600M beats prior ternary 3B | — | [arxiv 2502.02631](https://arxiv.org/abs/2502.02631) | 2025 | high |
| BitNet b1.58-2B-4T (native ternary) | within 1–2 pts of FP 2B peers; 0.4 GB vs ~2 GB; 2–6x CPU speed; requires training from scratch | — | [arxiv 2504.12285](https://arxiv.org/abs/2504.12285) | 2025-04 | high |
| Overtrained models quantize worse | degradation grows with training tokens; severe for fully-trained small models (law fit to 100T tokens) | — | [arxiv 2411.17691 (ACL 2025)](https://arxiv.org/abs/2411.17691) | 2025 | high |
| MLA vs GQA KV footprint | 70 vs 192–328 KB/token (2.7–4.7x) | KB/token | [arxiv 2505.09343](https://arxiv.org/html/2505.09343v1) | 2025-05 | high |
| TransMLA retrofit | −68.75% KV at −1.65% acc training-free; 93% compression mostly restored with **6B-token** fine-tune; up to 10.6x long-context speedup | % | [arxiv 2502.07864 (NeurIPS 25 Spotlight)](https://arxiv.org/abs/2502.07864) | 2025 | high |
| MHA2MLA at small scale (18.75% KV size) | SmolLM-135M/360M/1B7/Llama2-7B: −2.24 / −2.63 / −1.43 / −0.30% acc, using 0.6–1% of pretraining data | % | [arxiv 2502.14837 (ACL 2025)](https://arxiv.org/abs/2502.14837) | 2025 | high |
| KIVI 2-bit KV quant | ~−3% GSM8K, 2.35–3.47x throughput, up to 4x batch; **2025 papers (Kitty) show larger drops on hard reasoning — 4-bit KV nearly free, 2-bit task-dependent**; KVQuant ~0.1 ppl delta at 3-bit | % / x | [arxiv 2402.02750](https://arxiv.org/abs/2402.02750), [arxiv 2511.18643](https://arxiv.org/pdf/2511.18643), [KVQuant](https://arxiv.org/abs/2401.18079) | 2024–2025 | medium |
| Gemma 3 hybrid 5:1 local:global attention | KV overhead ~60% → <15% of inference memory at 32K ctx, minimal perplexity impact | % | [arxiv 2503.19786](https://arxiv.org/abs/2503.19786) | 2025-03 | high |
| Cross-Layer Attention (CLA2, 1B–3B scale) | 2x KV reduction near-equal accuracy; CLA-4 (75% reduction) ~1.2% ppl cost | x | [arxiv 2405.12981 (NeurIPS 2024)](https://arxiv.org/abs/2405.12981) | 2024 | high |
| SpQR salient-weight mixed precision | ~1% outliers FP16 + rest 3–4 bit → <1% rel. ppl loss at 3.4x compression, +20–30% gen speed | x / % | [arxiv 2306.03078](https://arxiv.org/abs/2306.03078) | 2023, ICLR 2024 | high |
| 2:4 structured sparsity | 1.24–1.27x e2e decode (~1.6x linears); 98% accuracy recovery **with** sparse recovery training (~tens of B tokens); 1.2–3.0x with INT4/Sparse-Marlin | x | [Red Hat / Neural Magic Sparse Llama](https://developers.redhat.com/articles/2025/02/28/24-sparse-llama-smaller-models-efficient-gpu-inference), [hpc-ai.com](https://company.hpc-ai.com/blog/explore-24-semi-structured-sparsity-with-1.27x-inference-speedup-on-nvidia-gpus) | 2025-02 | high |
| Minitron prune+distill economics | up to 40x fewer training tokens per derived model; 1.8x family compute saving; up to +16% MMLU vs from-scratch at equal budget | x | [arxiv 2407.14679](https://arxiv.org/abs/2407.14679) | 2024-07 | high |
| Decode arithmetic intensity at small batch | ~1–2 FLOPs/byte (weight-streaming dominated); KV overtakes weights at roughly ≥32K context or large batch | FLOPs/byte | [arxiv 2402.01528](https://arxiv.org/pdf/2402.01528), [KVQuant paper](https://www.stat.berkeley.edu/~mmahoney/pubs/neurips-2024-kvquant.pdf) | 2024 | high |
| Apple on-device palettization | ~3.7 bits/weight (4-bit k-means LUT per 16 channels), 4–6x memory reduction, shipped in production | bits | [WWDC 2024](https://developer.apple.com/videos/play/wwdc2024/10159/), [FLUTE kernels](https://arxiv.org/abs/2407.10960) | 2024–2025 | medium |

---

## 4. Market Prices

### 4.1 $/Mtok price table (fetched 2026-07-11 unless noted)

| Model | Provider | Input | Output | Notes | Source | Confidence |
|---|---|---|---|---|---|---|
| Llama 3.1 8B | DeepInfra | $0.02 | $0.03 | market floor — commoditized | [deepinfra.com/pricing](https://deepinfra.com/pricing) | high |
| Llama 3.1 8B | Novita | $0.02 | $0.05 | | [novita.ai/pricing](https://novita.ai/pricing) | high |
| Llama 3.1 8B | Groq | $0.05 | $0.08 | | [groq.com/pricing](https://groq.com/pricing) | medium (via aggregators) |
| Qwen3-30B-A3B | DeepInfra | $0.12 | $0.50 | only provider still listing it | [deepinfra.com/pricing](https://deepinfra.com/pricing) | high |
| GLM-4.5-Air | Novita | $0.13 | $0.85 | | [novita.ai/pricing](https://novita.ai/pricing) | high |
| GLM-4.6 | Novita | $0.55 | $2.20 | largely delisted at US providers | [novita.ai/pricing](https://novita.ai/pricing) | high |
| GLM-5 | Novita | $1.00 | $3.20 | | [novita.ai/pricing](https://novita.ai/pricing) | high |
| GLM-5.1 / 5.2 | Together, Nebius | $1.40 | $4.40 | | [together.ai/pricing](https://www.together.ai/pricing), [nebius.com](https://nebius.com/token-factory/prices) | medium |
| DeepSeek V3 Turbo | Novita | $0.40 | $1.30 | | [novita.ai/pricing](https://novita.ai/pricing) | high |
| DeepSeek R1 Turbo | Novita | $0.70 | $2.50 | | [novita.ai/pricing](https://novita.ai/pricing) | high |
| DeepSeek V3.1 | Baseten | $0.50 | $1.50 | | [baseten.co/pricing](https://www.baseten.co/pricing/) | medium |
| DeepSeek V4 Pro | Together, Baseten | $1.74 | $3.48 | $0.20 cached at Together | [together.ai/pricing](https://www.together.ai/pricing) | medium |
| DeepSeek V4 Pro | official API | $0.435 (miss) / **$0.003625 (cache hit)** | $0.87 | hit = ~2% of miss | [api-docs.deepseek.com](https://api-docs.deepseek.com/quick_start/pricing/) | high |
| DeepSeek V4 Flash | official API | $0.14 (miss) / $0.0028 (hit) | $0.28 | | same | high |
| Kimi K2.6 | Fireworks = Baseten = Nebius | $0.95 | $4.00 | **zero price dispersion — umbrella pricing**; $0.16 cached at Fireworks | [fireworks docs](https://docs.fireworks.ai/serverless/pricing) | high |
| Kimi K2 | Groq | $1.00 | $3.00 | cache hits 50% of input | [groq.com/pricing](https://groq.com/pricing) | medium |
| Kimi K2 Instruct | Novita | $0.57 | $2.30 | undercuts on older K2 only | [novita.ai/pricing](https://novita.ai/pricing) | high |
| Kimi K2.7 Code | Together | $0.95 | $4.00 | | [together.ai/pricing](https://www.together.ai/pricing) | medium |
| gpt-oss-120B | Groq | $0.15 | $0.60 | | [groq.com/pricing](https://groq.com/pricing) | medium |
| Llama 70B class | Cerebras | ~$0.60 flat combined | — | flat prompt+completion rate, no in/out split; reserved $0.25–0.60; range up to $2.30 (GLM-4.7) | [cerebras.ai/pricing](https://www.cerebras.ai/pricing), [deploybase.ai](https://deploybase.ai/articles/cerebras-inference-pricing) | medium |
| Llama 3.3 70B | Groq | $0.59 | $0.79 | ~parity with GPU providers — specialized silicon prices for speed, not passthrough savings | [groq.com/pricing](https://groq.com/pricing) | medium |
| Llama 3.1 405B | Hyperbolic | $4.00 | $4.00 | thin catalog | [docs.hyperbolic.xyz](https://docs.hyperbolic.xyz/docs/hyperbolic-pricing) | low |
| Qwen3-235B-A22B | cheapest (Alibaba) | $0.455 | $0.90 | ~67 tok/s median output speed | [pricepertoken.com](https://pricepertoken.com/pricing-page/model/qwen-qwen3-235b-a22b) | medium |
| Fireworks size-based fallback | Fireworks | <4B $0.10; 4–16B $0.20; >16B $0.90 | flat | Priority tier ~1.5x standard | [fireworks docs](https://docs.fireworks.ai/serverless/pricing) | high |

### 4.2 Pricing structure: batch, cache, tiers

| Metric | Value | Source | As-of | Confidence |
|---|---|---|---|---|
| Batch API discount (OpenAI, Anthropic, Google, Fireworks, Groq) | **50% off list, 24h turnaround** — universal; stacks with caching. The competitive floor for latency-insensitive tokens is batch price, not list. | [platform.claude.com pricing](https://platform.claude.com/docs/en/about-claude/pricing), [pecollective.com](https://pecollective.com/blog/llm-pricing-comparison-2026/) | 2026-07 | high |
| Anthropic prompt caching | read 0.1x base input; write 1.25x (5-min TTL) / 2x (1-hr TTL); stacks with batch → batched cache read = 0.05x list | [platform.claude.com prompt-caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) | 2026-07 | high |
| Google Gemini context caching | up to 90% off cached input | [prompthub.us](https://www.prompthub.us/blog/prompt-caching-with-openai-anthropic-and-google-models) | 2026 | high |
| DeepSeek cache-hit price | ~2% of miss price | [api-docs.deepseek.com](https://api-docs.deepseek.com/quick_start/pricing/) | 2026-07-11 | high |
| Open-model host cache-hit discount (Fireworks/Groq/Together; Baseten up to 80%) | 50% off input | [fireworks.ai/pricing](https://fireworks.ai/pricing) | 2026-07-11 | high |
| **Cache-hit pricing gap (the wedge)** | labs 2–10% of input price vs GPU-reseller hosts 50% → **5–25x structural gap** on the token class dominating agent spend | derived from rows above | 2026-07 | high |

### 4.3 Agent workload shape (canonical simulator workload)

| Metric | Value | Source | As-of | Confidence |
|---|---|---|---|---|
| Coding-agent input:output per step | ~500:1 median (126k prefix tokens in (Claude) / 116k (Codex), 252 / 184 out) | [TraceLab, arxiv 2606.30560](https://arxiv.org/html/2606.30560) | 2026-06 | high |
| Coding-agent prefix cache hit rate | 95.7% overall (97.5% tool-initiated, 84.4% user-initiated) | same | 2026-06 | high |
| Share of agent API cost: prefix reads / outputs | 59.5% / 11.2% | same | 2026-06 | high |
| Claude Code cache behavior | ~92–95% hit rate, ~13:1 read:write, ~81% cost reduction (client-side telemetry, not official) | [code.claude.com docs](https://code.claude.com/docs/en/prompt-caching), [dev.to analysis](https://dev.to/shilpamitra/how-claude-code-achieves-a-92-cache-hit-rate-a-deep-dive-into-prompt-caching-for-ai-agents-1hca) | 2026 | medium |
| Mooncake production | 70–84% KV hit on trace replay; >100B tokens/day; 92% prefill-time reduction at 128k ctx; **anonymized traces open-sourced (use to drive simulator)** | [github.com/kvcache-ai/Mooncake](https://github.com/kvcache-ai/Mooncake) | 2026-05 | high |
| DeepSeek production cache hit rate (chat-era baseline) | 56.3% (342B of 608B input tokens) | [api-docs.deepseek.com kv_cache](https://api-docs.deepseek.com/guides/kv_cache/) | 2025-02 | high |

### 4.4 Provider economics

| Metric | Value | Source | As-of | Confidence |
|---|---|---|---|---|
| Inference provider gross margins (Fireworks/Baseten/Fal) | <40% rising to >70%; Anthropic inference GM 38% → >70% | [SemiAnalysis "AI Value Capture"](https://newsletter.semianalysis.com/p/ai-value-capture-the-shift-to-model) — **paywalled, figures via snippets; verify before external use** | 2026-H1 | medium |
| Fireworks | ~$800M ARR (Sacra); $250M Series C at $4B (Oct 2025); $15B talks (May 2026) | [Bloomberg](https://www.bloomberg.com/news/articles/2026-05-27/fireworks-ai-in-talks-for-funding-at-15-billion-valuation) | 2026-05 | medium |
| Baseten | ~$600M ARR (Mar 2026); $1.5B at $13B post (Jun 2026) | [sacra.com/c/baseten](https://sacra.com/c/baseten/) | 2026-06 | medium |
| Advanced-serving baseline | PD disaggregation + wide EP already in production at OpenAI, Anthropic, xAI, Google DeepMind, DeepSeek, Together/Baseten/Fireworks | [SemiAnalysis InferenceX v2](https://newsletter.semianalysis.com/p/inferencex-v2-nvidia-blackwell-vs) | 2026 | medium |

### 4.5 Custom-silicon comparables

| Metric | Value | Source | As-of | Confidence |
|---|---|---|---|---|
| TPU v7 TCO advantage | ~44% lower all-in TCO/chip vs GB200 server; ~$15K unit (~1/3 NVIDIA capital cost — secondhand estimate) | [SemiAnalysis TPUv7](https://newsletter.semianalysis.com/p/tpuv7-google-takes-a-swing-at-the) | 2026 | medium |
| Groq post-mortem | 576 chips (230MB SRAM, GF 14nm) per Mixtral instance at batch ~3; NVIDIA ~10x perf/$ at throughput scale; exit via $20B non-exclusive NVIDIA license ($17B cash by end-2026) | [SemiAnalysis Groq teardown](https://newsletter.semianalysis.com/p/groq-inference-tokenomics-speed-but), [TechCrunch](https://techcrunch.com/2026/06/22/ai-chipmaker-groq-confirms-650m-raise-re-staffs-after-nvidias-20b-not-acqui-hire-deal/) | 2024-02 / 2026-06 | high |
| Cerebras | WSE-3 44GB on-wafer SRAM; ~2,100 tok/s/user Llama 3.3 70B (vs Groq ~750, H100 endpoints 100–150); throughput roughly batch-insensitive; IPO ~$56B on FY25 rev $510M; >$20B/750MW OpenAI deal | [spheron.network](https://www.spheron.network/blog/cerebras-vs-nvidia-h100-inference-2026/), [tech-insider.org](https://tech-insider.org/cerebras-ipo-filing-510m-revenue-openai-deal-23b-valuation-2026/), [SEC 8-K](https://www.sec.gov/Archives/edgar/data/0002021728/000162828026044941/cbrsannouncesfinancialresu.htm) | 2026-05 | medium-high |
| Etched Sohu claim | 500k tok/s Llama 70B on 8-chip server vs 25k (8xH100) / 43k (8xB200) — **vendor-only, no independent benchmark, no batch-32/256 figures, no pricing**; $800M raised, >$1B contracts; ~3yr respin for new architecture | [techtimes.com](https://www.techtimes.com/articles/319393/20260630/transformer-chip-startup-etched-exits-stealth-800m-raised-1b-contracts.htm), [spheron.network](https://www.spheron.network/blog/etched-ai-sohu-vs-nvidia-transformer-asic-inference/), [x.com/Etched](https://x.com/Etched/status/1805625693113663834) | 2026-06 | medium (claim itself: unverified) |
| Positron Atlas / Asimov | 280 tok/s/user Llama 3.1 8B in 2kW, claimed >3.5x perf/W vs NVIDIA; Asimov 2027: ~2TB LPDDR5X, ~2.76 TB/s, ~400W | [tomshardware.com](https://www.tomshardware.com/tech-industry/artificial-intelligence/positron-ai-says-its-atlas-accelerator-beats-nvidia-h200-on-inference-in-just-33-percent-of-the-power-delivers-280-tokens-per-second-per-user-with-llama-3-1-8b-in-2000w-envelope), [ipxchange.tech](https://ipxchange.tech/product-news/positron-atlas-inference-server/) | 2025–2026 | medium |
| Meta MTIA v2 memory hierarchy | 256MB SRAM + 128GB LPDDR5 @ 205 GB/s — owner co-designs for capacity/cost over bandwidth | [MTIA ISCA 2025 paper](https://aisystemcodesign.github.io/papers/MTIA-ISCA25.pdf) | 2025 | high |
