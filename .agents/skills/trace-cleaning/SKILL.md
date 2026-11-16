---
name: trace-cleaning
description: Anonymize and clean a customer's LLM traces into a high-quality dataset for SFT or RL environment synthesis, by reading random samples, building the cleaning code from what they show, and repeating fresh random close reads until they come back clean. Use when anonymizing, cleaning or quality-checking customer trace data for training.
---

# Trace cleaning

The output becomes training data and RL environments, so mistakes carry through to the model. A previous
environment was poor because its source data was badly cleaned. The goal is two things at once: no real personal or customer data is left, and every row stays accurate, consistent and worth training on.

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

Agree with the researcher what gets replaced, what stays, and which rows get dropped.

## 3. Build the first version

Draw 40 traces at random, spread across the task's range, and read them. Write the first anonymization and
cleaning code from what they show:

- **Clean:** drop empty, trivial or broken conversations, and merge duplicates. Drop traces not related to the task.
- **Anonymize:** replace each real name, company, email, id, address and secret with a fake of the same kind. A
  person's name becomes another plausible person's name, an organization another organization name, an address
  another address, and an id an id of the same shape. A cheap model tags names and companies in prose; patterns
  catch emails, URLs, ids and phones everywhere.
- **Keep fakes stable and varied:** the same real value always gets the same fake, derived from a seeded hash, so
  it stays consistent across all traces. Draw fakes from a large pool so few are reused across the dataset, and never
  give two real values the same fake within a trace.
- **Protect code:** never change code, queries, schemas or field names.
- **Final check:** drop any row where a known real value or a hard pattern survives.

Run it on the whole dataset, and count rows in, rows out and drops by reason.

## 4. Check

- **Leak check:** search the output for every real value in the map.
- **Audit:** a different cheap model looks for real data in a sample of the output.
- **Code check:** compare code in the output with the raw traces. It should be unchanged.
- **Consistency check:** the fake-to-real map is one-to-one within each trace. No two reals share a fake.

Passing these is not enough. Close reads find what they miss.

## 5. Close-read, fix, repeat

1. Draw a fresh random sample of 20 traces that no earlier round has read.
2. Have a cheap ZDR model compare each raw trace with its anonymized version. It reports real data left behind,
   anything that changes the task (merged or split entities, broken references, code or numbers that no longer
   agree), and rows too poor to train on.
3. Fix each kind of defect in the code, not in single rows, and add a test with made-up values.
4. Rerun everything and draw a new sample.

Stop when a round of 20 and then a round of 40 find nothing serious. Report the rounds and what each one fixed.
