import { parseEnvironment, type Environment } from "@gradiated/config";
import { z } from "@hono/zod-openapi";

const PortSchema = z.coerce.number().int().min(1).max(65_535);
const OptionalSecret = z.preprocess(
  (value) => (typeof value === "string" && !value.trim() ? undefined : value),
  z.string().trim().min(1).optional(),
);

const ApiOnlyEnvironmentSchema = z.object({
  SLACK_BOT_TOKEN: OptionalSecret,
  PANDADOC_API_KEY: OptionalSecret,
  GITHUB_APP_SLUG: z.preprocess(
    (value) => value || undefined,
    z
      .string()
      .regex(/^[a-z0-9][a-z0-9-]{0,99}$/)
      .default("gradiated"),
  ),
  POSTHOG_KEY: z
    .string()
    .optional()
    .transform((value) => value || undefined),
  POSTHOG_HOST: z.url().default("https://us.i.posthog.com"),
  TRAINING_ARTIFACTS_BUCKET: z.string().min(1).optional(),
  CONTENTS_BUCKET: z.string().min(1).optional(),
  METRICS_PORT: PortSchema.default(9_464),
  MCP_RESOURCE_URL: z.url().default("https://mcp.gradiated.com/mcp"),
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
