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
  // grad-server's internal listener, such as http://grad-internal.training.svc:8789.
  GRAD_SERVER_URL: z.url().optional(),
  CONTENTS_BUCKET: z.string().min(1).optional(),
  METRICS_PORT: PortSchema.default(9_464),
  MCP_RESOURCE_URL: z.url().default("https://mcp.gradiated.com/mcp"),
  PROFILING_INGEST_TOKEN: z.string().min(32).optional(),
  PROFILING_HOST: z.string().min(1).default("0.0.0.0"),
  PROFILING_PORT: PortSchema.default(3_003),
  // The private listener grad calls for prices, balance checks and usage;
  // the previous token keeps working during a rotation.
  TRAINING_INTERNAL_TOKEN: z.string().min(32).optional(),
  TRAINING_INTERNAL_TOKEN_PREVIOUS: z.string().min(32).optional(),
  TRAINING_INTERNAL_HOST: z.string().min(1).default("0.0.0.0"),
  TRAINING_INTERNAL_PORT: PortSchema.default(3_005),
  GPU_CONTROL_HOST: z.string().min(1).default("0.0.0.0"),
  GPU_CONTROL_PORT: PortSchema.default(3_004),
  // Lets the playground reach MCP servers on loopback and private networks; local development only.
  MCP_PROXY_ALLOW_PRIVATE_NETWORKS: z
    .enum(["true", "false"])
    .default("false")
    .transform((value) => value === "true"),
  // The providers whose hosts reach the private GPU control listener, such as
  // runpod,aws; a status report must come from a deployment on one of them.
  GPU_CONTROL_PROVIDERS: z
    .string()
    .regex(/^[a-z][a-z0-9_-]{0,99}(,[a-z][a-z0-9_-]{0,99})*$/)
    .transform((value) => value.split(","))
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
  const own = ApiOnlyEnvironmentSchema.parse(environment);
  if (
    environment.NODE_ENV === "production" &&
    own.MCP_PROXY_ALLOW_PRIVATE_NETWORKS
  )
    throw new Error(
      "MCP_PROXY_ALLOW_PRIVATE_NETWORKS cannot be enabled in production.",
    );

  if (own.TRAINING_INTERNAL_TOKEN_PREVIOUS && !own.TRAINING_INTERNAL_TOKEN)
    throw new Error(
      "TRAINING_INTERNAL_TOKEN_PREVIOUS needs TRAINING_INTERNAL_TOKEN.",
    );

  const shared = parseEnvironment(environment);

  return { ...shared, ...own, authEmail: authEmailTransport(shared) };
};
