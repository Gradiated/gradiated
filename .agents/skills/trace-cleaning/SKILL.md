---
name: trace-cleaning
description: Anonymize and clean a customer's LLM traces into a high-quality dataset for SFT or RL environment synthesis, by reading random samples, building the cleaning code from what they show, and repeating fresh random close reads until they come back clean. Use when anonymizing, cleaning or quality-checking customer trace data for training.
---

# Trace cleaning

The goal of a cleaned trace dataset is production signal for building a high-fidelity RL environment: what end
users actually ask for, the state they work in, the tools the agent uses, and how conversations succeed or fail.
Both successful and failed traces matter. A previous environment was poor because its source data was badly
cleaned, so mistakes here carry through to the model. Two things must hold at once: no real personal or customer
data is left, and every trace stays accurate, consistent and true to the task it came from.

The code changes for every customer. The loop stays the same: **read samples, build, check, read fresh samples, fix, repeat.**

## Keep the task intact

Anonymizing can quietly change what a trace means, and then any task built from it is wrong. Every real value maps
to exactly one fake, and every fake to exactly one real value, across the whole trace:

- two different customers must never end up with the same email, name or id;
- one entity must never appear as two different things, for example "Acme" in the question and "Globex" in the
  tool result, or a full name in one message and a different fake surname in another;
- relationships must survive: a query, its result and the answer that cites it still agree, counts and totals still
  add up, and ids, dates and references still point at the right things.

If a trace cannot be anonymized without changing its task, drop it.

## Data handling

- Raw traces, the fake-to-real map and review findings stay in the customer's folder (`~/dev/<customer>/`). Never
  commit them, and only send anonymized rows anywhere else.
- Every model call goes through OpenRouter with zero data retention:
  `{"zdr": true, "data_collection": "deny", "only": [<enabled ZDR providers>], "sort": "throughput"}`.
  Cheap models are enough, such as `deepseek/deepseek-v4.1-flash-1017`.
  Read `OPENROUTER_API_KEY` from the AWS secret `gradiated/dev/fde`, which holds the shared forward-deployed
  engineering keys, and never print it.

## 1. Convert to one format

Convert every customer's traces to the same format before cleaning, so the cleaning code and the checks only handle
one shape. Use OpenAI chat messages with tool calls and a list of tool definitions, one JSON line per conversation:

```json
{"id": "...", "tools": [{"type": "function", "function": {"name": "...", "description": "...", "parameters": {}}}],
 "messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."},
              {"role": "assistant", "content": "...", "reasoning_content": "...", "tool_calls": [...]},
              {"role": "tool", "tool_call_id": "...", "content": "..."}],
 "metadata": {"task": "...", "conversation_id": "...", "model": "...", "end_user": "...", "capture_notes": []}}
```

Chat templates, TRL, prime-rl and verifiers all read this format directly or after a mechanical split.

The model must be trained on what it will see when served inside the customer's harness. The conversion must not
change that:

- Rebuild anything the capture dropped from the customer's code at the commit that was live, such as the system
  prompt and its dynamic blocks.
- Take tool definitions, retry messages and other harness text from the harness itself, not from hand-written copies.
- Keep images, documents and other parts the harness sends.
- Move capture artifacts, such as truncation or "messages dropped" markers, out of the text and into `capture_notes`.

Check the conversion by rendering a sample through the harness's own code for an OpenAI-compatible model and diffing
it against the converted rows.

## 2. Understand the data

Read a random sample of traces from the chosen task before writing any code. Learn the record shape, what the
conversations are about, where personal and customer data appears (prose, tool arguments, tool results, tables),
what code or structured data must not change, and what was lost when the trace was captured.

Agree with the researcher what gets replaced, what stays, and which rows get dropped. Always replace hard PII:
people, emails, phones, companies other than manufacturers, street addresses and account, customer, job and PO
numbers. Context names that are not personal, such as project names, can be kept when replacing them would make
traces inconsistent; at Bild they caused most remaining defects, and keeping them was the right call.

## 3. Build the first version

Draw 40 traces at random, spread across the task's range, and read them. Write the first anonymization and
cleaning code from what they show:

