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

## Speculative-decoder evaluation

Split sessions, rather than individual turns, so growing prefixes cannot leak
between training and evaluation:

```sh
python3 split_agentic_workload.py \
  --input workloads/agentic-coding-192.jsonl \
  --output-dir workloads/speculative-splits
```

`speculative_eval.py` replays each session's final turns sequentially while
running sessions in parallel. Capture a target-only baseline, then compare each
speculative candidate against it. Greedy output must match exactly before a
candidate's latency or throughput result is accepted:

```sh
SGLANG_API_KEY=... python3 speculative_eval.py \
  --workload workloads/speculative-splits/holdout.jsonl \
  --output results/speculative-baseline.json

SGLANG_API_KEY=... python3 speculative_eval.py \
  --workload workloads/speculative-splits/holdout.jsonl \
  --baseline results/speculative-baseline.json \
  --output results/speculative-candidate.json
```

## Native precision quality gates

`gradiated-engine-fp8-quality-eval` can write the BF16 and candidate token
streams for completion-level checks. Use the same batch geometry for the BF16
reference and candidate so the comparison does not mistake batching-sensitive
activation scales for a precision regression:

```sh
GRADIATED_QUALITY_FREE_RUNNING=1 \
GRADIATED_QUALITY_EVALUATED_TOKENS=512 \
GRADIATED_QUALITY_REFERENCE_BATCH=16 \
GRADIATED_QUALITY_BATCH=16 \
GRADIATED_QUALITY_OUTPUT_JSONL=/tmp/quality.jsonl \
gradiated-engine-fp8-quality-eval MODEL PROMPTS.json tensor
```

`analyze_agentic_quality.py` checks EOS behavior, token-edit similarity, code
fence structure, and Bash/Python/JSON syntax. `prepare_humaneval_prompts.py`
creates disjoint partitions of the official HumanEval test set, and
`analyze_humaneval.py` executes both BF16 and candidate completions. Because
the latter executes generated code, run it only inside the networkless,
read-only, resource-limited container used by the deployment quality job; the
script intentionally treats that outer sandbox as part of its security model.

The retained tensor-scaled E4M3 policy uses weight multiplier `1.0`. Its
independent 64-task HumanEval holdout matched BF16 at 61/64 pass@1 with zero
BF16-pass-to-FP8-fail regressions. Scale clipping, per-channel/block scaling,
mixed BF16 islands, and MSE-selected weight scales remain rejected research
variants rather than production defaults.
