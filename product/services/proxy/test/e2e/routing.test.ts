// The routing rule: with a provider key, a request relays to that key's provider
// unless it names a model we host; everything else goes to the gateway. The key
// alone picks the provider, so paths and provider models need no proxy knowledge.
import { describe, expect, it } from "vitest";

import { expectPublicError } from "../../../gateway/test/integration/assertions.js";
import { useCases, type Case } from "../../../gateway/test/integration/case.js";
import {
  Client,
  type Headers,
  type Response,
} from "../../../gateway/test/integration/http-client.js";
import {
  anthropicKey,
  CHAT,
  expectProxyError,
  MESSAGES,
  openAiKey,
  providerKeyHeaders,
  providerModel,
  RELAY_ROUTES,
  relayHeaders,
  useProxy,
  type ProviderName,
} from "./support/fixtures.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);

const BOUNDARY = "----synthetic-boundary";
const MULTIPART = Buffer.concat([
  Buffer.from(
    `--${BOUNDARY}\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n` +
      `--${BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\nContent-Type: audio/wav\r\n\r\n`,
  ),
  Buffer.from([0x52, 0x49, 0x46, 0x46, 0x00, 0xff, 0x10, 0x80]),
  Buffer.from(`\r\n--${BOUNDARY}--\r\n`),
]);
const AUDIO = Buffer.from([0xff, 0xfb, 0x90, 0x64, 0x00, 0x0f, 0xf0, 0x00]);

interface Raw {
  readonly status: number;
  readonly headers: Record<string, string>;
  readonly body: Buffer;
}

/** Any method, raw bytes both ways: the proxy must not care what they are. */
const send = async (
  method: string,
  path: string,
  headers: Headers,
  body?: Buffer | string,
): Promise<Raw> => {
  const response = await fetch(new URL(path, fixture.proxy.url), {
    method,
    headers: headers as Record<string, string>,
    ...(body === undefined
      ? {}
      : { body: typeof body === "string" ? body : new Uint8Array(body) }),
  });

  const received: Record<string, string> = {};
  response.headers.forEach((value, name) => {
    received[name] = value;
  });

  return {
    status: response.status,
    headers: received,
    body: Buffer.from(await response.arrayBuffer()),
  };
};

