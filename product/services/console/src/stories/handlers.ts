import { MODEL_CATALOG } from "@gradiated/contracts/model-catalog";
import { http, HttpResponse } from "msw";

import type { components } from "@/api/schema";
import type { GenerationLog, UsageSummary } from "@/api/queries";

const organizationId = "00000000-0000-4000-8000-000000000001";
const workspaceId = "00000000-0000-4000-8000-000000000002";
const createdAt = "2026-09-01T12:00:00Z";
const modelId = "gradiated/example-model";
const list = <T>(...data: T[]) => ({ data, next_cursor: null });

const organization = {
  id: organizationId,
  name: "Example organization",
  status: "active",
  role: "owner",
  default_workspace_id: workspaceId,
  auto_join_domain: null,
  onboarding_completed: true,
} satisfies components["schemas"]["CurrentOrganization"];

const user = {
  id: "storybook-user",
  name: "Alex Example",
  email: "alex@example.invalid",
  email_verified: true,
  company_email_domain: null,
  image_url: null,
  created_at: createdAt,
  organizations: [organization],
} satisfies components["schemas"]["CurrentUser"];

type CurrentUser = components["schemas"]["CurrentUser"];
type CurrentOrganization = CurrentUser["organizations"][number];

const acmeUser = (
  email: string,
  companyEmailDomain: string | null,
  patch: Partial<CurrentOrganization>,
): CurrentUser => ({
  ...user,
  email,
  company_email_domain: companyEmailDomain,
  organizations: [{ ...organization, ...patch }],
});

export const onboardingCompanyUser = acmeUser("alex@acme.com", "acme.com", {
  name: "Personal",
  onboarding_completed: false,
});
export const onboardingPersonalUser = acmeUser("alex.example@gmail.com", null, {
  name: "Personal",
  onboarding_completed: false,
});
export const acmeOwner = acmeUser("alex@acme.com", "acme.com", {
  name: "Acme",
  auto_join_domain: "acme.com",
});

const workspace = {
  id: workspaceId,
  organization_id: organizationId,
  name: "Production",
  is_default: true,
  trace_capture_enabled: true,
  trace_retention_days: 90,
  default_judge_model: "Qwen/Qwen3-0.6B",
  archived_at: null,
  created_at: createdAt,
  updated_at: createdAt,
} satisfies components["schemas"]["Workspace"];

const model = {
  id: modelId,
  name: "Example Model",
  status: "available",
  created_at: createdAt,
  updated_at: createdAt,
  properties: {
    schema_version: 1,
    type: "chat",
    description: "A synthetic model for exploring the console in Storybook.",
    released_at: createdAt,
    hugging_face_id: null,
    quantization: "fp8",
    tokenizer: null,
    input_modalities: [
      {
        type: "text",
        supported_inputs: {
          max_context_length: { value: 131072, unit: "token" },
          max_prompt_length: { value: 114688, unit: "token" },
        },
        pricing: [{ type: "prompt", unit: "token", cost: 300 }],
      },
    ],
    output_modalities: [
      {
        type: "text",
        max_length: { value: 16384, unit: "token" },
        default_length: { value: 4096, unit: "token" },
        streaming: true,
        supported_parameters: {},
        pricing: [{ type: "completion", unit: "token", cost: 900 }],
      },
    ],
    passthrough_parameters: {},
    deprecation_date: null,
  },
} satisfies components["schemas"]["Model"];

const apiKey = {
  id: "storybook-key",
  organization_id: organizationId,
  workspace_id: workspaceId,
  name: "Production application",
  expires_at: null,
  revoked_at: null,
  created_by: user.id,
  created_at: createdAt,
  updated_at: createdAt,
} satisfies components["schemas"]["ApiKey"];

const task = {
  id: "00000000-0000-4000-8000-000000000003",
  name: "support-assistant",
  base_model_id: "Qwen/Qwen3-0.6B",
  comparison_model_id: "Qwen/Qwen3-0.6B",
  production_version_id: null,
  judge_model_id: "Qwen/Qwen3-0.6B",
  training_schedule: null,
} satisfies components["schemas"]["Task"];

const evaluation = {
  judging_method: "randomized_single",
  holdout_groups: 100,
  holdout_examples: 100,
  comparison_model_id: task.comparison_model_id,
  judge_model_id: task.judge_model_id,
  vs_comparison: {
    comparator_model_id: task.comparison_model_id,
    win: 72,
    tie: 18,
    loss: 10,
    unresolved: 0,
  },
  cost_per_request_nano_usd: { fine_tuned: 300000, comparison: 600000 },
  output_tokens_per_second: { fine_tuned: 80, comparison: 45 },
  error_rate: 0,
} satisfies NonNullable<components["schemas"]["RunEvaluation"]>;

