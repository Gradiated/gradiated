# Research-loop efficiency

Measure research speed as valid decisions produced, not as command count or GPU occupancy. The daily report partitions an active Codex turn into synchronous tool wait and model/orchestration time, then reports provider allocations separately because provider work may overlap the coordinator.

```bash
python3 .agents/skills/experiment-run/scripts/research_efficiency.py \
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

Speed policy:

1. Keep the main scientific director on the user-selected model.
2. Use high reasoning at hypothesis, admission, interpretation, and stop/promotion gates.
3. Route mechanical workers to faster models or lower effort and give them disjoint outputs.
4. Batch repeated operations into one deterministic command.
5. Prebuild and locally validate provider images; reuse resident state across preregistered arms.
6. Run offline analysis while a bounded provider command executes.