- **Clean:** drop empty, trivial or broken conversations, and merge duplicates. Drop traces not related to the task.
  Filter on signal, not on completeness. When traces seed an RL environment rather than being trained on directly,
  keep traces with capture gaps (missing images, dropped history, truncated results) and tag the gaps, since the
  request, the tools used and the outcome are still useful.
- **Anonymize:** replace each real name, company, email, id, address and secret with a fake of the same kind. A
  person's name becomes another plausible person's name, an organization another organization name, an address
  another address, and an id an id of the same shape. A cheap model tags names and companies in prose; patterns
  catch emails, URLs, ids, phones, licence numbers and user names in file paths everywhere.
- **Replace names word by word:** give each identifying word one fake word used everywhere in the conversation, and
  keep generic words. Every form of a name then changes the same way ("Quillmere Tower", `QUILLMERE_TWR.pdf`),
  where whole-name fakes needed clustering of forms and kept failing. A name made only of generic words gets one
  whole fake.
- **Decide what is generic from the data:** a word used by many different end users across the dataset (door,
  floor, plans) is generic; a dictionary is the wrong test. Build the manufacturer list from the customer's code
  and from manufacturer fields in tool results, and never replace those names.
- **Keep fakes stable and varied:** the same real value always gets the same fake, derived from a seeded hash, so
  it stays consistent across all traces. Draw fakes from a large pool so few are reused across the dataset, and never
  give two real values the same fake within a trace.
- **Protect code and structure:** never change code, queries, schemas, JSON field names, domain codes (spec
  sections, state codes) or two-letter acronyms. Change a number or code only inside the name it belongs to, so a
  house number never changes a coordinate elsewhere.
- **Final check:** drop any row where a known real value or a hard pattern survives.

Run it on the sample, and count rows in, rows out and drops by reason.

## 4. Check

- **Leak check:** search the output for every real value in the map.
- **Audit:** a different cheap model looks for real data in a sample of the output.
- **Code check:** compare code in the output with the raw traces. It should be unchanged.
- **Consistency check:** the fake-to-real map is one-to-one within each trace. No two reals share a fake.

Passing these is not enough. Close reads find what they miss.

## 5. Close-read, fix, repeat

Iterate on samples, not the whole dataset. Each round takes a minute and costs cents:

1. Draw a fresh random sample of 20 traces that no earlier round has read, from traces that contain values to
   replace, and anonymize only those.
2. Have a cheap ZDR model compare each raw trace with its anonymized version. It reports real data left behind,
   anything that changes the task (merged or split entities, broken references, code or numbers that no longer
   agree), and rows too poor to train on.
3. Verify every serious finding with a stronger ZDR model given the policy as an explicit checklist: what is
   replaced, what is kept, and what counts as serious. Cheap reviewers often report the policy itself as a defect;
   count only confirmed findings.
4. Fix each kind of defect in the code, not in single rows, and add a test with made-up values.
5. Draw a new sample and repeat.

Stop when rounds of 20 and then 40 have few confirmed serious defects. When several rounds do not move the rate,
change the design or the policy instead of adding rules, and measure before paying for a stronger tagger (at Bild a
10x more expensive tagger gave the same rate). Then run the whole dataset once, and measure it on a fresh sample of
about 100. Report the rounds and what each one fixed.

## 6. Tag and filter

Tag every trace for the environment: deterministic tags from the messages (decisions per step, tools used, whether
the request was captured) and judged tags from a cheap ZDR model (task type, completion state, failure mode, how a
rollout could be scored, signal value). Drop only duplicates and traces that are not meaningful. Keep failures,
capture gaps and low-signal traces, flagged, so each experiment can choose its own subset.

## Running the pipeline

- Cache every model call by its input, so a rerun only pays for text that changed.
- Write results as each trace finishes, cap every retry loop and request timeout, and print progress, so one slow
  request cannot stall a run.
- Run long jobs as one chain that writes a log per stage. Never start a second copy that writes the same files, and
  never pipe a long job through `head`.
- Log the cost of every request with the customer, stage and run, and send it to PostHog (see the
  customer-post-training workflow).