const run = {
  id: "storybook-run",
  task: task.name,
  trigger: "manual",
  requested_by: user.id,
  stage: "succeeded",
  base_model_id: task.base_model_id,
  input_cutoff: createdAt,
  dataset: {
    eligible_examples: 1200,
    duplicates_removed: 0,
    train: 1000,
    validation: 100,
    test: 100,
  },
  evaluation,
  version_id: "storybook-version",
  cancel_requested_at: null,
  created_at: createdAt,
  finished_at: "2026-09-01T12:20:00Z",
} satisfies components["schemas"]["TrainingRun"];

const version = {
  id: run.version_id,
  name: "support-assistant-v1",
  task: task.name,
  training_run_id: run.id,
  base_model_id: task.base_model_id,
  adapter: {
    format: "peft_lora",
    artifact_uri: "s3://example.invalid/adapter",
    sha256: "0".repeat(64),
    size_bytes: 10485760,
    rank: 16,
  },
  status: "available",
  is_production: true,
  created_at: createdAt,
} satisfies components["schemas"]["TaskVersion"];

const trace = {
  generation_id: "storybook-trace-generation",
  trace_id: "storybook-trace",
  task: task.name,
  model: task.base_model_id,
  source: "relay",
  trainable: true,
  started_at: createdAt,
  completed_at: "2026-09-01T12:00:02Z",
  status: 200,
  outcome: "complete",
  usage: { input_tokens: 1200, output_tokens: 400 },
  content_ref: "storybook-content",
} satisfies components["schemas"]["TraceGeneration"];

const traceContent = {
  generation_id: trace.generation_id,
  raw: {
    request: {
      model: task.base_model_id,
      messages: [{ role: "user", content: "How can I reset my password?" }],
    },
    response: {
      choices: [
        {
          message: {
            role: "assistant",
            content:
              "Select Forgot password on the sign-in page. We will email you a link to reset it.",
          },
          finish_reason: "stop",
        },
      ],
      usage: trace.usage,
    },
  },
} satisfies components["schemas"]["TraceContent"];

const evaluationResults = [
  {
    id: "storybook-evaluation",
    group: "password-reset",
    fine_tuned: {
      text: "Select Forgot password on the sign-in page. We will email you a link to reset it.",
      tokens: 22,
      seconds: 0.28,
      cost_nano_usd: 300000,
    },
    comparison: {
      text: "Contact support for help resetting your password.",
      tokens: 9,
      seconds: 0.2,
      cost_nano_usd: 600000,
    },
    judgment: "A",
    fine_tuned_first: true,
  },
] satisfies components["schemas"]["EvaluationResults"];

const events = [
  {
    id: 1,
    at: createdAt,
    source: "api",
    attempt: 1,
    payload: {
      type: "run_created",
      trigger: "manual",
      requested_by: user.id,
      base_model_id: task.base_model_id,
    },
  },
  ...(
    [
      "building_dataset",
      "awaiting_capacity",
      "training",
      "verifying",
      "publishing",
      "evaluating",
      "succeeded",
    ] as const
  ).map((stage, index) => ({
    id: index + 2,
    at: new Date(
      new Date(createdAt).getTime() + (index + 1) * 120000,
    ).toISOString(),
    source: "worker",
    attempt: 1,
    payload: { type: "stage_entered" as const, stage },
  })),
] satisfies components["schemas"]["TrainingRunEvent"][];

const generation = {
  id: "storybook-generation",
  external_id: null,
  model_id: "z-ai/glm-5.3-flash",
  status: "succeeded",
  streamed: true,
  charge: "720000",
  input_tokens: 1200,
  cached_input_tokens: 0,
  cache_write_tokens: 0,
  output_tokens: 400,
  reasoning_tokens: 0,
  finish_reason: "stop",
  error_code: null,
  usable_output_delivered: true,
  cancellation_owner: null,
  received_at: "2026-10-01T15:30:00Z",
  started_at: "2026-10-01T15:30:00Z",
  first_token_at: "2026-10-01T15:30:00.120Z",
  completed_at: "2026-10-01T15:30:02Z",
} satisfies GenerationLog;

const billing = {
  organization_id: organizationId,
  mode: "prepaid",
  balance: "42500000000",
  created_at: createdAt,
  updated_at: createdAt,
} satisfies components["schemas"]["BillingAccount"];

const transaction = {
  id: "storybook-topup",
  organization_id: organizationId,
  type: "topup",
  amount: "50000000000",
  balance_after: "50000000000",
  source_type: "stripe_checkout_session",
  period_start: null,
  period_end: null,
  generation_count: null,
  created_at: createdAt,
} satisfies components["schemas"]["BalanceTransaction"];

