---
name: trace-cleaning
description: Turn raw customer LLM traces (PostHog AI traces, OTel gen_ai spans, agent transcripts) into an anonymized, cleaned dataset fit for SFT or RL environment synthesis, by iterating an anonymizer against fresh random close-read samples until rounds come back clean. Use when exporting, anonymizing, cleaning, deduplicating or quality-checking customer trace data for training.
---

# Trace cleaning

Data from this workflow seeds training sets and RL environments, so defects compound downstream: an earlier
environment was built from traces whose anonymizer had scrambled about a third of all SQL calls, and it was poor.
Garbage in, garbage out. The goal is two things at once: no real personal or customer-identifying data survives, and
every row stays accurate, internally consistent and worth training on.

The code is disposable. Write a fresh pipeline for each source's shape. What carries over is the loop below:
**anonymize everything → automated gates → close-read a fresh random sample → fix each defect class at its root with
a test → rerun → new sample**, until a round finds nothing serious.

## Data handling

- Keep each customer's raw data, working files and outputs in that customer's own folder outside this repository
  (for example `~/dev/<customer>/traces/`). Never commit trace content, fake-to-real maps, tag caches or findings.
  Commit only reusable tooling and this skill.
- Every model call that sees raw or partly anonymized text goes through OpenRouter with zero data retention:

  ```python
  PROVIDER = {"zdr": True, "data_collection": "deny", "only": [<the account's enabled ZDR providers>],
              "allow_fallbacks": True, "sort": "throughput"}
  ```

  `OPENROUTER_API_KEY` comes from the environment; never print or write it. A cheap fast model is enough for every
  step (default `deepseek/deepseek-v4.1-flash-1017`, temperature 0, JSON output, reasoning off). Use a *different*
  cheap model for the independent audit so the tagger's blind spots are not shared.
- The coordinating agent works from counts, shapes, field names, anonymized rows, and reviewer findings. It does not
  read raw trace content into its own context, and it never sends raw content anywhere except the ZDR route.
- The fake-to-real map, tag cache and findings files stay on the machine that holds the raw data. Only anonymized
  rows and aggregate reports may leave it.
- Accessing a customer's account (for example via impersonation) is read-only: `SELECT` queries only, no saved
  queries, insights or setting changes. Confirm the org and project before querying.

## 0. Profile the source before writing code

Measure, do not assume. Report this to the user before building anything:

- Event or record types, counts, and date range. Where the content actually lives: in a PostHog project, large AI
  properties may be absent from `events.properties` and present only in `posthog.ai_events`
  (`input`, `output_choices`, `tools`, `trace_id`, `parent_id`, ...).
- Content coverage by month, agent, model and environment. Gaps usually mean capture was off or moved, not that
  traffic stopped.
