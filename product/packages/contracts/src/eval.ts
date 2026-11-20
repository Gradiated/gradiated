import { z } from "@hono/zod-openapi";

export const EVAL_SCHEMA = "gradiated.eval/1";
export const EVAL_FILE_PATTERN = /\.eval\.json$/i;
export const MAX_EVAL_FILE_CONTENT_BYTES = 32 * 1024 * 1024;

const Id = z.string().trim().min(1).max(200);
const Text = z.string().max(20_000);
const Metadata = z.record(z.string(), z.unknown());

const EvalToolCallSchema = z.object({
  id: z.string(),
  type: z.literal("function").default("function"),
  function: z.object({ name: z.string(), arguments: z.string() }),
});

export const EvalMessageSchema = z.object({
  role: z.enum(["system", "user", "assistant", "tool"]),
  content: z.string().nullable().default(null),
  reasoning: z.string().optional(),
  tool_calls: z.array(EvalToolCallSchema).optional(),
  tool_call_id: z.string().optional(),
  name: z.string().optional(),
  is_error: z.boolean().optional(),
});

export const EvalMetricSchema = z.strictObject({
  id: Id,
  name: z.string().trim().min(1).max(200),
  kind: z.enum(["pass", "score", "number"]),
  description: Text.optional(),
  min: z.number().finite().optional(),
  max: z.number().finite().optional(),
  unit: z.string().max(40).optional(),
  higher_is_better: z.boolean().default(true),
  pass_at: z.number().finite().optional(),
  tie_margin: z.number().nonnegative().finite().optional(),
  grader_id: Id.optional(),
});

export const EvalGraderSchema = z.strictObject({
  id: Id,
  kind: z.enum(["code", "llm_judge", "human"]),
  name: z.string().trim().min(1).max(200),
  model: z.string().max(200).optional(),
  description: Text.optional(),
});

export const EvalModelSchema = z.strictObject({
  id: Id,
  name: z.string().trim().min(1).max(200),
  description: z.string().max(500).optional(),
  kind: z.enum(["model", "router", "system"]).default("model"),
  provider: z.string().max(80).optional(),
  base_model: z.string().max(200).optional(),
  version_id: z.string().uuid().optional(),
  setup: z
    .strictObject({
      system_prompt: z.string().max(500).optional(),
      harness: z.string().max(200).optional(),
      sampling: z
        .record(z.string(), z.union([z.number(), z.string(), z.boolean()]))
        .optional(),
      notes: Text.optional(),
    })
    .optional(),
  metadata: Metadata.optional(),
});

export const EvalExpectedSchema = z.strictObject({
  id: Id.optional(),
  group: z.string().max(500).optional(),
  label: z.string().max(500),
  value: z.string().max(5000),
});

export const EvalCaseSchema = z.strictObject({
  id: Id,
  title: z.string().trim().min(1).max(300),
  description: Text.optional(),
  tags: z.record(z.string().min(1).max(80), z.string().max(200)).default({}),
  messages: z.array(EvalMessageSchema).default([]),
  expected: z.array(EvalExpectedSchema).default([]),
  expected_output: z.unknown().optional(),
  metadata: Metadata.optional(),
});

export const EvalCheckSchema = z.strictObject({
  expected_id: Id.optional(),
  group: z.string().max(500).optional(),
  label: z.string().max(500),
  expected: z.string().max(5000).optional(),
  actual: z.string().max(5000).optional(),
  status: z.enum(["passed", "wrong", "missing", "unexpected"]),
  note: z.string().max(2000).optional(),
});

const Tokens = z.number().int().nonnegative();

export const EvalRolloutSchema = z.strictObject({
  id: Id,
  case_id: Id,
  model_id: Id,
  status: z.enum(["completed", "error", "timeout"]).default("completed"),
  error: z.string().max(5000).optional(),
  scores: z.record(Id, z.union([z.boolean(), z.number().finite(), z.null()])),
  checks: z.array(EvalCheckSchema).default([]),
  explanation: Text.optional(),
  output: z.unknown().optional(),
  messages: z.array(EvalMessageSchema).default([]),
  usage: z
    .strictObject({
      input_tokens: Tokens.optional(),
      output_tokens: Tokens.optional(),
      reasoning_tokens: Tokens.optional(),
      cost_usd: z.number().nonnegative().finite().optional(),
      by_model: z
        .array(
          z.strictObject({
            model: z.string().max(200),
            input_tokens: Tokens.optional(),
            output_tokens: Tokens.optional(),
            cost_usd: z.number().nonnegative().finite().optional(),
          }),
        )
        .optional(),
    })
    .optional(),
  served_by: z
    .array(
      z.strictObject({
        model: z.string().max(200),
        share: z.number().min(0).max(1),
      }),
    )
    .optional(),
  duration_ms: z.number().nonnegative().finite().optional(),
  metadata: Metadata.optional(),
});

