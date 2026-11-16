---
name: customer-post-training-workflow
description: End-to-end workflow for post-training a model for a customer from their production LLM traces, from data access through trace cleaning, experiment selection, SFT or RL training, evaluation and delivery. Use when starting or resuming customer post-training work, to find which stage comes next and which skill runs it.
---

# Customer post-training workflow

The map for turning a customer's production traces into a model that beats their current one on their workload.
Each stage names the skill that runs it. Where a stage has no skill yet, follow the notes here and write the skill
once the procedure has worked on a real customer.

Work stage by stage. A stage is done when its exit criterion holds, not when its code runs. Quality of the data
bounds everything after it, so do not hurry stage 2 to reach training.

## Ground rules

- Keep each customer's data and working files in their own folder outside this repository
  (`~/dev/<customer>/`), next to any clone of their code. Commit only reusable tooling and skills here.
- Access to a customer's accounts, such as a PostHog impersonation, is read-only. Confirm the org and project before
  querying, run only reads, and tell the user when they can log out.
- Model calls that see customer content go through OpenRouter zero-data-retention providers. Cheap models are enough
  for tagging, review and auditing.
- Report each stage's numbers to the user before starting the next.

## Stages

| # | Stage | Skill | Exit criterion |
|---|---|---|---|
| 1 | Understand and export the source | `$trace-cleaning`, step 0 | Raw export verified against source totals; coverage, retention and capture loss reported |
| 2 | Clean and anonymize | `$trace-cleaning` | A close-read round of 20 and then 40 with no serious findings; gates pass |
| 3 | Choose the first experiments | planned (`$post-training-experiments`) | A ranked list of experiments with hypotheses, baselines, budget and the eval that decides each |
| 4 | Build training data or RL environments | none yet | SFT rows or environments spot-checked in rounds of 20 and 40 |
| 5 | Train | `$dev-training`, `$gpu-host-lease`, `$experiment-run` | Runs finish within budget with checkpoints and logs |
| 6 | Evaluate | `$experiment-run` | Candidate against the customer's current model and base on held-out data, with uncertainty |
| 7 | Deliver | none yet | Adapter uploaded as a task model version and promoted only with the user's approval |

### 1. Understand and export the source

Learn the customer's product and agents from their code and traces: which agents exist, what each one does, its
models, volume, cost and latency. Find where full content lives and how their instrumentation shaped it. Export
everything still within retention, since it expires. `$trace-cleaning` step 0 has the profiling and export
procedure.

### 2. Clean and anonymize

Run `$trace-cleaning` until its close-read loop is clean. Its output is the only data later stages use.

### 3. Choose the first experiments

To be written as `$post-training-experiments`. Until then, choose from the stage 1 profile:

- which agent or call type carries the most volume, cost or latency, and whether a smaller model could serve it;
- whether outcomes can be scored automatically (structured output, tool success, the user's next action), which
  decides between SFT and RL;
- how much clean, unique data each candidate has after stage 2;
- the cheapest experiment that would show a gain, and the baseline it must beat.

State each experiment's hypothesis, data, baseline, budget, timeout and deciding eval before running it.

### 4. Build training data or RL environments

Split by conversation or by customer end user, never by row. Restore what the capture dropped where the customer's
code makes it recoverable (for example a system prompt kept in source). Spot-check the built rows or generated tasks
in rounds of 20 and then 40, as in stage 2.

### 5. Train

Get compute with `$dev-training` (spot or on-demand VMs) or `$gpu-host-lease` (a host from the serving pool). Run
each experiment as `$experiment-run` describes, with an absolute deadline and cleanup.

### 6. Evaluate

Evaluate on held-out data the model never saw, against the customer's current model and the untrained base. Include
an untrained control when a gain is small. Report the uncertainty, and do not carry a result over to another model,
agent or workload without measuring it there.

### 7. Deliver

Upload the adapter as a task model version, and promote it only with the user's approval. Report what it was trained
on, how it was evaluated and its known limits.
