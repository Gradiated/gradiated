# Livetune: live SGLang settings that follow traffic

Livetune changes a running SGLang server's settings in response to the traffic it serves, without restarting it. It has three parts:

| Part                     | Runs                                  | Job                                                                                                                              |
| ------------------------ | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `livetune.sglang_plugin` | inside every SGLang scheduler process | Adds live settings to SGLang's `/set_internal_state` and installs startup forward-pass variants.                                 |
| `livetune control`       | next to the server                    | Reads `/metrics` every few seconds, maps the traffic shape to a policy rule, applies it, and rolls it back if it breaks the SLO. |
| `livetune tune`          | against a test server                 | Measures settings under each traffic profile and writes the policy.                                                              |
| `livetune advise`        | next to the server                    | Watches utilization, the traffic mix and batch counters, and proposes experiments.                                               |

[Adaptive serving](../../../docs/LIVETUNE_ADAPTIVE_SERVING.md) describes the whole loop: the data collected, the three tiers of levers and how each tier is rolled out. The tuner applies the persistent-engine idea from Together Compiler to settings. Each candidate is applied live, so a trial costs one measurement window instead of an engine restart.

## Live settings

The plugin registers through SGLang's plugin entry point (`sglang.srt.plugins`), so SGLang loads it in every scheduler process with no source patch. A request to `/set_internal_state` is validated on every tensor-parallel rank before any rank applies it. Every rank applies it at the same point of its scheduling loop, so the ranks cannot diverge.

| Setting                     | Effect                                                                                                                                          | Bound                                          |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| `max_running_requests`      | Running-batch cap: trades time to first token against per-user decode speed                                                                     | 1 to the startup value                         |
| `chunked_prefill_size`      | Prefill chunk size: smaller chunks stall decoding users less                                                                                    | page-aligned, up to the startup value          |
| `max_prefill_tokens`        | Prefill token budget per step                                                                                                                   | page-aligned, up to the startup value          |
| `schedule_policy`           | Waiting-queue order, as an index: 0 `fcfs`, 1 `lpm`, 2 `dfs-weight`, 3 `lof`, 4 `random`, 5 `hrrn`, 6 `shortest-prefill-first`, 7 `routing-key` | a policy the scheduler can build               |
| `schedule_conservativeness` | Decode headroom reserved when admitting prefill; lower admits more and risks retraction                                                         | 0.1 to 2.0                                     |
| `stream_interval`           | Tokens per streamed chunk                                                                                                                       | 1 to 64                                        |
| `max_queued_requests`       | Waiting-queue limit; arrivals beyond it are rejected; 0 is unlimited                                                                            | 0 to 1,000,000                                 |
| `min_evict_tokens`          | Minimum tokens freed per prefix-cache eviction; 0 is stock                                                                                      | up to a quarter of the KV cache                |
| `forward_variant`           | Reports the installed forward-pass variant; see below for how it changes                                                                        | ids in the pinned variant manifest; 0 is stock |

Buffers and CUDA graphs are sized at startup, so a setting can only move inside the envelope the server started with. Start the server at the most permissive values the policy may use.

```bash
curl -s -X POST localhost:30000/set_internal_state -d '{"server_args": {"max_running_requests": 16}}'
python -m livetune status --url http://127.0.0.1:30000   # live settings, startup bounds, recent changes
```

A forward variant is a module with `install(model, patch, ctx)`. Every change goes through `patch(obj, name, value)`, so it can be undone. Variants are selected by id, because SGLang's update endpoint carries numbers only. `LIVETUNE_VARIANTS_DIR/manifest.json` maps each id to a `<name>.py` file with a pinned sha256, and no code is ever sent over the wire. `livetune.variants.register` adds files on a host.

In production, a variant is chosen at startup with `LIVETUNE_STARTUP_VARIANT=<id>`. It is installed before SGLang captures its CUDA graphs, and it changes through a rolling restart. Live switching (`LIVETUNE_LIVE_VARIANTS=1`) is off by default because recapturing decode graphs at runtime is not safe on the pinned SGLang build:

- **In-flight batches.** Recapturing while a batch is still in flight under the overlap scheduler corrupted that batch. The plugin therefore defers a switch until the scheduler is idle and pauses admission meanwhile; if the scheduler doesn't drain within `LIVETUNE_DRAIN_STEPS`, the switch is cancelled.
- **Broken graphs.** Even a switch made while idle produced decode graphs that hit an illegal memory access on DeepSeek V4.1 Flash. SGLang's own recapture paths first drop attention-backend graph state, and a plain `init_decode_cuda_graph()` re-call does not.
- **Agreement.** Ranks all-reduce the success of install plus graph recapture, so either all of them switch or none does. A failed switch restores the variant that was serving, or stock if that fails too. If neither comes back, the scheduler stops rather than serve without working graphs. Data-parallel servers refuse live switching, because their schedulers drain independently.

