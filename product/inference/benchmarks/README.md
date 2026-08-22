# Inference benchmarks

`openai_sustained.py` is a dependency-free streaming benchmark for an
OpenAI-compatible runtime. It varies the first prompt token to avoid measuring
a fully cached prompt, records TTFT and output throughput from SSE responses,
and samples Desmond's GPU metrics throughout each level.

Run it from a client with private access to the inference and Desmond ports:

```sh
SGLANG_API_KEY=... python3 openai_sustained.py \
  --concurrencies 1,2,4,8,12,16,24 \
  --seconds 20 \
  --prompt-repetitions 25 \
  --output-tokens 128
```

The benchmark sends directly to the runtime. Gateway admission, billing, and
HTTP overhead should be measured separately before using the result as an
external API SLO.

