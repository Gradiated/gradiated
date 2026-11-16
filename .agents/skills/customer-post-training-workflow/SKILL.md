---
name: customer-post-training-workflow
description: End-to-end workflow for post-training a model for a customer from their production LLM traces, from export and task breakdown through trace cleaning, experiments, training, evaluation and delivery. Use when starting or resuming customer post-training work, to find which stage comes next and which skill runs it.
---

# Customer post-training workflow

Turn a customer's production traces into a model that beats their current one on a task they care about. Work stage by stage, and show the researcher each stage's results before starting the next.

The **researcher** is the person at Gradiated running this work. The **customer** is the company whose traces
these are, and **end users** are the customer's own users.

## Ground rules

- Keep the customer's data and any clone of their code in their own folder outside this repository
  (`~/dev/<customer>/`). Never commit or push either. Only skills and reusable tooling go in this repository.
- When getting trace data from the customers account, such as a PostHog impersonation, you should only take read-only actions: confirm the org and project, run only queries, and tell the researcher when they can log out.
- Model calls that see customer content go through OpenRouter zero-data-retention providers.

## Stages

1. **Export the traces.** Find where the full prompts and responses live, check retention (content may be expiring),
   and download everything with paginated read-only queries. Check the row count against the source.

2. **Break the traces into tasks.** A task is one kind of model call with one job, usually one agent or prompt.
   Group the traces into tasks, then read the customer's codebase to understand each one. Write a short report per
   task, a few paragraphs rather than a table row, covering:
   - **What it does and how it is set up:** for example, an agent with an MCP server and these tools, a one-shot
     extraction prompt, or a subagent called by another task. Say where it lives in the code.
   - **Model and usage:** the model, calls and traces per day, tokens, cost and its share of the total, latency and
     error rate.
   - **Evals:** whether the codebase has evals for it, what they measure, and how developed they are (none, a few
     hand-checked examples, a scored dataset, or running in CI).
   - **People:** who commits to it most often, and recently, from the git history of its files.

   Choose the task or tasks to train on with the researcher. Weigh cost, volume, whether a smaller model could do the job,
   and whether results can be scored. Some customers have only one task.

3. **Clean and anonymize** the chosen tasks with `$trace-cleaning`.

4. **Choose the first experiments.** A skill for this is planned. For now, write down each experiment's hypothesis,
   data, baseline, budget and the eval that decides it.

5. **Build the training data or RL environments.** Split by conversation or end user, never by row. Spot-check the
   result in rounds of 20 and then 40, as in cleaning.

6. **Train.** Get GPUs with `$dev-training` or `$gpu-host-lease`, and run each experiment as `$experiment-run`
   describes.

7. **Evaluate** on held-out data. Compare against the customer's current model and the untrained base model.

8. **Deliver** the adapter as a task model version. Promote it only with the researcher's approval.
