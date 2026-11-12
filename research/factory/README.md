# Simple research lab

The research lab is three Codex roles plus a small scheduler:

```text
Sol research director
  -> creates and updates independent projects
  -> parallel researchers run experiments and write project logs
  -> the next director turn reads those results and updates the portfolio

Periodic research supervisor
  -> reads agent traces, project logs, timings, and GPU outcomes
  -> improves the skills, shared tools, or scheduler when useful
```

The roles use `$research-director`, `$researcher`, and `$research-supervisor`. They are intentionally judgment-based. The scheduler does not rank hypotheses, impose experiment workflows, or decide when a line should be abandoned.

Projects default to the fast execution researcher pool. A director may set `researcher_profile: deep` in `STATUS.json` when the next result requires mechanism-level source, model, and accelerator reasoning; the harness routes that project to the configured Sol-high `deep_researcher`. Switching back to `execution` returns implementation and sweeps to the fast pool. The profile changes model allocation only and adds no experiment gate.

## What the harness does

`grad_research.lab_harness` uses the installed `codex` CLI and saved ChatGPT/Codex login. It explicitly removes API-key environment variables from child Codex processes. It:

- runs one serialized Sol director turn at startup and after each material
  researcher result;
- keeps up to `max_parallel_researchers` projects running continuously and
  refills a freed slot without waiting for unrelated researchers;
- preserves one Codex thread per role/project across restarts;
- periodically runs the research-process supervisor independently, so a slow
  supervisor never blocks results, director decisions, or researcher slots;
- records JSONL scheduling events, raw Codex traces, timings, and a compact `STATUS.md`.

Continuous mode is completion-driven. Director wake requests are coalesced
while a director is already running, and unchanged durable work is deferred by
the existing observation hash. `cycle_interval_seconds` is only the liveness
fallback; its next deadline is measured from the end of the latest director
turn, and it is not a batch barrier. `supervisor_every_cycles` multiplies that
interval for the independent supervisor cadence. `director_wake_requested`,
`director_wake_dispatched`, and `researcher_slot_filled` events make
result-to-decision and slot-refill latency directly measurable.

An agent turn that leaves its project and material artifacts unchanged cannot
hot-loop: its last outcome is shown to the director, and the same project waits
one fallback interval unless the director changes its contract. Source reloads
also remain fail-safe: the service stops admitting new turns, lets already
running agent turns reach their boundary, and then exits for systemd restart.

The lab directory is the durable interface:

```text
CAMPAIGN.md
DIRECTOR_LOG.md
SUPERVISOR_LOG.md
STATUS.md
projects/<project>/
  PROJECT.md
  RESEARCH_LOG.md
  STATUS.json
runtime/
  state.json
  status.json
  events.jsonl
  traces/
```

Existing artifact, telemetry, admission, provider, and experiment scripts remain available as optional tools. Researchers use them when they improve a project; they are not orchestration prerequisites.

## Shared GPU benches

Provider GPUs belong to the lab rather than individual projects. Live state is one atomic inventory at `research_lab/runtime/gpus.json`; every change is also appended to `runtime/gpu_events.jsonl`.

- The director creates the provider resource, gives it an absolute cleanup watchdog/deadline, registers it, and alone decides when to drain and tear it down.
- A researcher claims one compatible bench, runs and repairs experiments in place, updates the concise description of what is resident, then releases it without teardown.
- A stale claim remains fenced. The director inspects it and explicitly reclaims it to maintenance; another researcher never steals it automatically.
- Independent benches can run concurrently. Compatible projects queue onto existing resident state.
- The supervisor runs on its own periodic cadence even when the director is deferred. It compares the inventory with provider listings and lifecycle owners/watchdogs, fences objectively expired or ownerless registered benches by marking them draining, and wakes the director for provider cleanup. Healthy audits are not logged.

The inventory is deliberately not a provider abstraction or scheduler. Provider tools still create and delete resources; this file only coordinates ownership and records hardware, provider identifiers, hourly cost, watchdog/deadline, and resident model/checkpoint/image/runtime/cache/server state.