describe("with a provider key", () => {
  it.each(RELAY_ROUTES)(
    "relays $name for a model we do not host",
    async (route) => {
      const instance = await makeCase("vllm");

      const response = await fixture.proxy.client.post(route.path, {
        headers: relayHeaders(instance, route.provider),
        json: route.body(providerModel(route.provider)),
      });

      expect(response.status, response.text).toBe(200);
      expect(fixture.provider.requests.map((request) => request.path)).toEqual([
        route.providerPath,
      ]);
      await instance.expectNotDispatched();
    },
  );

  it.each<{
    name: string;
    provider: ProviderName;
    method: string;
    path: string;
    providerPath?: string;
    body?: Buffer | string;
    contentType?: string;
  }>([
    {
      name: "a multipart audio transcription",
      provider: "openai",
      method: "POST",
      path: "/v1/audio/transcriptions",
      body: MULTIPART,
      contentType: `multipart/form-data; boundary=${BOUNDARY}`,
    },
    {
      name: "an image generation",
      provider: "openai",
      method: "POST",
      path: "/v1/images/generations",
      body: '{"model":"gpt-image-1","prompt":"a lighthouse"}',
      contentType: "application/json",
    },
    {
      name: "a file deletion",
      provider: "openai",
      method: "DELETE",
      path: "/v1/files/file_123",
    },
    {
      name: "the provider's model list",
      provider: "openai",
      method: "GET",
      path: "/v1/models?limit=3",
    },
    {
      name: "a message batch listing",
      provider: "anthropic",
      method: "GET",
      path: "/v1/messages/batches?limit=2",
    },
    {
      name: "an endpoint that does not exist yet",
      provider: "anthropic",
      method: "PATCH",
      path: "/v1/agents/agent_1",
      body: '{"name":"new"}',
      contentType: "application/json",
    },
    {
      name: "a body that names no model",
      provider: "anthropic",
      method: "POST",
      path: "/v1/messages",
      body: '{"max_tokens":1}',
      contentType: "application/json",
    },
    {
      name: "a body that is not JSON",
      provider: "openai",
      method: "POST",
      path: "/v1/chat/completions",
      body: "not json",
      contentType: "text/plain",
    },
    {
      name: "an unprefixed gateway path",
      provider: "anthropic",
      method: "POST",
      path: "/messages",
      providerPath: "/v1/messages",
      body: '{"model":"claude-x","max_tokens":1}',
      contentType: "application/json",
    },
  ])(
    "relays $name with the exact method, path and bytes",
    async ({ provider, method, path, providerPath, body, contentType }) => {
      const instance = await makeCase("vllm");
      const headers: Headers = {
        ...relayHeaders(instance, provider),
        ...(contentType ? { "content-type": contentType } : {}),
      };

      const response = await send(method, path, headers, body);

      expect(response.status).toBe(200);
      const [sent] = fixture.provider.requests;
      expect(sent!.method).toBe(method);
      expect(sent!.path).toBe(providerPath ?? path);
      expect(sent!.body.equals(Buffer.from(body ?? ""))).toBe(true);
      if (contentType) expect(sent!.headers["content-type"]).toBe(contentType);
      await instance.expectNotDispatched();
    },
  );

  it("returns a binary provider response byte for byte", async () => {
    const instance = await makeCase("vllm");
    fixture.provider.reply({
      body: AUDIO,
      headers: { "content-type": "audio/mpeg" },
    });

    const response = await send(
      "POST",
      "/v1/audio/speech",
      {
        ...relayHeaders(instance, "openai"),
        "content-type": "application/json",
      },
      '{"model":"gpt-4o-mini-tts","input":"hello","voice":"alloy"}',
    );

    expect(response.status).toBe(200);
    expect(response.headers["content-type"]).toBe("audio/mpeg");
    expect(response.body.equals(AUDIO)).toBe(true);
  });

  it("relays to the key's provider whatever the path", async () => {
    const instance = await makeCase("vllm");
    const key = openAiKey();

    await fixture.proxy.client.post(MESSAGES.path, {
      headers: {
        authorization: `Bearer ${key}`,
        "x-gradiated-api-key": instance.key,
      },
      json: MESSAGES.body(providerModel("anthropic")),
    });

    const [sent] = fixture.provider.requests;
    expect(sent!.path).toBe("/v1/messages");
    expect(sent!.headers.authorization).toBe(`Bearer ${key}`);
  });

  it.each<{ name: string; route: typeof MESSAGES; headers: Headers }>([
    {
      name: "an Anthropic key on Messages",
      route: MESSAGES,
      headers: { "x-api-key": anthropicKey() },
    },
    {
      name: "an OpenAI key on Chat Completions",
      route: CHAT,
      headers: { authorization: `Bearer ${openAiKey()}` },
    },
    {
      name: "an OpenAI key on Messages",
      route: MESSAGES,
      headers: { authorization: `Bearer ${openAiKey()}` },
    },
  ])(
    "sends a hosted model to the gateway with $name",
    async ({ route, headers }) => {
      const instance = await fixture.hostedCase();

      const response = await fixture.proxy.client.post(route.path, {
        headers: { ...headers, "x-gradiated-api-key": instance.key },
        json: route.body(instance.model),
      });

      expect(response.status, response.text).toBe(200);
      await instance.settled(response);
      expect(fixture.provider.requests).toEqual([]);
    },
  );

  it("keeps a catalog model on the gateway when we have no deployment of it", async () => {
    const instance = await fixture.hostedCase({
      replicas: 0,
      openRouterModel: "synthetic-author/openrouter-model",
    });

    const response = await fixture.proxy.client.post(MESSAGES.path, {
      headers: relayHeaders(instance, "anthropic"),
      json: MESSAGES.body(instance.model),
    });

    expect(fixture.provider.requests).toEqual([]);
    expectPublicError(response, { code: "runtime_unavailable" });
    await instance.expectNotDispatched();
  });

  it("matches hosted models without regard to case, as the gateway does", async () => {
    const instance = await fixture.hostedCase();

    const response = await fixture.proxy.client.post(MESSAGES.path, {
      headers: relayHeaders(instance, "anthropic"),
      json: MESSAGES.body(instance.model.toUpperCase()),
    });

    expect(fixture.provider.requests).toEqual([]);
    expect(response.status, response.text).toBe(200);
    await instance.settled(response);
  });

  it("loads aliases from the catalog and serves their canonical model", async () => {
    const instance = await fixture.hostedCase();
    const aliases = [
      `alias-${crypto.randomUUID()}`,
      `alias-${crypto.randomUUID()}`,
    ];
    await instance.database.query(
      "update models set aliases = $2 where id = $1",
      [instance.model, aliases],
    );
    await instance.database.query(
      "insert into models (id, name, status, properties, type) select $2, name, 'retired', properties, type from models where id = $1",
      [instance.model, aliases[0]],
    );
    await fixture.proxy.catalogRefreshedAfter(Date.now());

    try {
      for (const alias of [
        aliases[0]!,
        aliases[1]!.toUpperCase(),
        aliases[0]!,
      ]) {
        const response = await fixture.proxy.client.post(CHAT.path, {
          headers: relayHeaders(instance, "openai"),
          json: CHAT.body(alias),
        });

        expect(response.status, response.text).toBe(200);
        expect(response.json().model).toBe(instance.model);
        await instance.settled(response);
      }

      expect(fixture.provider.requests).toEqual([]);
      const listed = await fixture.proxy.client.get("/v1/models", {
        headers: instance.headers,
      });
      expect(listed.status, listed.text).toBe(200);
      const ids = (listed.json().data as { id: string }[]).map(
        (model) => model.id,
      );
      expect(ids.filter((id) => id === instance.model)).toHaveLength(1);
      expect(ids).not.toContain(aliases[0]);
    } finally {
      await instance.database.query("delete from models where id = $1", [
        aliases[0],
      ]);
    }
  });

  it.each<{
    name: string;
    headers: (instance: Case) => Headers;
    format: ProviderName;
  }>([
    {
      name: "no Gradiated key",
      headers: () => providerKeyHeaders("anthropic", anthropicKey()),
      format: "anthropic",
    },
    {
      name: "an unknown key namespace",
      headers: (instance) => ({
        "x-api-key": "pk-unknown",
        "x-gradiated-api-key": instance.key,
      }),
      format: "openai",
    },
    {
      name: "two provider keys",
      headers: (instance) => ({
        "x-api-key": anthropicKey(),
        authorization: `Bearer ${openAiKey()}`,
        "x-gradiated-api-key": instance.key,
      }),
      format: "openai",
    },
    {
      name: "two different Gradiated keys",
      headers: (instance) => ({
        "x-api-key": anthropicKey(),
        authorization: `Bearer grad_${"a".repeat(32)}`,
        "x-gradiated-api-key": instance.key,
      }),
      format: "openai",
    },
  ])(
    "refuses $name without reaching the provider",
    async ({ headers, format }) => {
      const instance = await makeCase("vllm");

      const response = await fixture.proxy.client.post(MESSAGES.path, {
        headers: headers(instance),
        json: MESSAGES.body(providerModel("anthropic")),
      });

      expectProxyError(response, "invalid_api_key", format);
      expect(fixture.provider.requests).toEqual([]);
      await instance.expectNotDispatched();
    },
  );

  it.each<{ provider: ProviderName }>([
    { provider: "anthropic" },
    { provider: "openai" },
  ])(
    "answers its own errors in the $provider format on any path",
    async ({ provider }) => {
      const response = await fixture.proxy.client.post("/v1/files", {
        headers: providerKeyHeaders(
          provider,
          provider === "anthropic" ? anthropicKey() : openAiKey(),
        ),
        content: "{}",
      });

      expectProxyError(response, "invalid_api_key", provider);
    },
  );
});

