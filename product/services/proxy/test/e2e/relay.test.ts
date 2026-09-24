import { gzipSync } from "node:zlib";

import { describe, expect, it } from "vitest";

import { useCases } from "../../../gateway/test/integration/case.js";
import { deferred } from "../../../gateway/test/integration/eventually.js";
import {
  CHAT,
  MESSAGES,
  providerKey,
  providerModel,
  RELAY_ROUTES,
  relayHeaders,
  useProxy,
} from "./support/fixtures.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);

/** Headers an SDK or the edge sends that must reach the provider exactly. */
const CONTENT_HEADERS = {
  "anthropic-version": "2023-06-01",
  "anthropic-beta": "prompt-caching-2024-07-31",
  "openai-organization": "org_synthetic",
  "openai-project": "proj_synthetic",
  "user-agent": "synthetic-sdk/1.0",
  "x-stainless-retry-count": "0",
  "idempotency-key": "idem_1",
  "accept-encoding": "gzip, br",
};

/** Headers that must never leave our edge. */
const PRIVATE_HEADERS = {
  cookie: "session=secret",
  "x-forwarded-for": "203.0.113.9",
  "x-forwarded-proto": "https",
  "x-amzn-trace-id": "Root=1-synthetic",
  "x-real-ip": "203.0.113.9",
  forwarded: "for=203.0.113.9",
  "x-gradiated-service-tier": "flex",
  "x-gradiated-fallback-model": "claude-other",
};

describe("request fidelity", () => {
  it.each(RELAY_ROUTES)(
    "$name reaches the provider byte for byte",
    async (route) => {
      const instance = await makeCase("vllm");
      const model = providerModel(route.provider);
      // Whitespace, key order, escapes, duplicate non-model keys and non-ASCII text
      // would all change under a parse and re-serialize.
      const body = `{ "stream":false,\n"model" : "${model}", "metadata":{"b":1,"a":2},"note":"\\u00e9 ✓","note":"dup",\n"messages":[{"role":"user","content":"Synthetic ticket"}],"max_tokens":16 }`;

      const response = await fixture.proxy.client.post(route.path, {
        headers: {
          ...relayHeaders(instance, route.provider),
          "content-type": "application/json",
        },
        content: body,
      });

      expect(response.status, response.text).toBe(200);
      const [sent] = fixture.provider.requests;
      expect(sent!.method).toBe("POST");
      expect(sent!.path).toBe(route.providerPath);
      expect(sent!.body.toString()).toBe(body);
    },
  );

  it.each(RELAY_ROUTES)(
    "$name forwards content headers and nothing private",
    async (route) => {
      const instance = await makeCase("vllm");
      const key = providerKey(route.provider);

      await fixture.proxy.client.post(route.path, {
        headers: {
          ...relayHeaders(instance, route.provider, key),
          ...CONTENT_HEADERS,
          ...PRIVATE_HEADERS,
        },
        json: route.body(providerModel(route.provider)),
      });

      const { headers } = fixture.provider.requests[0]!;
      expect(headers).toMatchObject(CONTENT_HEADERS);
      for (const name of Object.keys(PRIVATE_HEADERS))
        expect(headers, name).not.toHaveProperty(name);
      expect(headers).not.toHaveProperty("x-gradiated-api-key");
      expect(JSON.stringify(headers)).not.toContain(instance.key);

      if (route.provider === "anthropic") {
        expect(headers["x-api-key"]).toBe(key);
        expect(headers).not.toHaveProperty("authorization");
      } else {
        expect(headers.authorization).toBe(`Bearer ${key}`);
        expect(headers).not.toHaveProperty("x-api-key");
      }
      expect(headers["x-gradiated-hop"]).toBe("1");
    },
  );

  it("keeps the query string on the fixed provider path", async () => {
    const instance = await makeCase("vllm");

    await fixture.proxy.client.post(`${MESSAGES.path}?beta=true`, {
      headers: relayHeaders(instance, "anthropic"),
      json: MESSAGES.body(providerModel("anthropic")),
    });

    expect(fixture.provider.requests[0]!.path).toBe("/v1/messages?beta=true");
  });

  it("refuses a request that already crossed a proxy", async () => {
    const instance = await makeCase("vllm");

    const response = await fixture.proxy.client.post(MESSAGES.path, {
      headers: {
        ...relayHeaders(instance, "anthropic"),
        "x-gradiated-hop": "1",
      },
      json: MESSAGES.body(providerModel("anthropic")),
    });

    expect(response.status).toBe(400);
    expect(response.error().code).toBe("invalid_request");
    expect(fixture.provider.requests).toEqual([]);
  });
});

