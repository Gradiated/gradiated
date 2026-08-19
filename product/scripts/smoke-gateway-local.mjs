const apiUrl = process.env.SEED_API_URL ?? "http://127.0.0.1:3001";
const gatewayUrl = process.env.GATEWAY_URL ?? "http://127.0.0.1:3002";
const email = process.env.SEED_USER_EMAIL ?? "dev@gradiated.com";

const requireOk = async (response, description) => {
  if (response.ok) return response;
  throw new Error(`${description} failed with status ${response.status}`);
};

const sessionCookie = (response) => {
  const cookies = response.headers.getSetCookie();
  if (cookies.length === 0) return null;
  return cookies.map((cookie) => cookie.split(";", 1)[0]).join("; ");
};

await requireOk(
  await fetch(`${apiUrl}/api/auth/sign-in/magic-link`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: "http://localhost:3000",
    },
    body: JSON.stringify({
      email,
      name: "Local Developer",
      callbackURL: "http://localhost:3000/api-keys",
      newUserCallbackURL: "http://localhost:3000/api-keys",
      errorCallbackURL: "http://localhost:3000/login",
    }),
  }),
  "Magic-link request",
);

const captured = await requireOk(
  await fetch(
    `${apiUrl}/api/auth/test/magic-link?email=${encodeURIComponent(email)}`,
  ),
  "Magic-link capture",
);
const verificationUrl = new URL((await captured.json()).url);
const apiOrigin = new URL(apiUrl);
verificationUrl.protocol = apiOrigin.protocol;
verificationUrl.host = apiOrigin.host;
const verified = await fetch(verificationUrl, { redirect: "manual" });
const cookie = sessionCookie(verified);
if (!cookie) throw new Error("Magic-link verification returned no session");

const me = await requireOk(
  await fetch(`${apiUrl}/api/v1/me`, { headers: { Cookie: cookie } }),
  "Current-user lookup",
).then((response) => response.json());
const organizationId = me.organizations[0]?.id;
if (!organizationId) throw new Error("The seed user has no organization");

const workspaces = await requireOk(
  await fetch(`${apiUrl}/api/v1/organizations/${organizationId}/workspaces`, {
    headers: { Cookie: cookie },
  }),
  "Workspace lookup",
).then((response) => response.json());
const workspaceId = workspaces.data[0]?.id;
if (!workspaceId) throw new Error("The seed organization has no workspace");

const keyUrl = `${apiUrl}/api/v1/organizations/${organizationId}/workspaces/${workspaceId}/api-keys`;
const created = await requireOk(
  await fetch(keyUrl, {
    method: "POST",
    headers: { Cookie: cookie, "Content-Type": "application/json" },
    body: JSON.stringify({ name: "Gateway local smoke" }),
  }),
  "API-key creation",
).then((response) => response.json());

try {
  const response = await requireOk(
    await fetch(`${gatewayUrl}/v1/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${created.secret}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "mlx-community/qwen3-0.6b-4bit",
        messages: [
          { role: "user", content: "Reply with exactly: gateway-ready" },
        ],
        max_tokens: 32,
        temperature: 0,
      }),
    }),
    "Gateway completion",
  );
  const generationId = response.headers.get("x-generation-id");
  if (
    !generationId ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      generationId,
    )
  ) {
    throw new Error("Gateway response has no UUIDv7 generation ID");
  }
  const completion = await response.json();
  const usage = completion.usage;
  if (
    !Number.isSafeInteger(usage?.prompt_tokens) ||
    usage.prompt_tokens < 1 ||
    !Number.isSafeInteger(usage?.completion_tokens) ||
    usage.completion_tokens < 1 ||
    usage.total_tokens !== usage.prompt_tokens + usage.completion_tokens
  ) {
    throw new Error("Gateway response has inconsistent authoritative usage");
  }

  console.log(
    JSON.stringify(
      {
        status: "passed",
        generation_id: generationId,
        model: completion.model,
        finish_reason: completion.choices?.[0]?.finish_reason,
        usage,
      },
      null,
      2,
    ),
  );
} finally {
  await requireOk(
    await fetch(`${keyUrl}/${created.api_key.id}`, {
      method: "DELETE",
      headers: { Cookie: cookie },
    }),
    "Temporary API-key revocation",
  );
}