Keep live switching off until a recapture path is qualified for the model's attention backend. A recapture also pauses decoding for about 27 s on DeepSeek V4.1 Flash with 12 graph sizes.

## Traffic data

Set `LIVETUNE_TRACE_DIR` and the plugin writes one JSON line per finished request on attention-TP rank 0. Each line holds prompt, cached and output tokens, queue time, scheduler TTFT and decode time, finish reason, retractions, spec accept length, sampling features, and keyed hashes of the prompt prefix at 256, 2,048 and 16,384 tokens and at the cached length. It holds no text and no token ids. Prefix hashes are keyed by `LIVETUNE_TRACE_KEY` (hex), or by a random per-process key. Files rotate at 64 MB, and the 8 newest are kept. The plugin also counts batches, requests, tokens, CUDA-graph batches and seconds for each forward mode, and reports them under `telemetry` in `/server_info`.

```bash
python -m livetune traffic --trace-dir /var/lib/livetune/trace          # the traffic mix
python -m livetune advise --url URL --trace-dir DIR --seconds 300 --out advice.json
python -m livetune tune --url URL --trace DIR --grid advice.json --slo-tps 80 --slo-ttft 10 --corpus corpus.json --out policy.json
python -m livetune replay --url URL --trace DIR --policy policy.json --corpus corpus.json
```

`livetune improve` closes the loop. Every `--every` seconds it:

1. advises from the production server;
2. replays the last `--window` seconds of recorded production traffic on a canary with the same scope, measuring each live proposal;
3. publishes a policy to `--policy-out` when a candidate beat the startup settings.

`control` reloads its policy file when the file changes, and ignores a file that fails the scope check. Tuning never adds load to production, and production only changes through a measured policy.

`advise` proposes live levers with values to try, restart levers (launch flags for a canary) and code levers, giving the hot shapes for a forward variant. Each proposal carries the measurements behind it. Its `grid` is a valid `tune --grid`. `--trace` replays recorded requests open loop at their recorded times, keeping each prefix family's shared prefix, so every candidate meets the same traffic.

## Policies

A policy is an SLO plus an ordered list of rules. Each rule is a box in (demand, prompt length) space with the settings to use inside it. Demand is the number of running plus queued requests. The first box that contains the current shape wins, and the last rule is a catch-all. `livetune tune` gives each measured profile a box that reaches at most 1.25× above and below its user count and prompt length, meeting a neighbour halfway where their reaches overlap. Everywhere else, including gaps between sparse profiles, the startup settings apply. A tuned rule also applies only near its profile's cache hit (within 0.2 of its shared-prefix fraction) and output length (within 2×). Live traffic outside those ranges falls through to startup settings, because rules do not select on those dimensions.

```json
{
  "slo": { "min_tps_per_user": 80, "max_ttft_p90_s": 4 },
  "rules": [
    {
      "name": "chat-light",
      "max_demand": 6,
      "max_prompt_tokens": 12000,
      "settings": { "max_running_requests": 8 }
    },
    "..."
  ]
}
```

Each policy records the scope it was tuned on. That is every SGLang launch argument that can change serving performance (model, parallel layout, KV dtype, speculative decoding, backends and so on). It also covers the model path and weight version serving now, from `/model_info`, so results do not cross checkpoints loaded in place, KV-cache capacity, within 5% because it is derived from free memory, the GPU product the scheduler reports, its page size and startup settings, including the startup variant, and the selectable forward variants, each hash verified against its file, whether live variant switching is enabled, and SHA-256 digests of the installed SGLang and livetune Python sources, overlays included, and of every installed distribution's version and RECORD, whose per-file hashes cover native libraries such as Torch, FlashInfer and the CUDA wheels. Files and directories the deployment names in `LIVETUNE_RUNTIME_INPUTS` are hashed too. The GLM bundle names its FlashInfer artifact manifest, patch manifest, model config and its FlashInfer autotune cache after seeding. A host keeps tactics it tuned itself, so the cache, not the seed, is what runs. A rebuilt runtime is a new scope. A variant id is pinned to the first hash its scheduler sees; re-registering the name with new code takes a restart. Addresses, ports, ranks, paths, logging, secrets, the random seed and the knobs livetune moves are left out, so replicas of one deployment match. `control` and `replay` refuse a policy whose scope differs from the live server unless given `--allow-scope-mismatch`. `livetune tune` writes policies from measurements. Each rule records the measured throughput, per-user speed and time to first token behind it. A setting a rule omits takes its startup value. Rules select on prompt length and demand only, so `tune` refuses two profiles with the same prompt length and user count.

