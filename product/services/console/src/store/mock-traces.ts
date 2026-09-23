import type {
  AssistantReply,
  TraceGenerationRow,
  TraceMessage,
} from "@/store/fine-tuning-types";
import { HOUR_MS, costNanoUsd, fakeDigest, isoAt } from "@/store/mock-values";

type TemplateMessage =
  | Exclude<TraceMessage, { role: "assistant" }>
  | {
      role: "assistant";
      model: string;
      latency_ms: number;
      reply: AssistantReply;
    };

type TraceTemplate = readonly TemplateMessage[];

const system = (content: string): TemplateMessage => ({
  role: "system",
  content,
});

const user = (content: string): TemplateMessage => ({ role: "user", content });

const toolResult = (toolName: string, content: string): TemplateMessage => ({
  role: "tool",
  tool_name: toolName,
  content,
});

const assistant = (
  model: string,
  latencyMs: number,
  reply: AssistantReply,
): TemplateMessage => ({
  role: "assistant",
  model,
  latency_ms: latencyMs,
  reply,
});

const toolCall = (name: string, args: string): AssistantReply => ({
  tool_call: { name, arguments: args },
});

const SUPPORT_SYSTEM = system(
  "You are a support triage agent. Classify the ticket by calling classify_ticket, then write a short acknowledgement to the customer.",
);

const SUPPORT_TRIAGE_TEMPLATES: readonly TraceTemplate[] = [
  [
    SUPPORT_SYSTEM,
    user(
      "Hey, I upgraded to the Pro plan yesterday but I'm still being charged the old rate and the invoice shows a $0 line item for the upgrade. Can you fix the billing?",
    ),
    assistant(
      "gpt-4o",
      640,
      toolCall("classify_ticket", '{"category":"billing","priority":"high"}'),
    ),
    toolResult(
      "classify_ticket",
      '{"ok":true,"ticket_id":48213,"queue":"billing","sla_hours":4}',
    ),
    assistant("gpt-4o", 910, {
      content:
        "Thanks for flagging this — I've routed it to our billing team as high priority (ticket #48213). They'll correct the plan rate and reissue the invoice; you should hear back within 4 hours.",
    }),
  ],
  [
    SUPPORT_SYSTEM,
    user(
      "The export button on the dashboard just spins forever and never downloads the CSV. Happens every time on Chrome and Safari.",
    ),
    assistant(
      "gpt-4o",
      580,
      toolCall(
        "classify_ticket",
        '{"category":"bug_report","priority":"medium"}',
      ),
    ),
    toolResult(
      "classify_ticket",
      '{"ok":true,"ticket_id":48219,"queue":"engineering","sla_hours":24}',
    ),
    assistant("gpt-4o-mini", 410, {
      content:
        "Sorry about that — I've logged it as a bug for the dashboard team (ticket #48219). In the meantime, the CSV is also available from Reports → Export history if you need the data today.",
    }),
  ],
  [
    SUPPORT_SYSTEM,
    user("How do I add a second admin to my workspace?"),
    assistant(
      "gpt-4o",
      520,
      toolCall(
        "classify_ticket",
        '{"category":"account_access","priority":"low"}',
      ),
    ),
  ],
];

const SQL_SYSTEM = system(
  "You answer analytics questions by writing PostgreSQL and calling run_sql. Schema: orders(id, customer_id, status, total_cents, created_at), customers(id, email, plan).",
);