export const EvalComparisonSchema = z.strictObject({
  case_id: Id,
  a: Id,
  b: Id,
  winner: z.enum(["a", "b", "tie"]),
  grader_id: Id.optional(),
  explanation: Text.optional(),
});

const unique = <T>(items: T[], key: (item: T) => string) =>
  new Set(items.map(key)).size === items.length;

export const EvalSchema = z
  .strictObject({
    schema: z.literal(EVAL_SCHEMA),
    id: Id,
    title: z.string().trim().min(1).max(300),
    description: Text.optional(),
    created_at: z.string().datetime({ offset: true }),
    grading: Text.optional(),
    metrics: z.array(EvalMetricSchema).min(1),
    primary_metric: Id,
    graders: z.array(EvalGraderSchema).default([]),
    interval_group_by: z.string().max(80).optional(),
    models: z.array(EvalModelSchema).min(2),
    cases: z.array(EvalCaseSchema).min(1),
    rollouts: z.array(EvalRolloutSchema),
    comparisons: z.array(EvalComparisonSchema).default([]),
    metadata: Metadata.optional(),
  })
  .superRefine((value, context) => {
    const issue = (message: string, path: (string | number)[]) =>
      context.addIssue({ code: z.ZodIssueCode.custom, message, path });
    const metrics = new Map(
      value.metrics.map((metric) => [metric.id, metric.kind]),
    );
    const models = new Set(value.models.map((model) => model.id));
    const cases = new Set(value.cases.map((item) => item.id));
    const rollouts = new Map(
      value.rollouts.map((rollout) => [rollout.id, rollout.case_id]),
    );

    if (!unique(value.metrics, (metric) => metric.id))
      issue("Metric IDs must be unique.", ["metrics"]);
    if (!unique(value.models, (model) => model.id))
      issue("Model IDs must be unique.", ["models"]);
    if (!unique(value.cases, (item) => item.id))
      issue("Case IDs must be unique.", ["cases"]);
    if (!unique(value.rollouts, (rollout) => rollout.id))
      issue("Rollout IDs must be unique.", ["rollouts"]);
    if (!metrics.has(value.primary_metric))
      issue("primary_metric must name a metric.", ["primary_metric"]);

    value.metrics.forEach((metric, index) => {
      if (metric.kind === "pass" && !metric.higher_is_better)
        issue("Pass metrics count passing as better.", [
          "metrics",
          index,
          "higher_is_better",
        ]);
    });

    const graders = new Set(value.graders.map((grader) => grader.id));
    if (graders.size !== value.graders.length)
      issue("Grader IDs must be unique.", ["graders"]);
    for (const [path, list] of [
      ["metrics", value.metrics],
      ["comparisons", value.comparisons],
    ] as const)
      list.forEach((item, index) => {
        if (item.grader_id !== undefined && !graders.has(item.grader_id))
          issue(`Unknown grader ${item.grader_id}.`, [
            path,
            index,
            "grader_id",
          ]);
      });

    const groupBy = value.interval_group_by;
    if (
      groupBy !== undefined &&
      !value.cases.some((item) => item.tags[groupBy] !== undefined)
    )
      issue("interval_group_by must name a case tag.", ["interval_group_by"]);

    value.rollouts.forEach((rollout, index) => {
      if (!cases.has(rollout.case_id))
        issue(`Unknown case ${rollout.case_id}.`, [
          "rollouts",
          index,
          "case_id",
        ]);
      if (!models.has(rollout.model_id))
        issue(`Unknown model ${rollout.model_id}.`, [
          "rollouts",
          index,
          "model_id",
        ]);
      for (const [metric, score] of Object.entries(rollout.scores)) {
        const kind = metrics.get(metric);
        const path = ["rollouts", index, "scores", metric];
        if (!kind) issue(`Unknown metric ${metric}.`, path);
        else if (
          score !== null &&
          (kind === "pass") !== (typeof score === "boolean")
        )
          issue(
            kind === "pass"
              ? `${metric} scores must be true, false or null.`
              : `${metric} scores must be numbers or null.`,
            path,
          );
      }
    });

    value.comparisons.forEach((comparison, index) => {
      if (
        rollouts.get(comparison.a) !== comparison.case_id ||
        rollouts.get(comparison.b) !== comparison.case_id
      )
        issue("Comparisons must name two rollouts of their case.", [
          "comparisons",
          index,
        ]);
    });
  });

export type Eval = z.infer<typeof EvalSchema>;
export type EvalCase = Eval["cases"][number];
export type EvalRollout = Eval["rollouts"][number];
export type EvalModel = Eval["models"][number];
export type EvalMetric = Eval["metrics"][number];
export type EvalCheck = EvalRollout["checks"][number];
export type EvalMessage = z.infer<typeof EvalMessageSchema>;