- Retention. Content that expires daily makes export urgent; say how much is already gone.
- How the customer's instrumentation shapes what was captured. Read their code: processors that drop history, strip
  system prompts or truncate tool results make the copy lossy, and per-agent instrumentation can silently replace a
  global exporter (check the framework's precedence rule instead of assuming both receive spans).
- Volume: billed tokens, captured characters, and *unique* content (per trace, the largest input plus all outputs).
  Billed totals overcount because every call resends its context.

Export with keyset pagination on `(timestamp, uuid)` using a UTC cursor at full precision, a fixed upper bound, small
pages (a few hundred rows when inputs are large), retries, and files of a fixed size. Verify row count, uniqueness and
parseability against the source totals before going further.

## 1. Agree the policy with the user

Decide explicitly, and write the decisions into the pipeline's README:

- What counts as identifying: people, emails, phones, addresses, handles, IPs, account and payment ids, secrets,
  customer company and brand names, customer domains, end-user locations finer than a region.
- What is kept: public vendors and products, the customer's own product vocabulary where it is not identifying,
  code, schemas, tool names, field names, standard query parameters, dates.
- How replacements look: like-for-like and consistent within a trace (one fake per real value across every spelling,
  context and message), seeded from the trace id, assigned only after every real value in the trace is collected.
- Whether brand words inside identifiers are renamed (consistently in code, results and prose) or left alone.
- Numeric data such as money: keep, blur or drop. Blurring once broke internal arithmetic and was removed.
- Drop rules: trivial or aborted conversations, duplicate traces of one conversation, rows whose capture lost tool
  results or was truncated past usefulness.

## 2. Build the pipeline

Stages, each counted in the report:

1. **Normalize** the source into one conversation record shape (messages with roles, tool calls with arguments,
   tool results, system prompt if known, ids for trace, conversation and customer).
2. **Clean**: drop trivial rows, collapse duplicates, drop or flag rows with lost tool results or capture truncation.
   Count every drop by reason.
3. **Tag** prose with the cheap model: user and assistant text with code removed. Never tag code or tool arguments
   as text. Tag distinct cells of tabular tool results separately; query results are a main source of customer data.
   Cache verdicts per unit so a rerun only pays for new units.
4. **Detect** with deterministic patterns everywhere, including inside code: emails, URLs and hosts, UUIDs and their
   prefixes, provider-style ids (Stripe `cus_`, `in_`, `ch_`, ...), phones, IPs, secrets, long numeric ids.
5. **Reject bad tags**: unknown labels, anything code-shaped (operators, quotes, dots, `$`, snake_case, keywords,
   functions, schema names, names the trace itself uses as code), geography tagged as a company, single dictionary
   words.
6. **Replace** in two passes: collect all reals, then assign fakes and rewrite. Inside code, change only string
   literals and comments, never identifiers (unless the brand rename policy says so).
7. **Residual check**: drop any row where a hard pattern or a known real value survives.
8. **Split** by conversation or by customer, never by row, and check that no id appears in two splits.

Run in parallel processes with a throughput-sorted provider route. A full rerun should take minutes. If it takes an
hour, fix the bottleneck (cache misses, a slow provider, serial calls) before the next round.

## 3. Automated gates (every run)

- **Leak check** against the fake-to-real map outside code. Set a threshold with the user (around 1%); flagged rows
  are dropped either way.
- **Independent audit**: a second cheap model reads a sample of anonymized rows, tool results included, with canaries
  planted to prove it is looking. Filter its findings through the map so known fakes do not count.
- **Fidelity**: compare code (SQL, JSON, tool arguments) against raw. Corrupted or changed code must be near zero
  apart from deliberate renames, and every exception must be explained.
- **Structure**: every tool call has its result, roles alternate correctly, JSON still parses.
- **Quality flags** per row: truncation, empty answers, error-only turns, duplicated content.

Passing gates is necessary, not sufficient. In past runs the gates passed while close reads still found serious
defects.

## 4. Close-read loop

1. **Draw a fresh sample.** 20 conversations, seeded, stratified across source, customer, agent, model, length and
   outcome, excluding every conversation read in an earlier round (keep the list of read ids). Later rounds use 40.
2. **Review each pair** (raw and anonymized side by side) with a cheap ZDR model, one conversation per call, chunked
   if long, in parallel. Give every reviewer the same brief:

   > You are checking one conversation before it is used to train a model. You see the raw version and the
   > anonymized version. Report every defect, each as JSON with `class`, `severity` (serious | minor), `location`
   > (message index and field) and `evidence` (the anonymized text around it; never copy a raw value). Look for:
   > a real person, company, domain, id, phone, address, handle or secret left in the anonymized text; one real value
   > given different fakes, or two values given one; code, queries, schemas, numbers or dates changed when they
   > should not be; replacements that break grammar, URLs, JSON, arithmetic or consistency between a query, its
   > result and the answer; ordinary words replaced as names; missing or truncated tool results; rows too trivial,
   > broken or misleading to teach anything. Say "no defects" only after reading every part.

3. **Group findings into defect classes** and fix each class at its root in the pipeline. Never patch one row. Add
   a regression test per class with synthetic values of the same shape (never real values in tests).
4. **Rerun everything**, then gates, then a new sample with a new seed.
5. **Stop** when a round of 20 and then a round of 40 both come back with no serious findings. Report the number of
   rounds and the classes fixed in each.

Spot-check the delivered output in the same way, not just intermediate stages. When the data later seeds an RL
environment, spot-check the generated tasks in rounds of 20 and 40 too.

## Report

Give the user, in the response or PR (not a committed evidence file):

- rows in, rows out, drops by reason, and split sizes;
- gate results and thresholds, fidelity numbers, audit findings by severity;
- close-read rounds, defect classes found per round, and the final clean rounds;
- known limits of the source (capture loss, truncation, retention gaps) and what they mean for training.

## Pitfalls seen before

- The final pass over all messages ignored an exemption for documentation results and rewrote them.
- Single name words from a large person list ("Data", "San") were replaced everywhere, corrupting ordinary text.
- The entity reviewer labelled vendors (Shopify, PostHog) and standard fields (`utm_campaign`) as customer brands.
- Missed real values: newer TLDs, hosts inside code blocks, install ids on vendor hosts, 6–7 character UUID prefixes,
  UUIDs glued to "id", first names as email local parts, real names at `example.com` in sample code.
- Corruption: clock times in URLs scrambled to 75:04, prefixes like `RO#` scrambled, one id given two fakes when it
  touched markdown.
- A customer named after a month made every month name a leak.
- A rate-limited provider with no fallback stalled a rerun for an hour.
