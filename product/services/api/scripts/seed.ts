import {
  createCatalogBillingService,
  createControlDatabase,
  createValkeyServingProjector,
} from "@gradiated/control";
import { createValkeyClient } from "@gradiated/valkey";

const apiUrl = process.env.SEED_API_URL ?? "http://127.0.0.1:3001";
const databaseUrl =
  process.env.DATABASE_URL ??
  "postgresql://gradiated:gradiated@127.0.0.1:5432/gradiated";
const valkeyUrl = process.env.VALKEY_URL ?? "redis://127.0.0.1:6379";
const email = process.env.SEED_USER_EMAIL ?? "dev@gradiated.com";
const userName = process.env.SEED_USER_NAME ?? "Local Developer";
const organizationName =
  process.env.SEED_ORGANIZATION_NAME ?? "Local Development";

const waitForApi = async (): Promise<void> => {
  const deadline = Date.now() + 60_000;
  for (;;) {
    try {
      const response = await fetch(`${apiUrl}/health/ready`);
      if (response.ok) return;
    } catch {
      // The API may not be listening yet.
    }

    if (Date.now() >= deadline)
      throw new Error("API did not become ready within 60 seconds");
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
      Origin: "http://localhost:3000",
    },
    body: JSON.stringify({
      email,
      name: userName,
      callbackURL: "http://localhost:3000/api-keys",
      newUserCallbackURL: "http://localhost:3000/api-keys",
      errorCallbackURL: "http://localhost:3000/login",
    }),
  });
  if (!requested.ok)
    throw new Error(
      `Development magic-link request failed with status ${requested.status}`,
    );

  const captured = await fetch(
    `${apiUrl}/api/auth/test/magic-link?email=${encodeURIComponent(email)}`,
  );
  if (!captured.ok)
    throw new Error(
      `Development magic-link capture failed with status ${captured.status}`,
    );
  const { url } = (await captured.json()) as { url: string };
  const verificationUrl = new URL(url);
  const apiOrigin = new URL(apiUrl);
  verificationUrl.protocol = apiOrigin.protocol;
  verificationUrl.host = apiOrigin.host;
  const verified = await fetch(verificationUrl, { redirect: "manual" });
  const cookie = sessionCookie(verified);

  if (!cookie) throw new Error("Better Auth did not return a session cookie");
  return cookie;
};

await waitForApi();
const cookie = await authenticate();
const me = await fetch(`${apiUrl}/api/v1/me`, { headers: { Cookie: cookie } });
if (!me.ok)
  throw new Error(`Current-user lookup failed with status ${me.status}`);

const currentUser = (await me.json()) as {
  id: string;
  organizations: Array<{ id: string }>;
};
let organizationId = currentUser.organizations[0]?.id;
if (currentUser.organizations.length === 0) {
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
  const created = (await organization.json()) as { id: string };
  organizationId = created.id;
  console.log(`Seeded ${email} with organization ${organizationName}`);
}

if (!organizationId) throw new Error("Seed organization identity is missing");

const { database, pool } = createControlDatabase(databaseUrl);
const valkey = createValkeyClient({ VALKEY_URL: valkeyUrl });
await valkey.connect();
try {
  const catalogBilling = createCatalogBillingService(
    database,
    createValkeyServingProjector(valkey),
  );
  await catalogBilling.upsertModel({
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
    },
  });
  await catalogBilling.upsertModelDeployment({
    id: "0198c36f-9b6a-7000-8000-000000000004",
    modelId: "mlx-community/qwen3-0.6b-4bit",
    status: "available",
    provider: "local",
    region: "local",
    faultDomain: "local:runtime-1",
    serviceUrl: "http://127.0.0.1:30000",
    release: {
      schema_version: 1,
      runtime_revision: "8bb106cee94c1ccb5625cdb78ef0ee3e0cad3918",
      model_path: "mlx-community/Qwen3-0.6B-4bit",
      model_revision: "73e3e38d981303bc594367cd910ea6eb48349da8",
      tokenizer_path: "mlx-community/Qwen3-0.6B-4bit",
      tokenizer_revision: "73e3e38d981303bc594367cd910ea6eb48349da8",
    },
  });
  await catalogBilling.initializeCurrentAccount(organizationId);
  await catalogBilling.applyBalanceTransaction({
    organizationId,
    type: "credit",
    amount: 100_000_000_000n,
    sourceType: "operator",
    sourceId: `local-development-credit-v1:${organizationId}`,
    createdBy: currentUser.id,
  });
  console.log(
    `Seed data ready for ${email}: ${organizationName}, local Qwen and $100.00 credit`,
  );
} finally {
  if (valkey.isOpen) await valkey.quit();
  await pool.end();
}
