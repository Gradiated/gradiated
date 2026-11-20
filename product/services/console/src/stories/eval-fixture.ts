import { EVAL_SCHEMA, type Eval } from "@gradiated/contracts";

const tickets = [
  ["Refund a duplicate charge", "Billing", "Hard", "refund"],
  ["Update the shipping address", "Shipping", "Medium", "update_address"],
  ["Cancel an annual plan", "Billing", "Hard", "cancel_plan"],
  ["Resend a lost invoice", "Billing", "Medium", "send_invoice"],
  ["Track a delayed parcel", "Shipping", "Medium", "track_parcel"],
  ["Split a shipment in two", "Shipping", "Hard", "split_shipment"],
] as const;

const outcomes: Record<string, boolean[]> = {
  "case-1/support-mini": [true, true, true],
  "case-1/frontier": [false, true, false],
  "case-3/support-mini": [false, false, true],
  "case-3/frontier": [true, true, true],
  "case-6/support-mini": [true, false, true],
  "case-6/frontier": [false, false, false],
};

const rollout = (caseIndex: number, model: string, attempt: number) => {
  const [title, , , tool] = tickets[caseIndex]!;
  const passed = outcomes[`case-${caseIndex + 1}/${model}`]?.[attempt] ?? true;
  const call = `call_${caseIndex}_${model}_${attempt}`;

  return {
    id: `case-${caseIndex + 1}/${model}/${attempt + 1}`,
    case_id: `case-${caseIndex + 1}`,
    model_id: model,
    status: "completed" as const,
    scores: { correct: passed },
    checks: [
      {
        group: "Order 1042",
        label: "Status",
        expected: "Done",
        actual: "Done",
        status: "passed" as const,
      },
      ...(passed
        ? []
        : [
            {
              group: "Order 1042",
              label: "Amount",
              expected: "$49.00",
              actual: "$98.00",
              status: "wrong" as const,
            },
            {
              group: "Order 1043",
              label: "Note",
              actual: "Customer called",
              status: "unexpected" as const,
            },
          ]),
    ],
    messages: [
      {
        role: "assistant" as const,
        content: null,
        reasoning: `The customer wants to ${title.toLowerCase()}. Look up the order first.`,
        tool_calls: [
          {
            id: `${call}_a`,
            type: "function" as const,
            function: { name: "get_order", arguments: '{"order_id":"1042"}' },
          },
        ],
      },
      {
        role: "tool" as const,
        tool_call_id: `${call}_a`,
        content: '{"id":"1042","status":"open","amount":"$49.00"}',
      },
      {
        role: "assistant" as const,
        content: null,
        tool_calls: [
          {
            id: `${call}_b`,
            type: "function" as const,
            function: { name: tool, arguments: '{"order_id":"1042"}' },
          },
        ],
      },
      {
        role: "tool" as const,
        tool_call_id: `${call}_b`,
        content: '{"ok":true}',
      },
      {
        role: "assistant" as const,
        content: `Done: ${title.toLowerCase()} for order 1042.`,
      },
    ],
    usage: { output_tokens: 600 + caseIndex * 40 + attempt * 15 },
    duration_ms: 9000 + attempt * 1200,
  };
};

export const sampleEval: Eval = {
  schema: EVAL_SCHEMA,
  id: "support-actions-2026-11",
  title: "Support actions",
  created_at: "2026-11-20T12:00:00Z",
  grading:
    "A rollout passes when the saved order matches the expected changes.",
  metrics: [
    { id: "correct", name: "Passed", kind: "pass", higher_is_better: true },
  ],
  primary_metric: "correct",
  graders: [],
  models: [
    {
      id: "support-mini",
      name: "support-mini",
      kind: "model",
      description: "Custom model · built on Qwen3 8B",
    },
    {
      id: "frontier",
      name: "Frontier model",
      kind: "model",
      description: "Off the shelf",
    },
  ],
  cases: tickets.map(([title, area, difficulty], index) => ({
    id: `case-${index + 1}`,
    title,
    tags: { Area: area, Difficulty: difficulty },
    messages: [
      { role: "user", content: `Please ${title.toLowerCase()} on order 1042.` },
    ],
    expected: [{ group: "Order 1042", label: "Status", value: "Done" }],
  })),
  rollouts: tickets.flatMap((_, index) =>
    ["support-mini", "frontier"].flatMap((model) =>
      [0, 1, 2].map((attempt) => rollout(index, model, attempt)),
    ),
  ),
  comparisons: [],
};

export const evalReport = `---
title: Support actions, round one
---

## Results

{% eval-summary eval="support.eval.json" /%}

{% columns %}
{% eval-breakdown eval="support.eval.json" by="Difficulty" title="Pass rate by difficulty" /%}
{% eval-head-to-head eval="support.eval.json" by="Difficulty" title="Head to head, case by case" /%}
{% /columns %}

{% eval-case-grid eval="support.eval.json" by="Area" title="Every case" /%}

{% columns %}
{% eval-examples eval="support.eval.json" where="better" title="Where support-mini did better" /%}
{% eval-examples eval="support.eval.json" where="worse" title="Where the frontier model did better" /%}
{% /columns %}

## Cases

{% eval-cases eval="support.eval.json" /%}
`;

export const evalReportData = {
  "support.eval.json": JSON.stringify(sampleEval),
};
