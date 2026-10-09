import { parseEnvironment, type Environment } from "@gradiated/config";
import { z } from "@hono/zod-openapi";

const PortSchema = z.coerce.number().int().min(1).max(65_535);

const DeploymentStatusTokensSchema = z
  .string()
  .optional()
  .transform((value, context) => {
    if (!value) return {};

    try {
      return JSON.parse(value) as unknown;
    } catch {
      // The input holds secret tokens, and V8 parse errors quote it.
      context.addIssue({
        code: "custom",
        message: "DEPLOYMENT_STATUS_INGEST_TOKENS must be a JSON object",
      });

      return z.NEVER;
    }
  })
  .pipe(
    z.record(
      z.string().regex(/^[a-z][a-z0-9_-]{0,99}$/, {
        error: "Deployment status provider names are invalid",
      }),
      z.string().min(32, {
        error: "Deployment status tokens must contain at least 32 characters",
      }),
      { error: "DEPLOYMENT_STATUS_INGEST_TOKENS must be a JSON object" },
    ),
  )
  .transform(
    (tokens): ReadonlyMap<string, string> => new Map(Object.entries(tokens)),
  );

const ApiOnlyEnvironmentSchema = z
  .object({
    POSTHOG_KEY: z
      .string()
      .optional()
      .transform((value) => value || undefined),
    POSTHOG_HOST: z.url().default("https://us.i.posthog.com"),
    NOMAD_CA_KMS_KEY: z.string().min(1).optional(),
    NOMAD_CA_PEM: z.string().min(1).optional(),
    TRAINING_ARTIFACTS_BUCKET: z.string().min(1).optional(),
    CONTENTS_BUCKET: z.string().min(1).optional(),
    METRICS_PORT: PortSchema.default(9_464),
    PROFILING_INGEST_TOKEN: z.string().min(32).optional(),
    PROFILING_HOST: z.string().min(1).default("0.0.0.0"),
    PROFILING_PORT: PortSchema.default(3_003),
    DEPLOYMENT_STATUS_INGEST_TOKENS: DeploymentStatusTokensSchema,
  })
  .refine(
    (value) => Boolean(value.NOMAD_CA_KMS_KEY) === Boolean(value.NOMAD_CA_PEM),
    {
      message: "NOMAD_CA_KMS_KEY and NOMAD_CA_PEM must be configured together",
    },
  );

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
