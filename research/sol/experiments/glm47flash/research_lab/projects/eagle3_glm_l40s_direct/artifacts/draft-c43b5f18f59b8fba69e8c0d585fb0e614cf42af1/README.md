---
license: apache-2.0
library_name: transformers
pipeline_tag: text-generation
tags:
- speculative-decoding
- eagle3
- glm
- draft-model
---

# EAGLE3 Draft Model for GLM-4.7-Flash

An [EAGLE3](https://arxiv.org/abs/2503.01840) draft model that accelerates inference for [zai-org/GLM-4.7-Flash](https://huggingface.co/zai-org/GLM-4.7-Flash) (30B MoE, ~3B active) through speculative decoding.

**1.66x mean speedup at B=1** across 4 benchmarks on a single H200.

---

## Results

Verified 2026-04-12 on 1x NVIDIA H200 144GB, TP=1, FlashInfer, temp=0, max_tokens=512.

### B=1 (single request)

| Dataset | Baseline tok/s | Eagle3 tok/s | Speedup | Accept Rate | Accept Length |
|---------|---------------|-------------|---------|-------------|---------------|
| HumanEval (75) | 130.2 | 231.8 | **1.78x** | 57.1% | 3.42 |
| Terminal-Bench (112) | 128.0 | 220.2 | **1.72x** | 62.9% | 3.77 |
| MT-Bench (154) | 129.2 | 207.1 | **1.60x** | 47.9% | 2.88 |
| SWEBench-Verified (75) | 127.4 | 194.4 | **1.53x** | 51.7% | 3.10 |
| **Mean** | **128.7** | **213.4** | **1.66x** | **54.9%** | **3.29** |

### B=32 (32 concurrent requests)

| Dataset | Baseline tok/s | Eagle3 tok/s | Speedup |
|---------|---------------|-------------|---------|
| SWEBench-Verified | 1,415.3 | 1,830.4 | **1.29x** |
| HumanEval | 1,595.8 | 1,851.5 | **1.16x** |
| MT-Bench | 1,489.9 | 1,627.9 | **1.09x** |
| Terminal-Bench | 1,479.4 | 1,614.0 | **1.09x** |
| **Mean** | **1,495.1** | **1,731.0** | **1.16x** |

**Protocol**: B=1: 5 warmup + 20 measured (sequential). B=32: 15 warmup + 60 measured (32 concurrent). Metrics from server-side Prometheus.

---

## Architecture

| Parameter | Value |
|-----------|-------|
| Type | LlamaForCausalLMEagle3 |
| Hidden Size | 2048 |
| Heads / KV Heads | 16 / 4 (GQA) |
| Head Dimension | 128 |
| Intermediate Size | 8192 |
| Layers | 1 |
| Vocab Size | 154,880 (draft: 32,000) |
| Size | 278 MB |

---

## Training

54K samples (45% ShareGPT, 35% UltraChat, 20% PerfectBlend). 3 epochs, LR=1e-4, max_length=1024, batch_size=1. Trained with `--target-model-backend sglang` via [SpecForge](https://github.com/sgl-project/SpecForge).

Best training accuracy (`acc_0`): 79.2%. Note: training accuracy does not predict inference accept rate — there is a 30-60pp gap.

---

## Usage

Benchmarked with our SGLang fork ([tails-mpt/sglang](https://github.com/tails-mpt/sglang), commit `63291f7f51`). Upstream SGLang may produce different speedups due to scheduling overhead differences.

```bash
python -m sglang.launch_server \
  --model-path zai-org/GLM-4.7-Flash \
  --speculative-algorithm EAGLE3 \
  --speculative-draft-model-path thoughtworks/GLM-4.7-Flash-Eagle3 \
  --speculative-num-steps 3 \
  --speculative-num-draft-tokens 6 \
  --speculative-eagle-topk 4 \
  --tp 1 --trust-remote-code --port 30000 \
  --enable-metrics --mem-fraction-static 0.65
```

**Pinned dependencies**: sgl-kernel 0.3.18.post2, flashinfer 0.6.6, torch 2.9.1+cu126.

Verify accept rate > 0% after startup to confirm the draft model loaded correctly.

---

## Citation

```bibtex
@article{li2025eagle3,
  title={EAGLE-3: Scaling up Inference Acceleration of Large Language Models via Training-Time Test},
  author={Li, Yuhui and Wei, Fangyun and Zhang, Chao and others},
  journal={arXiv preprint arXiv:2503.01840},
  year={2025}
}
```
