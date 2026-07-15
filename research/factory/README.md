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

## What the harness does

`grad_research.lab_harness` uses the installed `codex` CLI and saved ChatGPT/Codex login. It explicitly removes API-key environment variables from child Codex processes. It:

- runs one Sol director turn;
- discovers active project directories and runs several researchers in parallel;
- preserves one Codex thread per role/project across restarts;
- periodically runs the research-process supervisor;
- records JSONL scheduling events, raw Codex traces, timings, and a compact `STATUS.md`.

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

## Run

Create an external config containing the repository, lab directory, models, cadence, and shared tool paths. No credentials belong in it.

```json
{
  "repo_dir": "/root/workspace",
  "lab_dir": "/root/workspace/research/sol/experiments/glm47flash/research_lab",
  "cycle_interval_seconds": 60,
  "max_parallel_researchers": 3,
  "supervisor_every_cycles": 6,
  "routes": {
    "director": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
    "researcher": {"model": "gpt-5.6-terra", "reasoning_effort": "medium"},
    "supervisor": {"model": "gpt-5.6-sol", "reasoning_effort": "high"}
  },
  "tools": [
    "/root/workspace/research/factory/tools",
    "/root/workspace/research/sol/experiments/glm47flash/campaign_100"
  ]
}
```

Run one cycle or continuously:

```bash
PYTHONPATH=research/factory/src python3 -m grad_research.lab_harness --config <config> --once
PYTHONPATH=research/factory/src python3 -m grad_research.lab_harness --config <config>
```

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
python3 tools/devex/check.py
```
