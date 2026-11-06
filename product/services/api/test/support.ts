import type { ModelProperties } from "@gradiated/contracts";
import { expect, vi } from "vitest";
import type {
  ApiKeyRecord,
  BalanceTransactionRecord,
  BillingAccountRecord,
  CreatedOrganization,
  ModelRecord,
  UserOrganization,
  WorkspaceRecord,
} from "@gradiated/control";

import { createApp, type AppDependencies } from "../src/app.js";
import { unservedDependencies } from "../src/openapi.js";
import type { DependencyProbe } from "../src/readiness.js";
import type { ApiServices, AuthService, SessionUser } from "../src/types.js";

export const organizationId = "0198ae59-294a-73a9-9d2f-962449d34226";
export const workspaceId = "0198ae5a-2529-7c1a-801b-dc9d5f876a94";
export const apiKeyId = "0198ae6f-68b0-7644-812d-c4bf16a926e3";
export const now = new Date("2026-08-16T12:05:00.000Z");
export const apiKeySecret = `grad_${"a".repeat(43)}`;

export const user: SessionUser = {
  id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774",
  name: "Ada Lovelace",
  email: "ada@example.com",
  emailVerified: true,
  isStaff: false,
  image: null,
  createdAt: new Date("2026-08-16T12:00:00.000Z"),
};

export const authenticated: AuthService = {
  handler: async () => new Response(null, { status: 404 }),
  resolveSession: async () => user,
};

export const anonymous: AuthService = {
  handler: authenticated.handler,
  resolveSession: async () => null,
};

export class SessionStoreError extends Error {}

export const sessionStoreDown: AuthService = {
  handler: authenticated.handler,
  resolveSession: async () => {
    throw new SessionStoreError("session store unreachable");
  },
};

export const workspaceRecord: WorkspaceRecord = {
  id: workspaceId,
  organizationId,
  name: "Default",
  isDefault: true,
  traceCaptureEnabled: false,
  traceRetentionDays: 30,
  defaultJudgeModel: "openai/gpt-5.6-sol",
  archivedAt: null,
  createdAt: now,
  updatedAt: now,
};

export const apiKeyRecord: ApiKeyRecord = {
  id: apiKeyId,
  organizationId,
  workspaceId,
  name: "Production",
  expiresAt: null,
  revokedAt: null,
  hidden: false,
  createdBy: user.id,
  createdAt: now,
  updatedAt: now,
};

export const organizationSummary: UserOrganization = {
  id: organizationId,
  name: "Personal",
  status: "active",
  role: "admin",
  defaultWorkspaceId: workspaceId,
  autoJoinDomain: null,
  onboardingCompleted: false,
};

export const createdOrganization: CreatedOrganization = {
  id: organizationId,
  kind: "customer",
  name: "Analytical Engines",
  status: "active",
  role: "admin",
  defaultWorkspaceId: workspaceId,
  createdAt: now,
  updatedAt: now,
};

export const billingAccountRecord: BillingAccountRecord = {
  organizationId,
  mode: "prepaid",
  stripeCustomerId: null,
  balance: 100_000_000_000n,
  stripePaymentMethodId: null,
  autoTopUpEnabled: false,
  autoTopUpThreshold: null,
  autoTopUpAmount: null,
  createdAt: now,
  updatedAt: now,
};

export const balanceTransactionRecord: BalanceTransactionRecord = {
  id: "0198ae70-68b0-7644-812d-c4bf16a926e3",
  organizationId,
  type: "credit",
  amount: 100_000_000_000n,
  balanceAfter: 100_000_000_000n,
  sourceType: "operator",
  sourceId: "local-credit",
  periodStart: null,
  periodEnd: null,
  generationCount: null,
  createdBy: user.id,
  createdAt: now,
};

