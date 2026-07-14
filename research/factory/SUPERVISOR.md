# Persistent research supervisor

The supervisor is a small deterministic process that schedules bounded Codex turns. It uses the existing `codex` CLI login, so research reasoning is billed through the saved ChatGPT/Codex subscription rather than an API key. It never stores auth material in the repository or in prompts.

Scientific gates route to Sol/high, implementation to Terra/medium, and mechanical work to Luna/medium by default. Each Sol director turn is fresh and bounded to 15 minutes by default; it must not spawn its own Codex subagents or poll long experiments. After each Sol turn, the supervisor refreshes the queue and dispatches up to two explicitly `parallel_offline` packets concurrently to the appropriate fast route. Provider/setup-affine packets remain serialized and are never delegated as workers. The supervisor owns the coordinator lease and heartbeats it while every Codex turn runs. A foreign lease causes a read-only wait. Provider reconciliation and cleanup remain P0 gates in the factory resume contract.

Admitted provider controllers are first-class supervisor jobs. Configure a `provider_launcher` argv template outside the repository; the supervisor expands `{run_id}`, `{admission_sha256}`, `{reservation_id}`, `{allocation_id}`, `{absolute_deadline_utc}`, `{setup_key}`, `{output_dir}`, `{root}`, `{repo_dir}`, `{campaign_dir}`, `{owner}`, and `{lease_epoch}`, then launches the controller itself with durable stdout/stderr paths. Codex is never allowed to leave a provider command running inside an interactive tool session. `STATE.json`, `STATUS.json`, and `events.jsonl` retain the job PID, command hash, liveness, exit status, and logs. A running job receives lease heartbeats; an exited job is exposed as `provider_exited` for factory reconciliation rather than silently retried.

Runtime state is under `$RESEARCH_LAB_ROOT/supervisor/<program-id>/`:

- `STATUS.md` is the concise view to read from a separate Luna/Codex status session;
- `STATUS.json` is the machine-readable equivalent;
- `STATE.json` holds the persistent Codex thread ID and cycle counters;
- `events.jsonl` records scheduler decisions and cycle timings;
- `codex/*.jsonl` and `*.stderr.log` preserve noninteractive Codex events and errors.
- `workers/<packet>/RESULT.json` and the matching worker trace preserve delegated work, exit status, and output location.
- `provider/<run-id>.stdout.log` and `.stderr.log` preserve the independently launched provider controller.

The config is intentionally outside the repository. Start in `observe` mode, verify the status view, then change to `active` only when the retiring coordinator is stopped. The factory lease still prevents overlap until its TTL expires.

```json
{
  "root": "/root/.local/share/gradiated/research-lab",
  "program_id": "glm-4.7-flash",
  "repo_dir": "/root/workspace",
  "campaign_dir": "/root/workspace/research/sol/experiments/glm47flash/campaign_100",
  "owner": "supervisor-glm47",
  "mode": "observe",
  "director_timeout_seconds": 900,
  "reuse_director_thread": false,
  "provider_launcher": [
    "/usr/bin/python3",
    "{repo_dir}/path/to/provider_controller.py",
    "--run-id", "{run_id}",
    "--admission-sha256", "{admission_sha256}",
    "--output-dir", "{output_dir}",
    "--absolute-deadline", "{absolute_deadline_utc}"
  ],
  "routes": {
    "director": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
    "implementation": {"model": "gpt-5.6-terra", "reasoning_effort": "medium"},
    "mechanical": {"model": "gpt-5.6-luna", "reasoning_effort": "medium"}
  },
  "max_parallel_workers": 2,
  "max_worker_attempts": 2
}
```

Install the unit for the current user and inspect it with:

```bash
mkdir -p ~/.config/systemd/user ~/.config/gradiated/research-supervisor
cp research/factory/systemd/gradiated-research-supervisor@.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gradiated-research-supervisor@glm47.service
systemctl --user status gradiated-research-supervisor@glm47.service
```

For a safe one-cycle diagnostic, use `PYTHONPATH=research/factory/src python3 -m grad_research.supervisor --config <config> --once`. Stop or disable the unit to roll back; this leaves experiment evidence and provider state intact.
