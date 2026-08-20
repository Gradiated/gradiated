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

const generationId = (response) => {
  const value = response.headers.get("x-generation-id");
  if (
    !value ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value,
    )
  ) {
    throw new Error("Gateway response has no UUIDv7 generation ID");
  }
  return value;
};

const authoritativeUsage = (usage) => {
  if (
    !Number.isSafeInteger(usage?.prompt_tokens) ||
    usage.prompt_tokens < 1 ||
    !Number.isSafeInteger(usage?.completion_tokens) ||
    usage.completion_tokens < 1 ||
    usage.total_tokens !== usage.prompt_tokens + usage.completion_tokens
  ) {
    throw new Error("Gateway response has inconsistent authoritative usage");
  }
  return usage;
};

const completionBody = (stream) =>
  JSON.stringify({
    model: "mlx-community/qwen3-0.6b-4bit",
    messages: [{ role: "user", content: "Reply with exactly: gateway-ready" }],
    max_tokens: 32,
    temperature: 0,
    stream,
  });

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
  const catalog = await requireOk(
    await fetch(`${gatewayUrl}/v1/models`, {
      headers: { Authorization: `Bearer ${created.secret}` },
    }),
    "Gateway model catalog",
  ).then((response) => response.json());
  const advertisedModel = catalog.data?.find(
    (model) => model.id === "mlx-community/qwen3-0.6b-4bit",
  );
  if (!advertisedModel || advertisedModel.schema_version !== "2.4") {
    throw new Error("Gateway model catalog does not advertise the local model");
  }
  if (
    advertisedModel.is_ready !== true ||
    JSON.stringify(advertisedModel).includes("service_url")
  ) {
    throw new Error("Gateway model catalog exposes invalid operational state");
  }

  const response = await requireOk(
    await fetch(`${gatewayUrl}/v1/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${created.secret}`,
        "Content-Type": "application/json",
      },
      body: completionBody(false),
    }),
    "Gateway completion",
  );
  const nonStreamingGenerationId = generationId(response);
  const completion = await response.json();
  const nonStreamingUsage = authoritativeUsage(completion.usage);

  const streamResponse = await requireOk(
    await fetch(`${gatewayUrl}/v1/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${created.secret}`,
        "Content-Type": "application/json",
      },
      body: completionBody(true),
    }),
    "Gateway streaming completion",
  );
  const streamingGenerationId = generationId(streamResponse);
  if (
    !streamResponse.headers.get("content-type")?.startsWith("text/event-stream")
  ) {
    throw new Error("Gateway streaming response is not SSE");
  }
  const streamEvents = (await streamResponse.text())
    .split(/\r?\n\r?\n/)
    .map((frame) => frame.trim())
    .filter(Boolean)
    .map((frame) => frame.replace(/^data: ?/, ""));
  if (streamEvents.at(-1) !== "[DONE]") {
    throw new Error("Gateway streaming response did not end with [DONE]");
  }
  const chunks = streamEvents.slice(0, -1).map((event) => JSON.parse(event));
  const usageChunks = chunks.filter((chunk) => chunk.usage !== undefined);
  if (usageChunks.length !== 1 || usageChunks[0].choices?.length !== 0) {
    throw new Error("Gateway did not expose exactly one terminal usage chunk");
  }
  const streamingUsage = authoritativeUsage(usageChunks[0].usage);

  console.log(
    JSON.stringify(
      {
        status: "passed",
        model: completion.model,
        catalog_model: {
          id: advertisedModel.id,
          schema_version: advertisedModel.schema_version,
          is_ready: advertisedModel.is_ready,
        },
        non_streaming: {
          generation_id: nonStreamingGenerationId,
          finish_reason: completion.choices?.[0]?.finish_reason,
          usage: nonStreamingUsage,
        },
        streaming: {
          generation_id: streamingGenerationId,
          usage: streamingUsage,
        },
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