const SQL_GENERATION_TEMPLATES: readonly TraceTemplate[] = [
  [
    SQL_SYSTEM,
    user("What was revenue from completed orders in the last 30 days, by day?"),
    assistant(
      "claude-3-5-sonnet-20241022",
      1180,
      toolCall(
        "run_sql",
        "{\"query\":\"SELECT date_trunc('day', created_at) AS day, SUM(total) AS revenue FROM orders WHERE status = 'completed' AND created_at >= now() - interval '30 days' GROUP BY 1 ORDER BY 1\"}",
      ),
    ),
    toolResult(
      "run_sql",
      '{"error":"column \\"total\\" does not exist","hint":"Perhaps you meant total_cents"}',
    ),
    assistant(
      "claude-3-5-sonnet-20241022",
      1320,
      toolCall(
        "run_sql",
        "{\"query\":\"SELECT date_trunc('day', created_at) AS day, SUM(total_cents) / 100.0 AS revenue FROM orders WHERE status = 'completed' AND created_at >= now() - interval '30 days' GROUP BY 1 ORDER BY 1\"}",
      ),
    ),
    toolResult(
      "run_sql",
      '{"rows":30,"sample":[{"day":"2026-08-05","revenue":18420.50},{"day":"2026-08-06","revenue":17210.00}]}',
    ),
    assistant("claude-3-5-haiku-20241022", 540, {
      content:
        "Here's completed-order revenue per day for the last 30 days (30 rows). Revenue ranged from about $14.9k to $21.3k per day, averaging roughly $18.1k.",
    }),
  ],
  [
    SQL_SYSTEM,
    user("Emails of pro-plan customers with more than 3 orders this month?"),
    assistant(
      "claude-3-5-sonnet-20241022",
      1040,
      toolCall(
        "run_sql",
        "{\"query\":\"SELECT c.email FROM customers c JOIN orders o ON o.customer_id = c.id WHERE c.plan = 'pro' AND o.created_at >= date_trunc('month', now()) GROUP BY c.email HAVING COUNT(*) > 3\"}",
      ),
    ),
    toolResult(
      "run_sql",
      '{"rows":12,"sample":[{"email":"ana@acme.io"},{"email":"dev@northwind.co"}]}',
    ),
    assistant("claude-3-5-sonnet-20241022", 880, {
      content:
        "12 pro-plan customers placed more than 3 orders this month. First few: ana@acme.io, dev@northwind.co…",
    }),
  ],
];

const EMAIL_DRAFT_TEMPLATES: readonly TraceTemplate[] = [
  [
    system("Draft a short, friendly reply to the customer email below."),
    user(
      "Subject: Refund status?\n\nHi, I asked for a refund 5 days ago and haven't heard back. Order #48213. Can someone update me?",
    ),
    assistant("gpt-4o-mini", 720, {
      content:
        "Hi there, thanks for your patience and sorry for the delay. I checked order #48213 and your refund was approved — it should land in your account within 3–5 business days. Let me know if it hasn't shown up by then!",
    }),
  ],
];

interface TraceSeed {
  traceId: string;
  rows: TraceGenerationRow[];
  messages: TraceMessage[];
}

const generationId = (traceKey: string, turn: number) =>
  `gen_${fakeDigest(`${traceKey}-${turn}`).slice(0, 16)}`;

const buildTrace = (
  taskSlug: string,
  template: TraceTemplate,
  index: number,
  now: number,
): TraceSeed => {
  const traceKey = `${taskSlug}-${index}`;
  const turns = template.filter(
    (message) => message.role === "assistant",
  ).length;
  const traceId =
    turns > 1
      ? `tr_${fakeDigest(traceKey).slice(0, 12)}`
      : generationId(traceKey, 0);
  const errored = index % 11 === 3;
  let capturedAt = now - (index * 3 + 1) * HOUR_MS;

  const rows: TraceGenerationRow[] = [];
  const messages = template.map((message): TraceMessage => {
    if (message.role !== "assistant") return message;

    const turn = rows.length;
    const id = generationId(traceKey, turn);
    const inputTokens = 140 + turn * 90;
    const outputTokens = 18 + turn * 30;

    rows.push({
      id,
      trace_id: traceId,
      task: taskSlug,
      response_status: errored && turn === turns - 1 ? 429 : 200,
      captured_at: isoAt(capturedAt),
      model: message.model,
      latency_ms: message.latency_ms,
      input_tokens: inputTokens,
      output_tokens: outputTokens,
      cost_nano_usd: costNanoUsd(message.model, inputTokens, outputTokens),
    });
    capturedAt += message.latency_ms + 120;

    return { role: "assistant", generation_id: id, ...message.reply };
  });

  return { traceId, rows, messages };
};

const buildTraces = (
  taskSlug: string,
  templates: readonly TraceTemplate[],
  count: number,
  now: number,
): TraceSeed[] =>
  Array.from({ length: count }, (_, index) => {
    const template = templates[index % templates.length];

    return template ? [buildTrace(taskSlug, template, index, now)] : [];
  }).flat();

export const seedTraces = (
  now: number,
): {
  traces: TraceGenerationRow[];
  conversations: Record<string, TraceMessage[]>;
} => {
  const seeds = [
    ...buildTraces("support-triage", SUPPORT_TRIAGE_TEMPLATES, 18, now),
    ...buildTraces("sql-generation", SQL_GENERATION_TEMPLATES, 14, now),
    ...buildTraces("email-draft", EMAIL_DRAFT_TEMPLATES, 9, now),
  ];

  return {
    traces: seeds.flatMap((seed) => seed.rows),
    conversations: Object.fromEntries(
      seeds.map((seed) => [seed.traceId, seed.messages]),
    ),
  };
};
