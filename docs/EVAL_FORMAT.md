# Eval format

An eval file compares models on a fixed set of **cases**. Each case has one
or more **rollouts** per model. A training report shows an eval with the
`eval-*` tags in [TRAINING_REPORT_FORMAT.md](TRAINING_REPORT_FORMAT.md#evals).
`EvalSchema` in `product/packages/contracts/src/eval.ts` validates the file.

Name the file `<name>.eval.json` and attach it to a task version like any other
report file. Eval files can be read inline up to 32 MiB; other text files up
to 2 MiB.

## Shape

```jsonc
{
  "schema": "gradiated.eval/1",
  "id": "support-actions-2026-11",
  "title": "Support actions",
  "description": "…",
  "created_at": "2026-11-20T18:00:00Z",
  "grading": "A rollout passes when the saved order matches the expected changes.",

  "metrics": [{ "id": "correct", "name": "Passed", "kind": "pass", "grader_id": "order-diff" }],
  "primary_metric": "correct",
  "graders": [{ "id": "order-diff", "kind": "code", "name": "Saved order check" }],
  "interval_group_by": "Customer",

  "models": [
    {
      "id": "support-mini",
      "name": "support-mini",
      "description": "Custom model · built on Qwen3 8B",
      "kind": "model",
      "setup": { "system_prompt": "Standard prompt", "harness": "Support agent" }
    },
    { "id": "frontier", "name": "Frontier model", "description": "Off the shelf" }
  ],

  "cases": [
    {
      "id": "case-1",
      "title": "Refund a duplicate charge",
      "tags": { "Difficulty": "Hard", "Area": "Billing", "Customer": "Acme" },
      "messages": [{ "role": "user", "content": "…" }],
      "expected": [{ "id": "e1", "group": "Order 1042", "label": "Amount", "value": "$49.00" }]
    }
  ],

  "rollouts": [
    {
      "id": "case-1/support-mini/1",
      "case_id": "case-1",
      "model_id": "support-mini",
      "status": "completed",
      "scores": { "correct": false },
      "checks": [
        { "expected_id": "e1", "group": "Order 1042", "label": "Amount",
          "expected": "$49.00", "actual": "$98.00", "status": "wrong" }
      ],
      "messages": [],
      "usage": { "output_tokens": 3120 },
      "duration_ms": 48200
    }
  ]
}
```

## Fields

- **metrics**: what each rollout is scored on. `kind` is `pass` (true or
  false, summarised as a pass rate), `score` (a number between optional `min`
  and `max`, summarised as a mean; `pass_at` also makes it pass or fail) or
  `number` (a measurement such as cost). `higher_is_better` defaults to true.
  `tie_margin` sets how far apart two case means must be before one model
  counts as better; pass metrics count any difference.
- **primary_metric**: the metric the report shows unless a tag names another.
- **graders**: who or what scored the rollouts: `code`, `llm_judge` or `human`.
- **interval_group_by**: a tag key. The difference interval resamples whole
  groups with that tag value, for cases that are not independent, such as
  several cases from one project. Without it, cases are resampled.
- **models**: `kind` is `model`, `router` or `system`. `setup` records the
  system prompt, harness, sampling and notes, so readers see how each model
  was run. `version_id` links a model to a Gradiated task version.
- **cases**: `tags` is a flat map that becomes filters in the case list.
  `messages` is the conversation up to and including the request. `expected`
  lists what a correct rollout contains; `expected_output` holds any JSON
  answer instead.
- **rollouts**: `scores` maps metric IDs to a boolean, number or null.
  `status` is `completed`, `error` or `timeout`; rollouts that did not complete
  are left out of every score and counted separately. `checks` explain the
  score with `passed`, `wrong`, `missing` or `unexpected` items. `explanation`
  holds a judge's reasoning, `output` a final answer, and `messages` the trace.
  `served_by` and `usage.by_model` record which models a router or system used.
- **comparisons**: optional pairwise verdicts (`a`, `b`, `winner`) between two
  rollouts of one case.
- **metadata**: free-form on the eval, models, cases and rollouts. Reports
  ignore it; keep internal identifiers there.

Messages use the OpenAI Chat shapes from the trace `canonical` record in
[TRACES_PLAN.md](TRACES_PLAN.md), plus `reasoning` and `is_error`.