```bash
# Everyone can inspect the live benches.
PYTHONPATH=research/factory/src python3 -m grad_research.gpu_pool \
  --lab /path/to/research_lab list

# Director: register a resource after provider create and watchdog setup.
PYTHONPATH=research/factory/src python3 -m grad_research.gpu_pool \
  --lab /path/to/research_lab register --spec /path/to/bench.json

# Researcher: claim, then release with an optional JSON contents update.
PYTHONPATH=research/factory/src python3 -m grad_research.gpu_pool \
  --lab /path/to/research_lab claim --project PROJECT --accelerator h200-sxm
PYTHONPATH=research/factory/src python3 -m grad_research.gpu_pool \
  --lab /path/to/research_lab release --project PROJECT --contents /path/to/contents.json

# Director: stop new claims, perform provider cleanup, then retire the record.
PYTHONPATH=research/factory/src python3 -m grad_research.gpu_pool \
  --lab /path/to/research_lab drain --bench BENCH
PYTHONPATH=research/factory/src python3 -m grad_research.gpu_pool \
  --lab /path/to/research_lab retire --bench BENCH --cleanup-verified
```

The director can return an inspected maintenance bench to service with `ready --bench BENCH`. The registration JSON has only these top-level fields: `id`, `provider`, `accelerator`, `resource`, `contents`, `lifecycle`, and `hourly_cost_usd`. `lifecycle` contains `watchdog` and `deadline_utc`. Keep credentials out of it.

## Shared GPU profiling

[`PROFILING.md`](PROFILING.md) documents the provider-neutral `research/factory/tools/grad-profile` command. It records profiler-off baselines, bounded NVIDIA Nsight or AMD ROCm captures, exact-shape/codegen artifacts, normalized timeline/counter summaries, energy, and $/token comparisons. Deep profiling is optional and question-driven; it must not delay credible experiments.

[`SCIENTIFIC_TOOLS.md`](SCIENTIFIC_TOOLS.md) documents the optional instrument shelf for matched endpoint replay, first-divergence localization, exact-shape reproduction and kernel evaluation, hot-operation replacement, model surgery, warm workspaces, and upstream tool discovery. These tools are available through the shared `tools` directory and do not add harness stages or replace researcher judgment.

[`data/providers.json`](data/providers.json) tracks RunPod, Scaleway, and Gcore interfaces and verified profiler-access status without storing credentials. `research/factory/tools/grad-profile providers --provider runpod` reads live authenticated Pod stock and identifies the current MI300X route without creating resources; RunPod is the default venue for ordinary AMD experiments while stock is positive. [`docs/GCORE.md`](docs/GCORE.md) contains the Gcore usage guide plus its daily-refreshed Markdown price/availability snapshot. [`data/profiling_shape_atlas.json`](data/profiling_shape_atlas.json) is the shared exact-shape measurement inventory.

## Shared GPU price inventory

[`data/gpu_prices.json`](data/gpu_prices.json) is the single reusable price source for research economics. It separates actual experimental rates from the base production rate: a reasonable 12–24 month, 8–64 GPU, non-preemptible commitment rather than on-demand, spot, promotional, or hyperscale-floor pricing. A current matching written quote supersedes the planning estimate.

The director owns one refresh when the three-day window expires. Ordinary researchers consume the fresh inventory and do not repeat market searches unless their project is the refresh owner or needs an accelerator/topology that is absent. Validate it or inspect one accelerator with:

```bash
PYTHONPATH=research/factory/src python3 -m grad_research gpu-prices --require-fresh
PYTHONPATH=research/factory/src python3 -m grad_research gpu-prices --accelerator amd-mi355x
```

During each three-day refresh, update source retrieval timestamps, public/quoted reference rates, the evidence range, and the derived planning rate together. Preserve prior rates in version history; do not silently substitute an experimental preemptible rate into production economics.

## Shared accelerator capability inventory

[`data/accelerator_inventory.json`](data/accelerator_inventory.json) is the reusable hardware source for model–chip co-design. It covers practically obtainable NVIDIA, AMD, Intel, Google, and AWS inference/training accelerators, with separate architecture profiles for execution geometry shared by several SKUs. The fields include compute-unit geometry, concurrency limits, local/shared memory, cache, HBM capacity and bandwidth, numeric formats, peak vendor math, links, partitioning, power, software, availability, and concrete co-design implications.
The latest source audit, additions, live provider checks, and uncertainty notes are in [`docs/GPU_INVENTORY_REFRESH_2026-07-28.md`](docs/GPU_INVENTORY_REFRESH_2026-07-28.md).

Hardware capabilities have a weekly review cadence; changing market rates use the three-day price inventory. Unknown or undisclosed fields are `null`, not estimates. Vendor peak figures are useful ceilings, not measured application throughput. Query one chip or screen candidates without duplicating hardware research:

