# Paired open-loop inference benchmark

Fixed concurrency is useful for kernel saturation, but it is a closed-loop workload: a slow
response delays the client's next request and suppresses the queue that users would experience.
The open-loop harness schedules requests independently of completions and records client dispatch
lag so an overloaded load generator cannot create coordinated omission.

Generate the arrival manifest once and reuse the exact file for every runtime variant. A shared
random seed alone is insufficient because a small control-flow change can consume random numbers
in a different order.

```sh
python3 generate_open_loop_manifest.py \
  --workload native-agent-prompts-64.json \
  --arrival-model poisson \
  --offered-rps 4 \
  --conversations 16 \
  --warmup-conversations 4 \
  --turns 10 \
  --suffix-tokens 64 \
  --output-tokens 64 \
  --output workloads/agentic-poisson-rps4.json

python3 native_open_loop.py \
  --manifest workloads/agentic-poisson-rps4.json \
  --output results/baseline-rps4.json
```

The manifest contains absolute offsets, complete tokenized inputs, output limits, prefix lineage,
and a counter-style seed for every request. Conversation turns are immutable slices of the source
trace, so variants execute the same work even if their generated outputs differ. Turns are ordered
round-robin across conversations; choose enough conversations that a session's prior request has
finished before its continuation arrives.

Use `--arrival-model mmpp` to add correlated high-rate periods while preserving the requested mean
arrival rate. Production qualification should include both models and sweep offered load below and
above the queueing knee. A practical sweep is 25%, 50%, 70%, 85%, 95%, and 105% of the previously
measured sustainable request rate.

For coding agents, `--arrival-model session-poisson` is the primary economic workload. New
conversation starts are Poisson, while later turns use log-normal think times and therefore arrive
as correlated continuation traffic. Some sessions begin during the warmup horizon and cross the
measurement boundary, avoiding an unrealistic wave where every measured request is cold at once.
The requested rate is the long-run request rate (`session start rate × turns`); inspect the realized
rate because a finite trace has startup and tail effects.

Use `--arrival-model session-live` for the production-capacity score. Session starts are still a
Poisson process and therefore cannot be delayed by a slow server, but each conversation's next
turn waits for its previous response and a seeded log-normal think time. The next input is the
previous input plus the model's actual output and a traced user/tool suffix, matching how the
resident KV prefix evolves in a real agent conversation. This prevents overload from creating
impossible overlapping turns or impossible prompts that omit the model response. Reusing the
manifest keeps session starts, traced suffixes, think times, and sampling seeds identical;
continuation times and tokens can legitimately differ if a runtime changes latency or output.
Retain `session-poisson` as the fixed-work stress test and `poisson`/`mmpp` as request-level
overload tests.

Compare runs only when their manifest hashes match:

```sh
python3 compare_open_loop.py results/baseline-rps4.json results/candidate-rps4.json
```

The comparator reports paired latency deltas with a bootstrap confidence interval and exact output
agreement. Aggregate throughput is still a trace-level measurement rather than a per-request pair.
Alternate run order (`A-B-B-A`) and repeat with several manifests to control for clock, temperature,
and acceptance variation.

The primary production score is SLO-qualified goodput: output tokens completed while TTFT, TPOT,
request latency, errors, and the independent model-quality gate all pass. Always retain raw
throughput, queue latency, prefix-cache tokens, speculative acceptance, GPU power, and profiling
events so a faster result cannot hide overload or a quality regression.

For a long `session-live` run, `steady_window` scores completions after the configurable
`--steady-start-seconds` ramp and before the last scheduled session birth. It charges the full
window duration and excludes the artificial final drain. Keep the full-trace score beside it:
the steady window estimates sustained economics, while the full trace exposes startup and tail
debt that a short observation could hide.

`native_open_loop.py` computes revenue from the runtime's actual cached-input, uncached-input, and
output-token counters. Its default prices are the measured cheapest OpenRouter Gemma 4 prices
($0.01/M cached input, $0.08/M uncached input, and $0.35/M output) and the Nebius H200 cost is
$4.50/hour. Pass marketplace and ancillary costs explicitly when they apply. The economic
promotion metric is `slo_compute_recovery`, not the unconstrained recovery number.

After running each offered-load point, locate the highest-margin point that still satisfies the
SLO ratio and load-generator dispatch bound:

```sh
python3 summarize_open_loop_sweep.py results/variant-rps*.json
```
