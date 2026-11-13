# Research-loop efficiency

Measure research speed as valid decisions produced, not as command count or GPU occupancy. The daily report partitions an active Codex turn into synchronous tool wait and model/orchestration time, then reports provider allocations separately because provider work may overlap the coordinator.

```bash
gradctl research efficiency \
  --thread-id "$CODEX_RESEARCH_THREAD_ID" \
  --campaign-dir "$CAMPAIGN_DIR" \
  --hours 24 \
  --output-dir "$RESEARCH_LAB_ROOT/efficiency"
```

The analyzer reads timestamps, event types, tool names, thread model/effort metadata, and campaign lifecycle artifacts. It does not read model reasoning or tool-output contents. The output directory receives dated JSON/Markdown plus `LATEST.json` and `LATEST.md`.

Review these metrics daily:

- scientific outcomes per active coordinator hour and per dollar;
- model/orchestration versus synchronous tool-wait share;
- tool calls per active hour and context compactions;
- subagent count, reasoning-effort mix, and longest worker critical path;
- provisioning, SSH, remote execution, cleanup, and provider-active time;
- useful GPU seconds versus provider-active seconds;
- invalid/operational spend fraction and failure classes.

Interpretation is fail-closed. Provider activity can overlap model work, so its duration is not added to the Codex time partition. `useful_gpu_seconds` remains missing until the experiment harness emits it. Never infer useful GPU work from allocation lifetime or accelerator existence.

Initial improvement targets are directional, not scientific gates: cut tool calls per active hour by roughly half, bring model/orchestration below 50% on execution-heavy cycles, keep invalid/operational spend below 10%, and put more than half of provider-active time into measured useful GPU work. Change these targets after a week of comparable daily reports; never meet them by suppressing required evidence.

Speed policy:

1. Keep the main scientific director on the user-selected model.
2. Use high reasoning at hypothesis, admission, interpretation, and stop/promotion gates.
3. Route mechanical workers to faster models or lower effort and give them disjoint outputs.
4. Batch repeated operations into one deterministic command.
5. Prebuild and locally validate provider images; reuse resident state across preregistered arms.
6. Run offline analysis while a bounded provider command executes.

## When to move beyond one interactive thread

Keep the interactive Sol-high coordinator while it is producing sound decisions and the daily report is improving. Move to a small local event-driven supervisor when model/orchestration remains above 50% for two comparable days, routine work still consumes Sol-high turns, or the campaign stops whenever the interactive thread is unavailable.

The supervisor should be ordinary deterministic software, not another unbounded LLM loop. It owns the durable queue, budgets, provider adapters, deadlines, and metrics; launches Codex workers with explicit model and reasoning choices; and invokes Sol-high only at scientific decision gates. Codex non-interactive mode and the Codex SDK support programmatic threads and model selection while the local Codex runtime reuses its saved authentication. Keep authentication in the Codex credential store and provider credentials in the provider adapter environment; never copy either into prompts or repository state.

The persistent supervisor is now appropriate because the campaign otherwise stops with the interactive thread and the measured coordinator time is dominated by model/orchestration. It runs one fresh, bounded Sol director decision per material transition, forbids internal subagent spawning/polling, then refreshes the queue and dispatches up to five researchers on the configured Luna/Terra routes. Ownership serializes mutation only within one allocation; independent projects may run paid GPU sessions concurrently when the director judges the spend worthwhile. Keep it lean: explicit backoff when the event head does not advance, bounded worker retries, and no second workflow system. Its Codex JSONL traces, worker results, and scheduler events are inputs to this same daily efficiency report.
