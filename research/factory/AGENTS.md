# Research lab instructions

This workstream owns a deliberately small scheduler for three agent roles. Scientific behavior belongs in `$research-director`, `$researcher`, and `$research-supervisor`; do not turn it back into workflow code.

The harness may schedule subscription-authenticated Codex turns, preserve thread IDs, run researchers in parallel, and record status/timing traces. Shared scripts are optional tools. Existing event, artifact, admission, telemetry, and provider modules remain available to researchers when a project benefits from them, but they do not define the research loop.

Keep credentials outside the repository. Tests never call Codex or a provider. An active provider controller must reach its cleanup/terminal state before replacing its supervising service.

## Commands

```bash
PYTHONPATH=research/factory/src:research/factory/tests python3 -m unittest research/factory/tests/test_lab_harness.py -v
PYTHONPATH=research/factory/src python3 -m grad_research.lab_harness --config <config> --once
```
