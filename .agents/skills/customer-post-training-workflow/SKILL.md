---
name: customer-post-training-workflow
description: End-to-end workflow for post-training a model for a customer from their production LLM traces, from export and task breakdown through trace cleaning, experiments, training, evaluation and delivery. Use when starting or resuming customer post-training work, to find which stage comes next and which skill runs it.
---

# Customer post-training workflow

Turn a customer's production traces into a model that beats their current one on a task they care about. Work stage
by stage, and show the user each stage's results before starting the next.

## Ground rules

- Keep the customer's data and any clone of their code in their own folder outside this repository
  (`~/dev/<customer>/`). Never commit or push either. Only skills and reusable tooling go in this repository.
- Customer accounts, such as a PostHog impersonation, are read-only: confirm the org and project, run only
  queries, and tell the user when they can log out.
- Model calls that see customer content go through OpenRouter zero-data-retention providers.

## Stages

1. **Export the traces.** Find where the full prompts and responses live, check retention (content may be expiring),
   and download everything with paginated read-only queries. Check the row count against the source.

2. **Break the traces into tasks.** A task is one kind of model call with one job, usually one agent or prompt.
   For each task, find:
   - what it does, from sample traces and the customer's code;
   - the model it uses;
   - calls, traces and tokens per day;
   - cost, and its share of the total;
   - latency and error rate.

   Show the user a table, one row per task, and choose the task or tasks to train on. Look at cost, volume, whether
   a smaller model could do the job, and whether results can be scored. Some customers have only one task.

3. **Clean and anonymize** the chosen tasks with `$trace-cleaning`.

4. **Choose the first experiments.** A skill for this is planned. For now, write down each experiment's hypothesis,
   data, baseline, budget and the eval that decides it.

5. **Build the training data or RL environments.** Split by conversation or end user, never by row. Spot-check the
   result in rounds of 20 and then 40, as in cleaning.

6. **Train.** Get GPUs with `$dev-training` or `$gpu-host-lease`, and run each experiment as `$experiment-run`
   describes.

7. **Evaluate** on held-out data. Compare against the customer's current model and the untrained base model.

8. **Deliver** the adapter as a task model version. Promote it only with the user's approval.
