import { parseEnvironment, type Environment } from "@gradiated/config";
import { z } from "@hono/zod-openapi";

const PortSchema = z.coerce.number().int().min(1).max(65_535);
const OptionalPandaDocSetting = z.preprocess(
  (value) => (typeof value === "string" && !value.trim() ? undefined : value),
  z.string().trim().min(1).optional(),
);

const ApiOnlyEnvironmentSchema = z.object({
  ENGINEER_ONBOARDING_NOTIFY_EMAIL: z.preprocess(
    (value) => (typeof value === "string" && !value.trim() ? undefined : value),
    z.string().trim().toLowerCase().pipe(z.email()).optional(),
  ),
  GITHUB_INSTALLATIONS_ENABLED: z.enum(["true", "false"]).default("false"),
  SLACK_CONNECT_ENABLED: z.enum(["true", "false"]).default("false"),
  SLACK_BOT_TOKEN: OptionalPandaDocSetting,
  SLACK_ENGINEER_USER_IDS: z
    .string()
    .default("")
    .transform((value) =>
      value
        .split(",")
        .map((id) => id.trim())
        .filter(Boolean),
    )
    .pipe(z.array(z.string().regex(/^[UW][A-Z0-9]+$/)).max(20)),
  PANDADOC_API_KEY: OptionalPandaDocSetting,
  PANDADOC_NDA_TEMPLATE_ID: z
    .string()
    .trim()
    .min(1)
    .default("bTmxaYhTaU2tQ28fLhVrHn"),
  PANDADOC_NDA_TEMPLATE_VERSION: OptionalPandaDocSetting,
  PANDADOC_NDA_DATE_FIELD: OptionalPandaDocSetting,
  PANDADOC_NDA_ENABLED: z.enum(["true", "false"]).default("false"),
  PANDADOC_NDA_COUNTERSIGNER_COMPANY: z
    .string()
    .trim()
    .min(1)
    .default("PostHog Inc."),
  PANDADOC_NDA_COUNTERSIGNER_NAME: z
    .string()
    .trim()
    .min(1)
    .default("James Hawkins"),
  PANDADOC_NDA_COUNTERSIGNER_TITLE: z.string().trim().min(1).default("Co-CEO"),
  POSTHOG_KEY: z
    .string()
    .optional()
    .transform((value) => value || undefined),
  POSTHOG_HOST: z.url().default("https://us.i.posthog.com"),
  TRAINING_ARTIFACTS_BUCKET: z.string().min(1).optional(),
  CONTENTS_BUCKET: z.string().min(1).optional(),
  METRICS_PORT: PortSchema.default(9_464),
  PROFILING_INGEST_TOKEN: z.string().min(32).optional(),
  PROFILING_HOST: z.string().min(1).default("0.0.0.0"),
  PROFILING_PORT: PortSchema.default(3_003),
  GPU_CONTROL_HOST: z.string().min(1).default("0.0.0.0"),
  GPU_CONTROL_PORT: PortSchema.default(3_004),
  GPU_CONTROL_PROVIDER: z
    .string()
    .regex(/^[a-z][a-z0-9_-]{0,99}$/)
    .optional(),
});

export type AuthEmailTransport =
  { kind: "test" } | { kind: "resend"; from: string; apiKey: string };

export type ApiConfiguration = Environment &
  z.infer<typeof ApiOnlyEnvironmentSchema> & { authEmail: AuthEmailTransport };

const authEmailTransport = (environment: Environment): AuthEmailTransport => {
  if (environment.AUTH_TEST_MODE) return { kind: "test" };

  const { AUTH_EMAIL_FROM: from, RESEND_API_KEY: apiKey } = environment;
  if (!from || !apiKey) {
    throw new Error("parseEnvironment must enforce the Resend settings.");
  }

  return { kind: "resend", from, apiKey };
};

export const parseApiEnvironment = (
  environment: NodeJS.ProcessEnv,
): ApiConfiguration => {
  const shared = parseEnvironment(environment);

  return {
    ...shared,
    ...ApiOnlyEnvironmentSchema.parse(environment),
    authEmail: authEmailTransport(shared),
  };
};