## Controller safety

- **Hysteresis:** a new rule must win `dwell` consecutive windows (default 2 × 5 s), and changes are at least `cooldown_s` apart (default 20 s).
- **Box edges:** the current rule is kept while the observed shape is within ±15% of its box, so a shape sitting on a boundary does not flap. Without this, a cap flapped between 24 and 64 and cut throughput by 40% in a traffic-shift test. An earlier version also demanded that the new rule hold over ±15%. With tuned boxes narrower than that, no rule ever qualified, and a 40-user burst stayed on a 16-user rule for its whole phase.
- **Demand estimate:** closed-loop clients finish in waves, so the running-plus-queued gauge read at a scrape instant swings between near zero and the full load. The controller takes a new peak at once and decays the estimate by 0.8 per window. Smoothing alone let the shape wander across boxes, and the controller stayed on a light-chat rule through a 56-user overload.
- **Failed variant switches:** after a failed apply the controller re-applies the rule's other settings at once. A variant change made within the variant cooldown is retried only after the cooldown ends.
- **Probation and rollback:** after a change the rule is on probation for 45 s, and no other change is made until it is judged. In observe mode nothing is applied, so nothing is judged. If the SLO held before the change and fails in most probation windows, the controller restores the previous rule and penalises the failed one for 10 minutes.
- **Per-user speed:** live windows read SGLang's per-request decode-time histogram, one sample per finished request, which is the rate `tune` measures. Token-level inter-token latency weights long, fast streams by their token counts, so it can pass the SLO while most requests miss it.
- **Histogram resolution:** that histogram uses `--bucket-inter-token-latency`. The default buckets jump from 0.010 s to 0.015 s, which straddles an 80 tok/s SLO (0.0125 s). In one replay, live windows interpolated about 86 tok/s per user while the client measured 77, so a rule that missed the SLO passed probation. Launch servers with bucket edges at about 5% steps around the SLO, for example `--bucket-inter-token-latency 0.005 0.008 0.01 0.011 0.012 0.0125 0.013 0.014 0.015 0.02 0.04 0.1 1`.
- **Readback:** every change is checked against `/server_info`. If an update fails, the controller forgets what it believes the server runs and re-applies a full rule at the next window.
- **Reconciliation:** every window re-asserts the current rule's full settings, and only values that differ from the live state are sent. A restarted server, which comes back on its startup settings, is back on the rule within one window.

## Commands

```bash
python -m livetune load    --url URL --phases phases.json --corpus corpus.json
python -m livetune tune    --url URL --profiles profiles.json --grid grid.json \
                           --slo-tps 80 --slo-ttft 4 --corpus corpus.json --out policy.json
python -m livetune policy  --url URL --trials policy.json.trials.jsonl --slo-tps 80 --slo-ttft 10 --out policy.json
python -m livetune control --url URL --policy policy.json --log events.jsonl [--mode observe]
python -m livetune replay  --url URL --phases shift.json --corpus corpus.json --policy policy.json [--static]
```

A replay phase in which an apply was rejected is reported with `valid: false`, because its traffic ran on settings the controller did not choose.

`tune` records every trial, so `policy` can rebuild a policy for a different SLO without measuring again. One 30-second window can flatter a setting, so any winner other than the startup setting is re-measured in two interleaved rounds against startup, and the choice uses medians. `policy` likewise needs two measurements of a non-startup setting before it will choose it. A running cap at or above a profile's user count cannot bind in a closed-loop test, so the tuner never tries such caps and policies keep the startup value there. `control --mode observe` logs the decisions without applying them, which is the first step on a production host. `replay` plays a traffic schedule with the controller running, or with `--static` settings, and reports each phase against the SLO with the rules that were active and how soon the first change came.

`corpus.json` is a list of token ids, or a workload file holding `{"prompts": [[...]]}`. Load phases are closed-loop: each user sends its next request when the previous one finishes.

## Tests

```bash
python3 -m unittest discover -s product/inference/livetune/tests -p 'test_*.py'
```

The tests cover:

- settings validation, and variant pinning, undo and drained switching
- metrics windows, including real SGLang scrapes in `tests/fixtures`
- policy selection, controller hysteresis, edge margins and rollback
- the tuner's search and confirmation
- the plugin against a fake scheduler

Live behaviour was checked against DeepSeek V4.1 Flash on the production SGLang build; see the pull request for the measurements.
