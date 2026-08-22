# Inference benchmarks

`openai_sustained.py` is a dependency-free streaming benchmark for an
OpenAI-compatible runtime. It supports cold unique prompts, controlled shared
prefixes, and replay of multi-turn coding-agent traces. It records TTFT,
output throughput, SGLang's measured prefix-cache work, and Desmond GPU metrics.

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

## Coding-agent trace replay

The primary trace workload is
[`thoughtworks/agentic-coding-trajectories`](https://huggingface.co/datasets/thoughtworks/agentic-coding-trajectories),
a public corpus assembled specifically for multi-turn serving benchmarks. The
preparer selects sessions deterministically through Hugging Face's Dataset
Viewer API and records exact source IDs in a sidecar manifest:

```sh
python3 prepare_agentic_workload.py \
  --sessions 64 \
  --output workloads/agentic-coding-64.jsonl

SGLANG_API_KEY=... python3 openai_sustained.py \
  --prompt-mode agent-trace \
  --trace-workload workloads/agentic-coding-64.jsonl \
  --concurrencies 4,8,12,16 \
  --seconds 20 \
  --output-tokens 128
```

The workload stores canonical OpenAI messages rather than rendered prompt
text. The inference server therefore applies the selected model's own chat
template—in production, Gemma 4's template. Each request replays the original
history immediately before an assistant turn, while later turns retain earlier
assistant and tool output. This reproduces the growing, cacheable prefix shape
without allowing generated text to make benchmark runs diverge.

`workload_cacheable_ratio` is computed from consecutive prompt lengths within
each immutable replay and is the workload's theoretical cache opportunity.
`server_cache_hit_ratio` comes from process-wide SGLang counters and is only
accepted when their token delta agrees with request usage; the
`server_cache_metrics_valid` field makes that check explicit.

Tool events are flattened into tagged message text for this serving benchmark
so it is portable across model templates. AutoExacto-compatible tool-call
correctness and JSON Schema adherence are separate quality gates.
