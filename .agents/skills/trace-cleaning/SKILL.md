---
name: trace-cleaning
description: Anonymize and clean a customer's LLM traces into a high-quality dataset for SFT or RL environment synthesis, by reading random samples, building the cleaning code from what they show, and repeating fresh random close reads until they come back clean. Use when anonymizing, cleaning or quality-checking customer trace data for training.
---

# Trace cleaning

The output becomes training data and RL environments, so mistakes carry through to the model. A previous
environment was poor because its source data was badly cleaned. The goal is two things at once: no real personal or
customer data is left, and every row stays accurate, consistent and worth training on.

The code changes for every customer. The loop stays the same: **read samples, build, check, read fresh samples, fix,
repeat.**

## Data handling

- Raw traces, the fake-to-real map and review findings stay in the customer's folder (`~/dev/<customer>/`). Never
  commit them, and only send anonymized rows anywhere else.
- Every model call goes through OpenRouter with zero data retention:
  `{"zdr": true, "data_collection": "deny", "only": [<enabled ZDR providers>], "sort": "throughput"}`.
  Cheap models are enough, such as `deepseek/deepseek-v4.1-flash-1017`.

## 1. Understand the data

Read a random sample of traces from the chosen task before writing any code. Learn the record shape, what the
conversations are about, where personal and customer data appears (prose, tool arguments, tool results, tables),
what code or structured data must not change, and what was lost when the trace was captured.

Agree with the researcher what gets replaced, what stays, and which rows get dropped.

## 2. Build the first version

Draw 40 traces at random, spread across the task's range, and read them. Write the first anonymization and
cleaning code from what they show:

- **Clean:** drop empty, trivial or broken conversations, and merge duplicates.
- **Anonymize:** replace each real name, company, email, id, address and secret with a realistic fake, the same fake
  everywhere in the trace. A cheap model tags names and companies in prose; patterns catch emails, URLs, ids and
  phones everywhere.
- **Protect code:** never change code, queries, schemas or field names.
- **Final check:** drop any row where a known real value or a hard pattern survives.

Run it on the whole dataset, and count rows in, rows out and drops by reason.

## 3. Check

- **Leak check:** search the output for every real value in the map.
- **Audit:** a different cheap model looks for real data in a sample of the output.
- **Code check:** compare code in the output with the raw traces. It should be unchanged.

Passing these is not enough. Close reads find what they miss.

## 4. Close-read, fix, repeat

1. Draw a fresh random sample of 20 traces that no earlier round has read.
2. Have a cheap ZDR model compare each raw trace with its anonymized version. It reports real data left behind,
   inconsistent fakes, broken code or numbers, and rows too poor to train on.
3. Fix each kind of defect in the code, not in single rows, and add a test with made-up values.
4. Rerun everything and draw a new sample.

Stop when a round of 20 and then a round of 40 find nothing serious. Report the rounds and what each one fixed.