const usage = (from: string): UsageSummary => ({
  charge: "7500000000",
  input_tokens: "18000000",
  output_tokens: "4200000",
  generation_count: "12000",
  succeeded_count: "11940",
  daily: Array.from({ length: 30 }, (_, index) => ({
    date: new Date(new Date(from).getTime() + index * 86400000)
      .toISOString()
      .slice(0, 10),
    charge: String(((index % 7) + 1) * 62500000),
    input_tokens: "600000",
    output_tokens: "140000",
    generation_count: "400",
  })),
  models: [
    {
      model_id: modelId,
      charge: "7500000000",
      input_tokens: "18000000",
      output_tokens: "4200000",
      generation_count: "12000",
    },
  ],
});

export const handlersFor = (currentUser: CurrentUser) => [
  http.get("/api/v1/me", () => HttpResponse.json(currentUser)),
  http.patch("/api/v1/organizations/:organizationId", async ({ request }) => {
    const patch = (await request.json()) as Partial<CurrentOrganization>;
    return HttpResponse.json({
      ...(currentUser.organizations[0] ?? organization),
      ...patch,
    });
  }),
  ...sharedHandlers,
];

const sharedHandlers = [
  http.patch("/api/v1/workspaces/:workspaceId", async ({ request }) => {
    const patch = (await request.json()) as Partial<
      components["schemas"]["Workspace"]
    >;
    return HttpResponse.json({ ...workspace, ...patch });
  }),
  http.get("/api/v1/organizations/:organizationId/workspaces", () =>
    HttpResponse.json(list(workspace)),
  ),
  http.get("/api/v1/models", ({ request }) =>
    HttpResponse.json<components["schemas"]["ModelList"]>({
      ...list(
        ...(new URL(request.url).searchParams.get("external") === "true"
          ? [
              ...MODEL_CATALOG.filter((entry) =>
                /^(openai|anthropic)\//.test(entry.id),
              ).map((entry) => ({
                ...model,
                id: entry.id,
                name: entry.displayName,
                icon: entry.icon,
              })),
              {
                ...model,
                id: "openai/gpt-4.1-mini",
                name: "GPT-4.1 Mini",
                icon: "/model-providers/openai.svg",
              },
            ]
          : [
              model,
              {
                ...model,
                id: task.base_model_id,
                name: "Example training model",
              },
            ]),
      ),
      service_tiers: [
        {
          service_tier: "default",
          price_multiplier_numerator: 1,
          price_multiplier_denominator: 1,
          price_change_percent: 0,
        },
      ],
    }),
  ),
  http.get("/api/v1/workspaces/:workspaceId/api-keys", () =>
    HttpResponse.json(list(apiKey)),
  ),
  http.get("/api/v1/organizations/:organizationId/billing", () =>
    HttpResponse.json(billing),
  ),
  http.get("/api/v1/organizations/:organizationId/balance-transactions", () =>
    HttpResponse.json(list(transaction)),
  ),
  http.get("/api/v1/workspaces/:workspaceId/usage", ({ request }) =>
    HttpResponse.json(
      usage(new URL(request.url).searchParams.get("from") ?? createdAt),
    ),
  ),
  http.get("/api/v1/workspaces/:workspaceId/generations", ({ request }) =>
    HttpResponse.json(
      new URL(request.url).searchParams.has("task_id")
        ? list(trace)
        : list(generation),
    ),
  ),
  http.get("/api/v1/workspaces/:workspaceId/generations/:generationId", () =>
    HttpResponse.json(traceContent),
  ),
  http.get("/api/v1/workspaces/:workspaceId/tasks", () =>
    HttpResponse.json(
      list({ ...task, latest_run: { ...run, version_name: version.name } }),
    ),
  ),
  http.get("/api/v1/workspaces/:workspaceId/tasks/:task", () =>
    HttpResponse.json({ ...task, production_version_id: version.id }),
  ),
  http.get("/api/v1/workspaces/:workspaceId/tasks/:task/versions", () =>
    HttpResponse.json(list(version)),
  ),
  http.get(
    "/api/v1/workspaces/:workspaceId/tasks/:task/versions/:versionId/evaluation",
    () => HttpResponse.json(evaluationResults),
  ),
  http.get("/api/v1/workspaces/:workspaceId/training-runs", () =>
    HttpResponse.json(list(run)),
  ),
  http.get(
    "/api/v1/workspaces/:workspaceId/training-runs/:runId/events",
    ({ request }) => {
      const after = Number(new URL(request.url).searchParams.get("after") ?? 0);

      return HttpResponse.json(
        list(...events.filter((event) => event.id > after)),
      );
    },
  ),
  http.all(/\/api\//, () =>
    HttpResponse.json(
      {
        title: "Mock unavailable",
        detail: "This action is not mocked in Storybook.",
        status: 501,
      },
      { status: 501 },
    ),
  ),
];

export const handlers = handlersFor(user);
export const newOrganizationHandlers = [
  http.get("/api/v1/organizations/:organizationId/billing", () =>
    HttpResponse.json({ ...billing, balance: "5000000000" }),
  ),
  ...handlersFor(acmeOwner),
];