const modelProperties: ModelProperties = {
  schema_version: 1,
  description: "Exact Kimi K3 inference.",
  released_at: null,
  hugging_face_id: "moonshotai/Kimi-K3",
  quantization: null,
  tokenizer: "Kimi",
  input_modalities: [
    {
      type: "text",
      supported_inputs: {
        max_context_length: { value: 262_144, unit: "token" },
        max_prompt_length: { value: 262_144, unit: "token" },
      },
      pricing: [
        { type: "prompt", unit: "token", cost: 2_800 },
        { type: "cached_prompt", unit: "token", cost: 2_800 },
      ],
    },
  ],
  output_modalities: [
    {
      type: "text",
      max_length: { value: 32_768, unit: "token" },
      default_length: { value: 1_024, unit: "token" },
      streaming: true,
      supported_parameters: {},
      pricing: [{ type: "completion", unit: "token", cost: 14_000 }],
    },
  ],
  passthrough_parameters: {},
  deprecation_date: null,
};

export const modelRecord: ModelRecord = {
  id: "moonshotai/kimi-k3",
  name: "Kimi K3",
  status: "available",
  properties: modelProperties,
  createdAt: now,
  updatedAt: now,
};

export const notUsed = (name: string) => async (): Promise<never> => {
  throw new Error(`${name} is not used by this test`);
};

export type ServiceOverrides = {
  [Service in keyof ApiServices]?: Partial<ApiServices[Service]>;
};

type TestAppOverrides = Partial<Omit<AppDependencies, "services">> & {
  services?: ServiceOverrides;
};

export const createTestApp = ({
  services = {},
  ...overrides
}: TestAppOverrides = {}) => {
  const unserved = unservedDependencies();
  const service = <Name extends keyof ApiServices>(
    name: Name,
  ): ApiServices[Name] => ({ ...unserved.services[name], ...services[name] });

  return createApp({
    ...unserved,
    auth: anonymous,
    ...overrides,
    services: {
      waitlist: service("waitlist"),
      // Billing responses read card details and the last failure; tests override them.
      billingPayments: {
        ...service("billingPayments"),
        describeCard:
          services.billingPayments?.describeCard ?? (async () => null),
      },
      catalogBilling: {
        ...service("catalogBilling"),
        topUpStatus:
          services.catalogBilling?.topUpStatus ??
          (async () => ({ pending: false, autoTopUpFailure: null })),
      },
      members: service("members"),
      organizations: service("organizations"),
      integrations: service("integrations"),
      usage: service("usage"),
      traces: service("traces"),
      training: service("training"),
      workspaces: service("workspaces"),
    },
  });
};

export type TestApp = ReturnType<typeof createTestApp>;

export const postJson = (
  app: TestApp,
  path: string,
  body: unknown,
  headers: Record<string, string> = {},
) =>
  app.request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });

export const expectProblem = async (
  response: Response,
  expected: { status: number; code: string; type: string },
) => {
  expect(response.status).toBe(expected.status);
  expect(response.headers.get("content-type")).toContain(
    "application/problem+json",
  );
  await expect(response.json()).resolves.toMatchObject({
    status: expected.status,
    code: expected.code,
    type: `https://gradiated.com/problems/${expected.type}`,
    request_id: expect.any(String),
  });
};

export const dependencyUp: DependencyProbe = { status: "up" };

export const dependencyDown: DependencyProbe = {
  status: "down",
  error: new Error("connection refused"),
};

const parseLogLine = (line: string): Record<string, unknown> =>
  JSON.parse(line);

export const captureServiceLogs = () => {
  const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
  log.mockClear();
  const lines = () => log.mock.calls.map(([line]) => String(line));

  return { lines, events: () => lines().map(parseLogLine) };
};

export const failWith = (error: Error) => async (): Promise<never> => {
  throw error;
};

export const controlServiceProblems = [
  { code: "forbidden", status: 403, type: "forbidden" },
  { code: "not_found", status: 404, type: "not-found" },
  { code: "unavailable", status: 503, type: "unavailable" },
] as const;

export const unauthenticatedProblem = {
  status: 401,
  code: "unauthenticated",
  type: "unauthenticated",
};

export const validationProblem = {
  status: 422,
  code: "validation_failed",
  type: "validation",
};

// An in-memory stand-in for the Valkey cache of Stripe card details.
export const cardDetailsCache = () => {
  const values = new Map<string, string>();

  return {
    values,
    get: async (key: string) => values.get(key) ?? null,
    set: async (key: string, value: string) => {
      values.set(key, value);
    },
  };
};
