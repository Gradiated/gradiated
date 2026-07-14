# Task: 2026-07-14-research-supervisor

## Outcome

A persistent local supervisor will safely resume the GLM-4.7 research program, route bounded Codex turns through the user's saved ChatGPT authentication, and expose enough durable status and timing data for a separate Luna session to inspect progress.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/18
- GitHub project:
- owner: codex-supervisor-build
- Codex thread:
- created: 2026-07-14T18:28:19+00:00
- started: 2026-07-14T18:28:19+00:00
- last updated: 2026-07-14T18:28:19+00:00
- scope: research/factory supervisor implementation, tests, docs, and service template
- excluded paths: active GLM campaign artifacts owned by the retiring coordinator
- dependencies: existing factory event store, lab lease, provider watchdog/cleanup contract, saved Codex login

## Contract

- hypothesis or user value: deterministic scheduling plus explicit model routing will keep research running without spending Sol-high time on polling and mechanical orchestration.
- acceptance checks: lease fencing; read-only observe mode; active resume; persistent Codex thread; heartbeat during turns; timeout; atomic JSON/Markdown status; model/timing event capture; service smoke test.
- quality gate: no provider mutation while another owner holds the lease or a P0 recovery action is unresolved; no credential material in repository or prompts.
- SLO or budget: one bounded Codex turn per meaningful cycle; back off after no progress; no new provider budget authority.
- timeout: 60 minutes per director turn by default, independently bounded paid runs retain their existing deadlines.
- artifact locations: research/factory/src/grad_research/supervisor.py, research/factory/tests/test_supervisor.py, persistent lab root supervisor/<program>/
- resume command: systemctl --user restart gradiated-research-supervisor@glm47.service
- rollback or cleanup: stop/disable the service; it does not delete research state or provider resources.

## Plan

1. Implement supervisor configuration, fencing, Codex runner, model routes, and status views.
2. Test failure, lease, heartbeat, timeout, and event parsing paths.
3. Install in observe mode, then activate after the old lease and provider state are reconciled.

## Result

- status: active
- verification:
- changed paths:
- limitations or blocked paths:
- commit:
- next action:
