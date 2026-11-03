---
name: experiment-record
description: Keep conversation traces, a thin experiment summary, and supporting data or charts in a dated research folder for later writing. Use when the user asks to record an experiment as it develops, rather than draft or publish a post.
---

# Experiment record

Keep the actual conversation as the record someone can later turn into a post.
Do not replace it with a long reconstructed narrative or publish it unless asked.

## Start

- Look for an existing record for this work before creating another.
- Use `research/experiments/YYYY-MM-DD-short-name/`, dated by the experiment's
  start date. Keep that folder stable as work continues across days.
- Put conversation exports in `traces/`: structured JSONL plus a small
  coverage/provenance manifest. Do not duplicate the conversation in Markdown
  unless the user specifically asks for a readable copy. Use the
  conversation's stable thread ID and item IDs to avoid duplicate exports.
- Keep the experiment's `README.md` to a few bullets: question/setup, current
  result and caveat, and links to the traces and useful data/charts.
- Add `data/` and `figures/` only for useful supporting artifacts. The top-level
  `research/experiments/README.md` describes the convention; do not add per-run
  log entries or a status index there.

## Keep it current

After meaningful progress, extend or refresh the same conversation export and
update the few summary bullets if needed. Keep failures, questions, corrections,
and superseded attempts in the transcript instead of curating only successes.
Do not add a prose log entry for every tool call.

Export a bounded snapshot so reading/exporting the thread does not recursively
include the export itself forever. Paginate to the recorded high-water position,
recover truncated messages when supported, and state the cutoff and missing
coverage. Never call a reconstructed summary a full transcript. A T3 deep link
is not automatically public or accessible outside that T3 instance.

Include visible user/assistant messages. Keep hidden reasoning, system/developer
prompts, secrets, and restricted customer/tool payloads out. Redact credentials
and authentication links; record redaction categories/counts without the values.
For T3, infer speaker from the message type: delivered user messages can have
`createdBy: null`, so the creator field alone is not a reliable role label.
When tools expose only activity summaries or raw bodies cannot be exported,
keep labeled activity metadata rather than inventing or implying complete logs.
Omit command previews, arguments, titles, and raw bodies from activity exports.
Before committing an approved export, run `python3
.agents/skills/experiment-record/scripts/sanitize_trace.py --self-test PATH/TO/traces`
to redact literal/escaped network addresses and account endpoints and refresh hashes.
This helper supplements the data-handling review; it does not clear restricted
source material for export.

Separate measurements, derived values, estimates, and hypotheses. Preserve
denominators, units, model/hardware/data scope, comparison conditions, and
judge/sample uncertainty. Never turn an infrastructure failure into a model
failure, a throughput window into a causal speedup, or training loss into a
capability gain. Mark partial or historically reconstructed results clearly.

Keep enough provenance to locate the source: thread/run/item IDs, capture time,
coverage, artifact hashes, and chart-generation command where useful. Preserve
prior results when a repair changes them. Avoid duplicating maintained reports.

Apply the experiment's data-handling rules before exporting anything. Prefer
approved aggregates; leave restricted prompts, traces, customer records,
credentials, and large datasets at their authorized location. A record is not
automatically cleared for public release.

This skill records work; it does not authorize extra experiments, spending,
schedules, deployments, or publication. Follow the user's current scope and
continue the actual research rather than building a documentation system.
