import { CurrentUserSchema, OrganizationSchema } from "@gradiated/contracts";
import { z } from "@hono/zod-openapi";

import type { ModelDeploymentRelease } from "@gradiated/contracts";
import {
  applyCatalog,
  catalogModels,
  type CatalogModelInput,
} from "@gradiated/control";

import { withControlDatabase } from "../src/operations/database.js";

interface LocalDeployments {
  model: CatalogModelInput;
  deployments: readonly { id: string; serviceUrl: string }[];
  placement: { provider: string; region: string; faultDomain: string };
  release: ModelDeploymentRelease;
}

const includeLocalQwen = process.env.SEED_LOCAL_QWEN === "1";

const apiUrl = process.env.SEED_API_URL ?? "http://127.0.0.1:3001";
const consoleUrl = process.env.SEED_CONSOLE_URL ?? "http://localhost:3000";
const databaseUrl =
  process.env.DATABASE_URL ??
  "postgresql://gradiated:gradiated@127.0.0.1:5432/gradiated";
const email = process.env.SEED_USER_EMAIL ?? "dev@gradiated.com";
const userName = process.env.SEED_USER_NAME ?? "Local Developer";
const organizationName =
  process.env.SEED_ORGANIZATION_NAME ?? "Local Development";

const waitForApi = async (): Promise<void> => {
  const deadline = Date.now() + 60_000;
  for (;;) {
    const response = await fetch(`${apiUrl}/health/ready`).catch(
      () => undefined,
    );
    if (response?.ok) return;

    if (Date.now() >= deadline) {
      throw new Error("API did not become ready within 60 seconds");
    }

    await new Promise((resolve) => setTimeout(resolve, 500));
  }
};

const sessionCookie = (response: Response): string | null => {
  const cookies = response.headers.getSetCookie();
  if (cookies.length === 0) return null;

  return cookies.map((cookie) => cookie.split(";", 1)[0]).join("; ");
};

const authenticate = async (): Promise<string> => {
  const requested = await fetch(`${apiUrl}/api/auth/sign-in/magic-link`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: consoleUrl,
    },
    body: JSON.stringify({
      email,
      name: userName,
      callbackURL: `${consoleUrl}/api-keys`,
      newUserCallbackURL: `${consoleUrl}/api-keys`,
      errorCallbackURL: `${consoleUrl}/login`,
    }),
  });
  if (!requested.ok) {
    throw new Error(
      `Development magic-link request failed with status ${requested.status}`,
    );
  }

  const captured = await fetch(
    `${apiUrl}/api/auth/test/magic-link?email=${encodeURIComponent(email)}`,
  );
  if (!captured.ok) {
    throw new Error(
      `Development magic-link capture failed with status ${captured.status}`,
    );
  }

  const { url } = z.object({ url: z.string() }).parse(await captured.json());
  const verificationUrl = new URL(url);
  const apiOrigin = new URL(apiUrl);
  verificationUrl.protocol = apiOrigin.protocol;
  verificationUrl.host = apiOrigin.host;

  const verified = await fetch(verificationUrl, { redirect: "manual" });
  const cookie = sessionCookie(verified);

  if (!cookie) throw new Error("Better Auth did not return a session cookie");

  return cookie;
};

const localQwen = {
  model: {
    id: "mlx-community/qwen3-0.6b-4bit",
    name: "Qwen3 0.6B 4-bit",
    status: "available",
    properties: {
      description:
        "Pinned small local-development model served with zero prompt and response retention.",
      released_at: "2025-04-29T00:00:00.000Z",
      hugging_face_id: "mlx-community/Qwen3-0.6B-4bit",
      quantization: "int4",
      tokenizer: "Qwen3",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 32_768, unit: "token" },
          },
          pricing: [
            { type: "prompt", unit: "token", cost: 100 },
            { type: "cached_prompt", unit: "token", cost: 50 },
          ],
        },
      ],
      output_modalities: [
        {
          type: "text",
          max_length: { value: 4_096, unit: "token" },
          supported_parameters: {
            max_tokens: {
              type: "integer",
              min: 1,
              max: 4_096,
              unit: "token",
            },
            temperature: { type: "range", min: 0, max: 2 },
          },
          pricing: [{ type: "completion", unit: "token", cost: 300 }],
        },
      ],
      // From the model's generation_config.json; SGLang applies it by default.
      default_parameters: { temperature: 0.6 },
    },
  },
  deployments: [
    {
      id: "0198c36f-9b6a-7000-8000-000000000004",
      serviceUrl: "http://127.0.0.1:30000",
    },
  ],
  placement: {
    provider: "local",
    region: "local",
    faultDomain: "local:runtime-1",
  },
  release: {
    schema_version: 1,
    runtime_revision: "8bb106cee94c1ccb5625cdb78ef0ee3e0cad3918",
    model_path: "mlx-community/Qwen3-0.6B-4bit",
    model_revision: "73e3e38d981303bc594367cd910ea6eb48349da8",
    tokenizer_path: "mlx-community/Qwen3-0.6B-4bit",
    tokenizer_revision: "73e3e38d981303bc594367cd910ea6eb48349da8",
  },
} satisfies LocalDeployments;

const catalogOnly = process.env.SEED_CATALOG_ONLY === "1";

interface CreditTarget {
  organizationId: string;
  createdBy: string;
}

const seedAccount = async (): Promise<CreditTarget> => {
  await waitForApi();

  const cookie = await authenticate();
  const me = await fetch(`${apiUrl}/api/v1/me`, {
    headers: { Cookie: cookie },
  });
  if (!me.ok) {
    throw new Error(`Current-user lookup failed with status ${me.status}`);
  }

  const currentUser = CurrentUserSchema.parse(await me.json());
  const [existing] = currentUser.organizations;
  if (existing)
    return { organizationId: existing.id, createdBy: currentUser.id };

  const organization = await fetch(`${apiUrl}/api/v1/organizations`, {
    method: "POST",
    headers: { Cookie: cookie, "Content-Type": "application/json" },
    body: JSON.stringify({ name: organizationName }),
  });
  if (!organization.ok) {
    throw new Error(
      `Organization seed failed with status ${organization.status}`,
    );
  }

  const created = OrganizationSchema.parse(await organization.json());
  console.log(`Seeded ${email} with organization ${organizationName}`);

  return { organizationId: created.id, createdBy: currentUser.id };
};

const creditTarget = catalogOnly ? undefined : await seedAccount();

await withControlDatabase(async ({ database, catalog }) => {
  await applyCatalog(database);

  if (includeLocalQwen) {
    await catalog.upsertModel(localQwen.model);
    for (const deployment of localQwen.deployments) {
      await catalog.upsertModelDeployment({
        ...deployment,
        modelId: localQwen.model.id,
        status: "available",
        ...localQwen.placement,
        release: localQwen.release,
      });
    }
  } else {
    const qwen = (await catalog.listModels()).find(
      (model) => model.id === localQwen.model.id,
    );
    if (qwen) await catalog.upsertModel({ ...qwen, status: "retired" });
  }

  if (creditTarget) {
    await catalog.applyBalanceTransaction({
      ...creditTarget,
      type: "credit",
      amount: 100_000_000_000n,
      sourceType: "operator",
      sourceId: `local-development-credit-v1:${creditTarget.organizationId}`,
    });
  }
}, databaseUrl);

const seededModelNames = catalogModels.map((model) => model.name).join(", ");
console.log(
  creditTarget
    ? `Seed data ready for ${email}: ${organizationName}, ${seededModelNames} and $100.00 credit`
    : "Local model catalog updated",
);
