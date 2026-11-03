---
name: experiment-record
description: Start or maintain a research experiment record with methods, results, data, charts, failures, and learnings for later writing. Use when the user asks to document an experiment as it develops, rather than draft or publish a blog post.
---

# Experiment record

Keep a factual working record that someone can later turn into a post. Do not
write marketing copy or publish anything unless asked.

## Start

- Look for an existing record for this work before creating another.
- Use `research/experiments/YYYY-MM-DD-short-name/`, dated by the experiment's
  start date. Keep that folder stable as work continues across days.
- Begin with `README.md`. Add `data/` and `figures/` only when there are useful
  artifacts to put there. Link the record from `research/experiments/README.md`.
- Capture the question, hypothesis, baseline, setup, data, metrics, evaluation
  protocol, resource/time constraints, and what would change the decision.
  Record what actually ran, including revisions and deviations.

## Keep it current

While working on the requested experiment, update the same record after a
meaningful run, failure, methodological change, or decision, and before handing
the work back. Do not add an entry for every tool call. A simple structure is:

1. **Overview:** question, current status, strongest supported result.
2. **Setup and method:** enough detail to interpret or reproduce the work.
3. **Experiment log:** date/run ID, hypothesis, change, measurement, result,
   decision, and an evidence link. Keep failed and superseded attempts visible.
4. **Results and artifacts:** small CSV/JSON summaries and linked figures.
5. **Learnings and limits:** supported conclusions, competing explanations,
   uncertainty, and open questions.
6. **Next steps:** pending runs and the next discriminating experiment.

Separate measurements, derived values, estimates, and hypotheses. Preserve
denominators, units, model/hardware/data scope, comparison conditions, and
judge/sample uncertainty. Never turn an infrastructure failure into a model
failure, a throughput window into a causal speedup, or training loss into a
capability gain. Mark partial or historically reconstructed results clearly.

Keep compact, decision-relevant artifacts and enough provenance to locate the
source: revision, run/manifest path, hash, capture time, and chart-generation
command where useful. Preserve prior versions when a repair changes a result.
Avoid copying large raw logs or duplicating another maintained report; link it.

Apply the experiment's data-handling rules before exporting anything. Prefer
approved aggregates; leave restricted prompts, traces, customer records,
credentials, and large datasets at their authorized location. A record is not
automatically cleared for public release.

This skill records work; it does not authorize extra experiments, spending,
schedules, deployments, or publication. Follow the user's current scope and
continue the actual research rather than building a documentation system.
