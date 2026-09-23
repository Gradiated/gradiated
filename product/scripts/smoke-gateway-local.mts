import { CurrentUserSchema } from "../packages/contracts/src/me.js";
import {
  CreatedApiKeySchema,
  WorkspaceListSchema,
  type CreatedApiKeyResponse,
} from "../packages/contracts/src/workspaces.js";

const apiUrl = process.env.SEED_API_URL ?? "http://127.0.0.1:3001";
const gatewayUrl = process.env.GATEWAY_URL ?? "http://127.0.0.1:3002";
const email = process.env.SEED_USER_EMAIL ?? "dev@gradiated.com";
const consoleOrigin = "http://localhost:3000";
const localModel = "mlx-community/qwen3-0.6b-4bit";

type Usage = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
};

type ReportedUsage = {
  prompt_tokens?: unknown;
  completion_tokens?: unknown;
  total_tokens?: unknown;
};

type CatalogModel = { id: string; is_ready?: boolean };

type Completion = {
  model?: unknown;
  choices?: { finish_reason?: string }[];
  usage?: ReportedUsage;
};

type CompletionChunk = { choices?: unknown[]; usage?: ReportedUsage };

const requireOk = (response: Response, description: string) => {
  if (!response.ok) {
    throw new Error(`${description} failed with status ${response.status}`);
  }

  return response;
};

const generationId = (response: Response) => {
  const value = response.headers.get("x-generation-id");
  const uuidV7 =
    /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  if (!value || !uuidV7.test(value)) {
    throw new Error("Gateway response has no UUIDv7 generation ID");
  }

  return value;
};

const isCount = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 1;

const authoritativeUsage = (usage: ReportedUsage | undefined): Usage => {
  const prompt = usage?.prompt_tokens;
  const completion = usage?.completion_tokens;
  const total = usage?.total_tokens;

  if (
    !isCount(prompt) ||
    !isCount(completion) ||
    total !== prompt + completion
  ) {
    throw new Error("Gateway response has inconsistent authoritative usage");
  }

  return {
    prompt_tokens: prompt,
    completion_tokens: completion,
    total_tokens: total,
  };
};

const signIn = async () => {
  requireOk(
    await fetch(`${apiUrl}/api/auth/sign-in/magic-link`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: consoleOrigin },
      body: JSON.stringify({
        email,
        name: "Local Developer",
        callbackURL: `${consoleOrigin}/api-keys`,
        newUserCallbackURL: `${consoleOrigin}/api-keys`,
        errorCallbackURL: `${consoleOrigin}/login`,
      }),
    }),
    "Magic-link request",
  );

  const captured = requireOk(
    await fetch(
      `${apiUrl}/api/auth/test/magic-link?email=${encodeURIComponent(email)}`,
    ),
    "Magic-link capture",
  );
  const capture: { url?: unknown } = await captured.json();

  if (typeof capture.url !== "string") {
    throw new Error("Magic-link capture returned no URL");
  }

  const verificationUrl = new URL(capture.url);
  const apiOrigin = new URL(apiUrl);
  verificationUrl.protocol = apiOrigin.protocol;
  verificationUrl.host = apiOrigin.host;

  const verified = await fetch(verificationUrl, { redirect: "manual" });
  const cookies = verified.headers.getSetCookie();

  if (cookies.length === 0) {
    throw new Error("Magic-link verification returned no session");
  }

  return cookies.map((cookie) => cookie.split(";", 1)[0]).join("; ");
};

const apiKeysUrl = async (cookie: string) => {
  const me = CurrentUserSchema.parse(
    await requireOk(
      await fetch(`${apiUrl}/api/v1/me`, { headers: { Cookie: cookie } }),
      "Current-user lookup",
    ).json(),
  );
  const organizationId = me.organizations[0]?.id;

  if (!organizationId) throw new Error("The seed user has no organization");

  const organizationUrl = `${apiUrl}/api/v1/organizations/${organizationId}`;
  const workspaces = WorkspaceListSchema.parse(
    await requireOk(
      await fetch(`${organizationUrl}/workspaces`, {
        headers: { Cookie: cookie },
      }),
      "Workspace lookup",
    ).json(),
  );
  const workspaceId = workspaces.data[0]?.id;

  if (!workspaceId) throw new Error("The seed organization has no workspace");

  return `${organizationUrl}/workspaces/${workspaceId}/api-keys`;
};

