import {
  createCatalogBillingService,
  createControlDatabase,
  createValkeyServingProjector,
} from "@gradiated/control";
import { createClient } from "redis";

const apiUrl = process.env.SEED_API_URL ?? "http://127.0.0.1:3001";
const databaseUrl =
  process.env.DATABASE_URL ??
  "postgresql://gradiated:gradiated@127.0.0.1:5432/gradiated";
const valkeyUrl = process.env.VALKEY_URL ?? "redis://127.0.0.1:6379";
const email = process.env.SEED_USER_EMAIL ?? "dev@gradiated.com";
const password = process.env.SEED_USER_PASSWORD ?? "1234";
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
  const signUp = await fetch(`${apiUrl}/api/auth/sign-up/email`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: "http://localhost:3000",
    },
    body: JSON.stringify({ email, password, name: userName }),
  });
  let cookie = sessionCookie(signUp);

  if (!signUp.ok || !cookie) {
    const signIn = await fetch(`${apiUrl}/api/auth/sign-in/email`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Origin: "http://localhost:3000",
      },
      body: JSON.stringify({ email, password }),
    });
    if (!signIn.ok) {
      throw new Error(
        `Development user sign-in failed with status ${signIn.status}`,
      );
    }
    cookie = sessionCookie(signIn);
  }

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
const valkey = createClient({ url: valkeyUrl });
await valkey.connect();
try {
  const catalogBilling = createCatalogBillingService(
    database,
    createValkeyServingProjector(valkey),
  );
  await catalogBilling.upsertModel({
    id: "moonshotai/kimi-k3",
    name: "Kimi K3",
    status: "available",
    properties: {
      schema_version: 1,
      description:
        "Moonshot AI's exact Kimi K3 open-weight model, served with zero prompt and response retention.",
      released_at: null,
      hugging_face_id: "moonshotai/Kimi-K3",
      quantization: null,
      tokenizer: "Kimi",
      input_modalities: [{ type: "text" }],
      output_modalities: [{ type: "text" }],
      pricing: [
        { unit: "input_token", cost: 2_800 },
        { unit: "output_token", cost: 14_000 },
      ],
      capacity: [
        { metric: "context_tokens", value: 262_144 },
        { metric: "max_output_tokens", value: 32_768 },
      ],
      passthrough_parameters: {
        max_tokens: { type: "integer", minimum: 1, maximum: 32_768 },
        stream: { type: "boolean" },
        temperature: { type: "number", minimum: 0, maximum: 2 },
      },
      deprecation_at: null,
      openrouter: null,
    },
  });
  await catalogBilling.projectCurrentAccount(organizationId);
  await catalogBilling.applyBalanceTransaction({
    organizationId,
    type: "credit",
    amount: 100_000_000_000n,
    sourceType: "operator",
    sourceId: `local-development-credit-v1:${organizationId}`,
    createdBy: currentUser.id,
  });
  console.log(
    `Seed data ready for ${email}: ${organizationName}, Kimi K3 and $100.00 credit`,
  );
} finally {
  if (valkey.isOpen) await valkey.quit();
  await pool.end();
}