```bash
PYTHONPATH=research/factory/src python3 -m grad_research accelerators --accelerator nvidia-l40s
PYTHONPATH=research/factory/src python3 -m grad_research accelerators --vendor AMD --min-memory-gb 250 --format fp4
PYTHONPATH=research/factory/src python3 -m grad_research accelerators --require-current
```

Each chip may reference a matching `price_inventory_id`. Keep model-specific measurements, exact tensor-shape analysis, and runtime compatibility findings in the research project; promote only reusable hardware corrections back into this inventory.

## Run

Create an external config containing the repository, lab directory, models, cadence, and shared tool paths. No credentials belong in it.

```json
{
  "repo_dir": "/root/workspace",
  "lab_dir": "/root/workspace/research/lab/experiments/glm47flash/research_lab",
  "cycle_interval_seconds": 60,
  "max_parallel_researchers": 5,
  "spend_cap_usd": 100.0,
  "spend_cap_starts_at": "2026-07-17T21:59:00Z",
  "quiescent_spend_floor_usd": 0.0,
  "supervisor_every_cycles": 6,
  "routes": {
    "director": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
    "researcher": {"model": "gpt-5.6-terra", "reasoning_effort": "medium"},
    "deep_researcher": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
    "supervisor": {"model": "gpt-5.6-sol", "reasoning_effort": "high"}
  },
  "tools": [
    "/root/workspace/research/factory/tools",
    "/root/workspace/research/lab/experiments/glm47flash/campaign_100"
  ]
}
```

Run one synchronous diagnostic cycle or the continuous event-driven service:

```bash
PYTHONPATH=research/factory/src python3 -m grad_research.lab_harness --config <config> --once
PYTHONPATH=research/factory/src python3 -m grad_research.lab_harness --config <config>
```

When `spend_cap_usd` and `spend_cap_starts_at` are configured, the harness creates `runtime/spend_cap.json` and reserves each paid project's full `authorized_spend_usd` before scheduling it. Reservations are conservative and durable. A terminal project settles its recorded cumulative `actual_spend_usd`, releases the unused reservation, and leaves the actual spend counted against the fixed campaign cap. Changing the cap or start timestamp still requires an explicit new ledger rather than a config edit. Projects without a reservation are prompted and scheduled for zero-cost work only; projects that would overcommit the remaining cap are deferred. `quiescent_spend_floor_usd` is an opt-in lab-specific minimum executable reservation: when the portfolio and GPU inventory are empty, durable observations are unchanged, and available authority is below this floor, fallback director turns are deferred while periodic supervisors continue. The default is `0`, which preserves aggressive empty-portfolio replenishment.

The systemd unit is `systemd/gradiated-research-lab@.service`. See `SUPERVISOR.md` for installation and cutover.

## WhatsApp result notifications

`grad_research.result_notifier` tails completed researcher turns independently of the lab and sends the project's compact `STATUS.json` result and next action through Meta's WhatsApp Cloud API. Notification failures retry with backoff and never block research. New notifier state starts at the end of the event log, so enabling it does not replay historical turns.

Install `systemd/gradiated-research-notifier@.service`, then create the host-only file `/root/.config/gradiated/research-lab/whatsapp.env`:

```bash
WHATSAPP_ACCESS_TOKEN=<permanent-system-user-token>
WHATSAPP_PHONE_NUMBER_ID=<business-phone-number-id>
WHATSAPP_RECIPIENT=<international-number-with-country-code>
WHATSAPP_GRAPH_VERSION=v23.0
WHATSAPP_TEMPLATE_NAME=research_result
WHATSAPP_TEMPLATE_LANGUAGE=en_US
```

For unattended notifications, create and approve a utility template named `research_result` whose body contains one text variable, for example `Research result: {{1}}`. Omit `WHATSAPP_TEMPLATE_NAME` only when a free-form customer-service conversation window is deliberately being used. Keep tokens and phone numbers outside the repository.

```bash
systemctl --user enable --now gradiated-research-notifier@glm47.service
journalctl --user -u gradiated-research-notifier@glm47.service -f
```

## Verify

```bash
PYTHONPATH=research/factory/src:research/factory/tests \
  python3 -m unittest research/factory/tests/test_lab_harness.py \
    research/factory/tests/test_result_notifier.py -v
grad-ctl devex check
```
