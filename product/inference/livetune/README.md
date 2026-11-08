# Livetune: live SGLang settings that follow traffic

Livetune changes a running SGLang server's settings in response to the traffic it serves, without restarting it. It has three parts:

| Part                     | Runs                                  | Job                                                                                                                              |
| ------------------------ | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `livetune.sglang_plugin` | inside every SGLang scheduler process | Adds live settings to SGLang's `/set_internal_state` and installs startup forward-pass variants.                                 |
| `livetune control`       | next to the server                    | Reads `/metrics` every few seconds, maps the traffic shape to a policy rule, applies it, and rolls it back if it breaks the SLO. |
| `livetune tune`          | against a test server                 | Measures settings under each traffic profile and writes the policy.                                                              |

The tuner applies the persistent-engine idea from Together Compiler to settings. Each candidate is applied live, so a trial costs one measurement window instead of an engine restart.

## Live settings

The plugin registers through SGLang's plugin entry point (`sglang.srt.plugins`), so SGLang loads it in every scheduler process with no source patch. A request to `/set_internal_state` is validated on every tensor-parallel rank before any rank applies it. Every rank applies it at the same point of its scheduling loop, so the ranks cannot diverge.

| Setting                | Effect                                                                      | Bound                                          |
| ---------------------- | --------------------------------------------------------------------------- | ---------------------------------------------- |
| `max_running_requests` | Running-batch cap: trades time to first token against per-user decode speed | 1 to the startup value                         |
| `chunked_prefill_size` | Prefill chunk size: smaller chunks stall decoding users less                | page-aligned, up to the startup value          |
| `max_prefill_tokens`   | Prefill token budget per step                                               | page-aligned, up to the startup value          |
| `forward_variant`      | Reports the installed forward-pass variant; see below for how it changes    | ids in the pinned variant manifest; 0 is stock |

Buffers and CUDA graphs are sized at startup, so a setting can only move inside the envelope the server started with. Start the server at the most permissive values the policy may use.

```bash
curl -s -X POST localhost:30000/set_internal_state -d '{"server_args": {"max_running_requests": 16}}'
python -m livetune status --url http://127.0.0.1:30000   # live settings, startup bounds, recent changes
```

A forward variant is a module with `install(model, patch, ctx)`. Every change goes through `patch(obj, name, value)`, so it can be undone. Variants are selected by id, because SGLang's update endpoint carries numbers only. `LIVETUNE_VARIANTS_DIR/manifest.json` maps each id to a `<name>.py` file with a pinned sha256, and no code is ever sent over the wire. `livetune.variants.register` adds files on a host.

In production, a variant is chosen at startup with `LIVETUNE_STARTUP_VARIANT=<id>`. It is installed before SGLang captures its CUDA graphs, and it changes through a rolling restart. Live switching (`LIVETUNE_LIVE_VARIANTS=1`) is off by default because recapturing decode graphs at runtime is not safe on the pinned SGLang build:

- **In-flight batches.** Recapturing while a batch is still in flight under the overlap scheduler corrupted that batch. The plugin therefore defers a switch until the scheduler is idle and pauses admission meanwhile; if the scheduler doesn't drain within `LIVETUNE_DRAIN_STEPS`, the switch is cancelled.
- **Broken graphs.** Even a switch made while idle produced decode graphs that hit an illegal memory access on DeepSeek V4.1 Flash. SGLang's own recapture paths first drop attention-backend graph state, and a plain `init_decode_cuda_graph()` re-call does not.
- **Agreement.** Ranks all-reduce install success, so either all of them switch or none does.

Keep live switching off until a recapture path is qualified for the model's attention backend. A recapture also pauses decoding for about 27 s on DeepSeek V4.1 Flash with 12 graph sizes.

## Policies

A policy is an SLO plus an ordered list of rules. Each rule is a box in (demand, prompt length) space with the settings to use inside it. Demand is the number of running plus queued requests. The first box that contains the current shape wins, and the last rule is a catch-all.

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

`livetune tune` writes policies from measurements. Each rule records the measured throughput, per-user speed and time to first token behind it.

## Controller safety

- **Hysteresis:** a new rule must win `dwell` consecutive windows (default 2 × 5 s), and changes are at least `cooldown_s` apart (default 20 s).
- **Box edges:** a new rule must still be selected when the observed shape is ±15% larger or smaller, so a shape sitting on a boundary keeps the current rule. Without this, a cap flapped between 24 and 64 and cut throughput by 40% in a traffic-shift test.
- **Demand estimate:** closed-loop clients finish in waves, so the running-plus-queued gauge read at a scrape instant swings between near zero and the full load. The controller takes a new peak at once and decays the estimate by 0.8 per window. Smoothing alone let the shape wander across boxes, and the controller stayed on a light-chat rule through a 56-user overload.
- **Probation and rollback:** after a change the rule is on probation. If the SLO held before the change and fails in most probation windows, the controller restores the previous rule and penalises the failed one for 10 minutes.
- **Readback:** every change is checked against `/server_info`. If an update fails, the controller forgets what it believes the server runs and re-applies a full rule at the next window.

## Commands

```bash
python -m livetune load    --url URL --phases phases.json --corpus corpus.json
python -m livetune tune    --url URL --profiles profiles.json --grid grid.json \
                           --slo-tps 80 --slo-ttft 4 --corpus corpus.json --out policy.json
python -m livetune policy  --url URL --trials policy.json.trials.jsonl --slo-tps 80 --slo-ttft 10 --out policy.json
python -m livetune control --url URL --policy policy.json --log events.jsonl [--mode observe]
python -m livetune replay  --url URL --phases shift.json --corpus corpus.json --policy policy.json [--static]
```

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