const createKey = async (keysUrl: string, cookie: string) =>
  CreatedApiKeySchema.parse(
    await requireOk(
      await fetch(keysUrl, {
        method: "POST",
        headers: { Cookie: cookie, "Content-Type": "application/json" },
        body: JSON.stringify({ name: "Gateway local smoke" }),
      }),
      "API-key creation",
    ).json(),
  );

const revokeKey = async (
  keysUrl: string,
  cookie: string,
  key: CreatedApiKeyResponse,
) => {
  requireOk(
    await fetch(`${keysUrl}/${key.api_key.id}`, {
      method: "DELETE",
      headers: { Cookie: cookie },
    }),
    "Temporary API-key revocation",
  );
};

const checkCatalog = async (secret: string) => {
  const catalog: { data?: CatalogModel[] } = await requireOk(
    await fetch(`${gatewayUrl}/v1/models`, {
      headers: { Authorization: `Bearer ${secret}` },
    }),
    "Gateway model catalog",
  ).json();
  const model = catalog.data?.find((entry) => entry.id === localModel);

  if (!model) {
    throw new Error("Gateway model catalog does not advertise the local model");
  }

  if (
    model.is_ready !== true ||
    JSON.stringify(model).includes("service_url")
  ) {
    throw new Error("Gateway model catalog exposes invalid operational state");
  }

  return { id: model.id, is_ready: model.is_ready };
};

const complete = async (secret: string, stream: boolean, description: string) =>
  requireOk(
    await fetch(`${gatewayUrl}/v1/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${secret}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: localModel,
        messages: [
          { role: "user", content: "Reply with exactly: gateway-ready" },
        ],
        max_tokens: 32,
        temperature: 0,
        stream,
      }),
    }),
    description,
  );

const checkCompletion = async (secret: string) => {
  const response = await complete(secret, false, "Gateway completion");
  const generation_id = generationId(response);
  const completion: Completion = await response.json();

  if (completion.model !== localModel) {
    throw new Error("Gateway completion did not name the requested model");
  }

  return {
    model: completion.model,
    generation_id,
    finish_reason: completion.choices?.[0]?.finish_reason,
    usage: authoritativeUsage(completion.usage),
  };
};

const checkStream = async (secret: string) => {
  const response = await complete(secret, true, "Gateway streaming completion");
  const generation_id = generationId(response);

  if (!response.headers.get("content-type")?.startsWith("text/event-stream")) {
    throw new Error("Gateway streaming response is not SSE");
  }

  const events = (await response.text())
    .split(/\r?\n\r?\n/)
    .map((frame) => frame.trim())
    .filter(Boolean)
    .map((frame) => frame.replace(/^data: ?/, ""));

  if (events.at(-1) !== "[DONE]") {
    throw new Error("Gateway streaming response did not end with [DONE]");
  }

  const chunks: CompletionChunk[] = events
    .slice(0, -1)
    .map((event) => JSON.parse(event));
  const [terminal, ...extra] = chunks.filter(
    (chunk) => chunk.usage !== undefined,
  );

  if (!terminal || extra.length > 0 || terminal.choices?.length !== 0) {
    throw new Error("Gateway did not expose exactly one terminal usage chunk");
  }

  return { generation_id, usage: authoritativeUsage(terminal.usage) };
};

const checkGateway = async (secret: string) => {
  const catalog_model = await checkCatalog(secret);
  const { model, ...non_streaming } = await checkCompletion(secret);
  const streaming = await checkStream(secret);

  return { status: "passed", model, catalog_model, non_streaming, streaming };
};

const cookie = await signIn();
const keysUrl = await apiKeysUrl(cookie);
const key = await createKey(keysUrl, cookie);

const summary = await checkGateway(key.secret).catch(async (error) => {
  await revokeKey(keysUrl, cookie, key).catch(console.error);
  throw error;
});

await revokeKey(keysUrl, cookie, key);
console.log(JSON.stringify(summary, null, 2));
