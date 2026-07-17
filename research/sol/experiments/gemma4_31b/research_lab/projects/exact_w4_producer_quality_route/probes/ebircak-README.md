---
license: apache-2.0
base_model: google/gemma-4-31B-it
library_name: compressed-tensors
tags:
  - gemma
  - gemma-4
  - quantization
  - awq
  - w4a16
  - 4bit
  - llm-compressor
  - compressed-tensors
  - vllm
  - multimodal
  - vision-language
pipeline_tag: text-generation
---

# Gemma-4-31B-it 4-bit AWQ Quantization (W4A16)

This is a **4-bit AWQ quantization** of Google's [Gemma-4-31B-it](https://huggingface.co/google/gemma-4-31B-it) instruction-tuned multimodal model, optimized for deployment with vLLM.

> **Format note**: This model was quantized using the AWQ algorithm via [llm-compressor](https://github.com/vllm-project/llm-compressor) and is saved in **compressed-tensors** format. When loading with vLLM, use `--quantization compressed-tensors` (not `--quantization awq`, which expects the AutoAWQ schema and will fail).

## Model Details

| Property | Value |
|----------|-------|
| **Base Model** | google/gemma-4-31B-it |
| **Quantization Algorithm** | AWQ (Activation-aware Weight Quantization) |
| **Weight Scheme** | W4A16_ASYM (4-bit asymmetric weights, 16-bit activations) |
| **Weight Precision** | 4-bit int4 |
| **Activation Precision** | FP16/BF16 |
| **Group Size** | 128 |
| **Serialization Format** | compressed-tensors (pack-quantized) |
| **Quantization Library** | llm-compressor (main branch, post-0.10.0.1) |
| **Architecture** | Gemma4ForConditionalGeneration |
| **Decoder Layers** | 60 |
| **Hidden Size** | 5376 |
| **Context Window** | 262K tokens (128K verified) |
| **Vision Tower** | SigLIP (27 layers, preserved in BF16 — NOT quantized) |
| **Quantized Components** | Text decoder only (vision tower + multimodal projector excluded) |

## Hardware Requirements

- **Verified context**: 128K tokens on 48GB total VRAM (2× 24GB GPUs) and 256K on 96GB single GPU
- **Minimum VRAM**: ~24GB for short contexts; ~48GB for 128K context
- **Recommended**: 48GB+ for production use with 128K+ context and FP8 KV cache

## Quantization Recipe

This model was quantized using the AWQ algorithm with the following configuration:

```yaml
AWQModifier:
  targets: [Linear]
  scheme: W4A16_ASYM
  group_size: 128
  duo_scaling: both
  ignore:
    - lm_head
    - model.vision_tower.*
    - model.multi_modal_projector.*
    - model.embed_vision.*
  mappings: <per-layer hybrid-attention mappings — see recipe.yaml>
```

**Calibration Dataset** (512 samples total, 2048 tokens each):

| Dataset | Samples | Purpose |
|---------|---------|---------|
| `ise-uiuc/Magicoder-Evol-Instruct-110K` | 256 | Coding baseline |
| `Salesforce/APIGen-MT-5k` | 128 | Tool calling / function calling |
| `nvidia/When2Call` (llm_judge split) | 128 | Tool-call decision making |

**Gemma4 hybrid-attention handling**: Gemma4-31B uses interleaved `sliding_attention` (50 layers, have `v_proj`) and `full_attention` (10 layers, `v_proj=None`) decoder layers. The quantization script generates per-layer AWQ mappings to handle this correctly — a single regex pattern would fail due to AWQ's lowest-common-ancestor grouping logic.

## Usage

### vLLM Docker (Recommended)

vLLM publishes special Docker images with Gemma4 support. Use a `gemma4`-tagged image for guaranteed compatibility with Gemma4's tool calling parser, reasoning parser, and chat template handling.

**Available Gemma4-compatible vLLM images (with transformers 5.5.0 and gemma4 parsers):**

| Image | Backend | Notes |
|-------|---------|-------|
| `vllm/vllm-openai:gemma4-cu130` | CUDA 13.0 (Blackwell sm120+) | For NVIDIA Blackwell GPUs |
| `vllm/vllm-openai-rocm:gemma4` | ROCm (RDNA3/CDNA) | For AMD GPUs |

**Example docker run (RTX Pro 6000 GPU, 1× 96GB):**

```bash
docker run -it --rm \
  --network=host \
  --gpus all \
  --ipc=host \
  --shm-size=32g \
  -v /path/to/model:/model \
  vllm/vllm-openai:gemma4-cu130 \
  /model \
    --quantization compressed-tensors \
    --dtype auto \
    --tensor-parallel-size 1 \
    --kv-cache-dtype fp8_e4m3 \
    --max-model-len 262144 \
    --max-num-batched-tokens 16384 \
    --gpu-memory-utilization 0.95 \
    --max-num-seqs 4 \
    --enable-prefix-caching \
    --enable-auto-tool-choice \
    --tool-call-parser gemma4 \
    --reasoning-parser gemma4 \
    --port 8000
```

**For ROCm (AMD GPUs), replace the image and add device flags:**

```bash
docker run -it --rm \
  --network=host \
  --device=/dev/kfd \
  --device=/dev/dri \
  --group-add=video \
  --group-add=render \
  --ipc=host \
  --shm-size=32g \
  -e HSA_OVERRIDE_GFX_VERSION=11.0.0 \
  -v /path/to/model:/model \
  vllm/vllm-openai-rocm:gemma4 \
  /model \
    --quantization compressed-tensors \
    --dtype auto \
    --tensor-parallel-size 2 \
    --kv-cache-dtype fp8_e4m3 \
    --max-model-len 131072 \
    --max-num-batched-tokens 16384 \
    --gpu-memory-utilization 0.95 \
    --max-num-seqs 4 \
    --enable-prefix-caching \
    --enable-auto-tool-choice \
    --tool-call-parser gemma4 \
    --reasoning-parser gemma4 \
    --port 8000
```

> `HSA_OVERRIDE_GFX_VERSION=11.0.0` is required for RDNA3 GPUs (RX 7900 XTX, RX 7900 XT, etc.) to enable ROCm compute support.

### Loading with vLLM (CLI)

> Use `--quantization compressed-tensors`, **not** `--quantization awq`. llm-compressor saves in compressed-tensors format regardless of the quantization algorithm. The `--quantization awq` flag expects AutoAWQ schema and will fail.

**Minimal example:**

```bash
vllm serve ebircak/gemma-4-31B-it-4bit-W4A16-AWQ \
    --quantization compressed-tensors \
    --dtype auto \
    --kv-cache-dtype fp8_e4m3 \
    --max-model-len 131072 \
    --gpu-memory-utilization 0.95
```

**With tool calling (recommended):**

```bash
vllm serve ebircak/gemma-4-31B-it-4bit-W4A16-AWQ \
    --quantization compressed-tensors \
    --dtype auto \
    --kv-cache-dtype fp8_e4m3 \
    --max-model-len 131072 \
    --gpu-memory-utilization 0.95 \
    --enable-auto-tool-choice \
    --tool-call-parser gemma4 \
    --reasoning-parser gemma4
```

**Multi-GPU (tensor parallel, 2 GPUs):**

```bash
vllm serve ebircak/gemma-4-31B-it-4bit-W4A16-AWQ \
    --quantization compressed-tensors \
    --dtype auto \
    --kv-cache-dtype fp8_e4m3 \
    --tensor-parallel-size 2 \
    --max-model-len 131072 \
    --max-num-batched-tokens 16384 \
    --max-num-seqs 4 \
    --gpu-memory-utilization 0.95 \
    --enable-prefix-caching \
    --enable-auto-tool-choice \
    --tool-call-parser gemma4 \
    --reasoning-parser gemma4
```

**Example vLLM config file:**

```yaml
# vllm_config.yaml
model: ebircak/gemma-4-31B-it-4bit-W4A16-AWQ
quantization: compressed-tensors   # AWQ weights in compressed-tensors format
kv_cache_dtype: fp8_e4m3           # FP8 KV cache (applied at runtime by vLLM)
dtype: auto
gpu_memory_utilization: 0.95
max_model_len: 131072              # 128K context (verified)
tensor_parallel_size: 2            # Adjust to your GPU count
enable_prefix_caching: true

# Gemma4-specific (required for tool calling)
enable_auto_tool_choice: true
tool_call_parser: gemma4
reasoning_parser: gemma4

# Suppress thinking mode server-wide (clients can override per-request)
default_chat_template_kwargs:
  enable_thinking: false
```

### Loading with Transformers

```python
from transformers import AutoModelForMultimodalLM, AutoTokenizer

model_id = "ebircak/gemma-4-31B-it-4bit-W4A16-AWQ"

tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForMultimodalLM.from_pretrained(
    model_id,
    device_map="auto",
    torch_dtype="auto"
)
```

## Tool Calling

This model uses the **Google Gemma4 chat template** (baked into `tokenizer_config.json`), which is required for vLLM's `gemma4` tool call parser. The native Gemma4 tool call format uses special tokens:

```
<|tool_call>call:function_name{key:<|"|>value<|"|>}<tool_call|>
```

vLLM's `gemma4` tool_call_parser converts this to standard OpenAI `tool_calls` JSON automatically.

## Files in This Repository

| File | Description |
|------|-------------|
| `model.safetensors` | Quantized model weights (~17.9 GB) |
| `config.json` | Model configuration with quantization_config |
| `tokenizer.json` | Tokenizer vocabulary |
| `tokenizer_config.json` | Tokenizer config with baked Gemma4 chat template |
| `chat_template.jinja` | Gemma4 native chat template |
| `generation_config.json` | Generation parameters |
| `processor_config.json` | Processor configuration |
| `recipe.yaml` | Full AWQ quantization recipe (per-layer mappings) |
| `LICENSE` | Apache 2.0 License |

## License

This quantization is released under the **Apache 2.0 License**.

The base model [google/gemma-4-31B-it](https://huggingface.co/google/gemma-4-31B-it) is also licensed under Apache 2.0.

See [`LICENSE`](LICENSE) for the full text.

## Citation

If you use this model in your research, please cite:

```bibtex
@misc{gemma4-31b-awq-quantization,
  title = {Gemma-4-31B-it 4-bit AWQ Quantization},
  author = {ebircak},
  year = {2026},
  howpublished = {\url{https://huggingface.co/ebircak/gemma-4-31B-it-4bit-W4A16-AWQ}},
  note = {Quantized with llm-compressor (main branch) using AWQ W4A16\_ASYM}
}
```

## Disclaimer

This is a community quantization of the Google Gemma-4-31B-it model. While efforts have been made to ensure quality, this model is provided "as is" without warranty of any kind. Users should evaluate the model for their specific use cases.

This quantization would not be possible without the hardware support of Gratex International, a.s. (https://www.gratex.com).

## Model Card Version

This model card follows the [Model Cards for Model Reporting](https://arxiv.org/abs/1810.03993) standard.

---

**Original Model**: [google/gemma-4-31B-it](https://huggingface.co/google/gemma-4-31B-it)  
**Quantization Tool**: [llm-compressor](https://github.com/vllm-project/llm-compressor)  
**Quantization Format**: [compressed-tensors](https://github.com/neuralmagic/compressed-tensors)  