describe("response fidelity", () => {
  it.each([
    {
      status: 200,
      body: '{"id":"msg_1","content":[{"type":"text","text":"ok"}]}',
    },
    {
      status: 400,
      body: '{"type":"error","error":{"type":"invalid_request_error","message":"bad"}}',
    },
    {
      status: 401,
      body: '{"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}',
    },
    { status: 403, body: '{"error":{"type":"permission_error"}}' },
    {
      status: 404,
      body: '{"error":{"message":"The model does not exist","code":"model_not_found"}}',
    },
    { status: 413, body: '{"error":{"type":"request_too_large"}}' },
    {
      status: 429,
      body: '{"error":{"type":"rate_limit_error"}}',
      headers: { "retry-after": "7" },
    },
    { status: 500, body: '{"error":{"type":"api_error"}}' },
    { status: 503, body: '{"error":{"message":"slow down"}}' },
    {
      status: 529,
      body: '{"type":"error","error":{"type":"overloaded_error"}}',
    },
  ])(
    "returns a provider $status unchanged",
    async ({ status, body, headers = {} }) => {
      const instance = await makeCase("vllm");
      fixture.provider.reply({
        status,
        body,
        headers: {
          ...headers,
          "request-id": "req_synthetic",
          "anthropic-ratelimit-requests-remaining": "9",
        },
      });

      const response = await fixture.proxy.client.post(MESSAGES.path, {
        headers: relayHeaders(instance, "anthropic"),
        json: MESSAGES.body(providerModel("anthropic")),
      });

      expect(response.status).toBe(status);
      expect(response.text).toBe(body);
      expect(response.headers).toMatchObject({
        ...headers,
        "request-id": "req_synthetic",
        "anthropic-ratelimit-requests-remaining": "9",
        "content-type": "application/json",
      });
      expect(response.headers["x-generation-id"]).toMatch(/^[0-9a-f-]{36}$/);
      await instance.expectNotDispatched();
    },
  );

  it("drops the provider's cookies and connection hints", async () => {
    const instance = await makeCase("vllm");
    fixture.provider.reply({
      headers: {
        "set-cookie": "__cf_bm=1",
        "alt-svc": 'h3=":443"',
        "x-request-id": "req_1",
      },
    });

    const response = await fixture.proxy.client.post(CHAT.path, {
      headers: relayHeaders(instance, "openai"),
      json: CHAT.body(providerModel("openai")),
    });

    expect(response.headers).not.toHaveProperty("set-cookie");
    expect(response.headers).not.toHaveProperty("alt-svc");
    expect(response.headers["x-request-id"]).toBe("req_1");
  });

  it("returns an encoded body without decoding it", async () => {
    const instance = await makeCase("vllm");
    const encoded = gzipSync(Buffer.from('{"id":"msg_1"}'));
    fixture.provider.reply({
      body: encoded,
      headers: { "content-encoding": "gzip" },
    });

    const response = await fixture.proxy.client.stream(MESSAGES.path, {
      headers: relayHeaders(instance, "anthropic"),
      json: MESSAGES.body(providerModel("anthropic")),
    });
    const chunks: Buffer[] = [];
    for await (const chunk of response.message) chunks.push(Buffer.from(chunk));

    expect(response.headers["content-encoding"]).toBe("gzip");
    expect(Buffer.concat(chunks).equals(encoded)).toBe(true);
  });

  it("returns a provider redirect instead of following it", async () => {
    const instance = await makeCase("vllm");
    fixture.provider.reply({
      status: 307,
      headers: { location: `${fixture.provider.url}/elsewhere` },
    });

    const response = await fixture.proxy.client.post(MESSAGES.path, {
      headers: relayHeaders(instance, "anthropic"),
      json: MESSAGES.body(providerModel("anthropic")),
    });

    expect(response.status).toBe(307);
    expect(fixture.provider.requests.map((request) => request.path)).toEqual([
      "/v1/messages",
    ]);
  });

  it("never charges or admits a relayed request", async () => {
    const instance = await makeCase("vllm");
    await instance.setTenant({ balance: 0 });

    const response = await fixture.proxy.client.post(MESSAGES.path, {
      headers: relayHeaders(instance, "anthropic"),
      json: MESSAGES.body(providerModel("anthropic")),
    });

    expect(response.status).toBe(200);
    expect(await instance.operationalBalance()).toBeUndefined();
    await instance.expectNotDispatched();
  });
});

describe("streaming", () => {
  const EVENTS = [
    'event: message_start\ndata: {"type":"message_start"}\n\n',
    'event: content_block_delta\ndata: {"delta":{"text":"Hel"}}\n\n',
    'event: content_block_delta\ndata: {"delta":{"text":"lo ✓"}}\n\n',
    'event: message_stop\ndata: {"type":"message_stop"}\n\n',
  ];

  it.each([MESSAGES, CHAT])(
    "$name delivers each event before the provider sends the next",
    async (route) => {
      const instance = await makeCase("vllm");
      const rest = deferred();
      fixture.provider.reply({ chunks: EVENTS, afterFirstChunk: rest });

      const response = await fixture.proxy.client.stream(route.path, {
        headers: relayHeaders(instance, route.provider),
        json: { ...route.body(providerModel(route.provider)), stream: true },
      });
      const reader = response.message[Symbol.asyncIterator]();
      const first = await reader.next();

      // The provider is still holding the rest of the stream.
      expect(rest.settled()).toBe(false);
      expect(String(first.value)).toBe(EVENTS[0]);

      rest.resolve();
      let received = String(first.value);
      for (
        let next = await reader.next();
        !next.done;
        next = await reader.next()
      )
        received += String(next.value);

      expect(response.status).toBe(200);
      expect(response.headers["content-type"]).toBe("text/event-stream");
      expect(received).toBe(EVENTS.join(""));
    },
  );

  it("fails a stream whose provider goes silent past the idle deadline", async () => {
    const instance = await makeCase("vllm");
    const silent = await fixture.startProxy({ PROXY_IDLE_SECONDS: "1" });
    fixture.provider.reply({ chunks: [EVENTS[0]!], stall: true });

    const response = await silent.client.stream(MESSAGES.path, {
      headers: relayHeaders(instance, "anthropic"),
      json: { ...MESSAGES.body(providerModel("anthropic")), stream: true },
      timeoutMs: 10_000,
    });
    const started = Date.now();
    let received = "";
    const ended = new Promise<string>((resolve) => {
      response.message.on("data", (chunk) => (received += String(chunk)));
      response.message.on("aborted", () => resolve("aborted"));
      response.message.on("error", () => resolve("error"));
      response.message.on("end", () => resolve("end"));
    });

    expect(await ended).not.toBe("end");
    expect(received).toBe(EVENTS[0]);
    expect(Date.now() - started).toBeLessThan(5000);
    await fixture.provider.requests[0]!.abandoned.promise;
  });
});