describe("the gateway's private endpoints", () => {
  it.each(["/health", "/health/ready", "/health/live", "/metrics"])(
    "keeps %s private, even with a provider key",
    async (path) => {
      const instance = await makeCase("vllm");
      const before = await fixture.proxy.responses("gateway");

      const response = await fixture.proxy.client.get(path, {
        headers: relayHeaders(instance, "openai"),
      });

      expect(response.status).toBe(404);
      expect(response.error().code).toBe("not_found");
      expect(await fixture.proxy.responses("gateway")).toBe(before);
      expect(fixture.provider.requests).toEqual([]);
    },
  );
});

/**
 * Without a provider key every request must behave exactly as a direct gateway
 * call. Each row is sent both ways and the answers compared.
 */
describe("without a provider key", () => {
  type Request = {
    method: "GET" | "POST";
    path: string;
    headers: Headers;
    content?: string;
  };

  type Row = {
    name: string;
    request: (instance: Case) => Request;
    /** Other tests add models concurrently, so a listing compares this case's own entry. */
    listing?: boolean;
  };

  const rows: Row[] = [
    {
      name: "a model we do not host",
      request: (instance) => ({
        method: "POST",
        path: CHAT.path,
        headers: instance.headers,
        content: JSON.stringify(CHAT.body(providerModel("openai"))),
      }),
    },
    {
      name: "a body that names no model",
      request: (instance) => ({
        method: "POST",
        path: MESSAGES.path,
        headers: instance.headers,
        content: JSON.stringify({ max_tokens: 1 }),
      }),
    },
    {
      name: "a duplicate model key",
      request: (instance) => ({
        method: "POST",
        path: MESSAGES.path,
        headers: instance.headers,
        content: `{"model":"${instance.model}","model":"${instance.model}","max_tokens":1}`,
      }),
    },
    {
      name: "a body that is not JSON",
      request: (instance) => ({
        method: "POST",
        path: CHAT.path,
        headers: instance.headers,
        content: "not json",
      }),
    },
    {
      name: "our model list",
      request: (instance) => ({
        method: "GET",
        path: "/v1/models",
        headers: instance.headers,
      }),
      listing: true,
    },
    {
      name: "a GET on an inference path",
      request: (instance) => ({
        method: "GET",
        path: MESSAGES.path,
        headers: instance.headers,
      }),
    },
    {
      name: "a path the gateway does not serve",
      request: (instance) => ({
        method: "POST",
        path: "/v1/embeddings",
        headers: instance.headers,
        content: "{}",
      }),
    },
    {
      name: "an unknown Gradiated key on a hosted model",
      request: (instance) => ({
        method: "POST",
        path: CHAT.path,
        headers: { authorization: "Bearer grad_revoked_or_unknown" },
        content: JSON.stringify(CHAT.body(instance.model)),
      }),
    },
  ];

  const sendTo = (client: Client, request: Request): Promise<Response> =>
    request.method === "GET"
      ? client.get(request.path, { headers: request.headers })
      : client.post(request.path, {
          headers: request.headers,
          content: request.content ?? "",
        });

  const comparable = (
    response: Response,
    instance: Case,
    listing: boolean,
  ) => ({
    status: response.status,
    contentType: response.headers["content-type"],
    body: listing
      ? (response.json().data as { id: string }[]).find(
          (model) => model.id === instance.model,
        )
      : response.text.replaceAll(/"(created|id)":\s*("[^"]*"|\d+)/g, '"$1":_'),
  });

  it.each(rows)(
    "forwards $name exactly as the gateway answers it",
    async ({ request, listing = false }) => {
      const instance = await fixture.hostedCase();
      const sent = request(instance);

      const direct = await sendTo(new Client(fixture.gatewayUrl), sent);
      const proxied = await sendTo(fixture.proxy.client, sent);

      expect(comparable(proxied, instance, listing)).toEqual(
        comparable(direct, instance, listing),
      );
      if (listing)
        expect(comparable(proxied, instance, listing).body).toBeDefined();
      expect(fixture.provider.requests).toEqual([]);
    },
  );

  it("keeps the gateway's own public error for an unknown Gradiated key", async () => {
    const response = await fixture.proxy.client.post(CHAT.path, {
      headers: { authorization: "Bearer grad_unknown" },
      json: CHAT.body("anything"),
    });

    expectPublicError(response, { code: "invalid_api_key" });
  });
});
