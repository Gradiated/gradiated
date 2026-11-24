import { createHash } from "node:crypto";
import { createServer } from "node:http";

import { expect, inject, it } from "vitest";

import { useCases } from "./case.js";
import { chatChunks } from "./chat.js";
import { GatewayProcess } from "./gateway-process.js";
import { freePort } from "./ports.js";

const { makeCase } = useCases();

it("fails over, stays on the winning provider and settles buffered and streamed usage", async () => {
  const stack = inject("stack");
  const model = `test/fallback-${crypto.randomUUID()}`;
  const providers = ["baseten", "modal"] as const;
  const upstreamModel = (provider: string): string => `fixture/${provider}`;
  const requests: Array<{
    authorization?: string;
    model: string;
    stream: boolean;
  }> = [];
  const usage = {
    prompt_tokens: 100,
    completion_tokens: 3,
    total_tokens: 103,
    prompt_tokens_details: { cached_tokens: 20 },
  };
  const upstream = createServer(async (req, res) => {
    const chunks: Buffer[] = [];
    for await (const chunk of req) chunks.push(Buffer.from(chunk));
    const body = JSON.parse(Buffer.concat(chunks).toString());

    if (req.url === "/") {
      res.setHeader("Content-Type", "application/json");
      res.end(
        JSON.stringify({
          SecretString: JSON.stringify({
            activeSlot: "primary",
            primaryApiKey: `fixture-${String(body.SecretId).split("/").at(-1)}`,
          }),
        }),
      );
      return;
    }

    if (req.url !== "/v1/chat/completions") {
      res.writeHead(404).end();
      return;
    }

    requests.push({
      ...(req.headers.authorization
        ? { authorization: req.headers.authorization }
        : {}),
      model: body.model,
      stream: body.stream,
    });

    if (requests.length === 1) {
      res.writeHead(429, { "Content-Type": "application/json" }).end("{}");
      return;
    }

    const envelope = {
      id: "chatcmpl-provider-fixture",
      created: 1,
      model: body.model,
    };
    const message = { role: "assistant", content: "Synthetic answer" };
    if (body.stream) {
      res.setHeader("Content-Type", "text/event-stream");
      const frames = [
        { choices: [{ index: 0, delta: message, finish_reason: "stop" }] },
        { choices: [], usage },
      ].map(
        (frame) =>
          `data: ${JSON.stringify({
            ...envelope,
            object: "chat.completion.chunk",
            ...frame,
          })}\n\n`,
      );
      res.end(frames.join("") + "data: [DONE]\n\n");
      return;
    }

    res.setHeader("Content-Type", "application/json");
    res.end(
      JSON.stringify({
        ...envelope,
        object: "chat.completion",
        choices: [{ index: 0, message, finish_reason: "stop" }],
        usage,
      }),
    );
  });
  await new Promise<void>((resolve) =>
    upstream.listen(0, "127.0.0.1", resolve),
  );
  const address = upstream.address();
  if (!address || typeof address === "string")
    throw new Error("missing upstream port");
  const upstreamUrl = `http://127.0.0.1:${address.port}`;
  let gateway: GatewayProcess | undefined;

  try {
    gateway = await GatewayProcess.start({
      redisUrl: stack.redisUrl,
      databaseUrl: stack.databaseUrl,
      runtimeToken: stack.runtimeToken,
      port: await freePort(),
      generationTimeoutSeconds: 10,
      logName: "gateway-direct-fallback",
      logLevel: "info",
      fallback: {
        secretsManagerUrl: upstreamUrl,
        routes: {
          [model]: providers.map((provider) => ({
            provider,
            base_url: `${upstreamUrl}/v1`,
            model: upstreamModel(provider),
            nano_usd_per_token: { input: 300, cached_input: 30, output: 1200 },
          })),
        },
      },
    });
    const instance = await makeCase("vllm", {
      gatewayUrl: gateway.url,
      modelId: model,
      replicas: 0,
    });

    const session = { session_id: "shared-session" };
    const response = await instance.post(session);

    expect(response.status, response.text).toBe(200);
    expect(response.json().model).toBe(model);
    expect(requests.map((call) => call.model).sort()).toEqual(
      providers.map(upstreamModel),
    );
    for (const provider of providers) {
      expect(requests).toContainEqual({
        authorization: `Bearer fixture-${provider}`,
        model: upstreamModel(provider),
        stream: false,
      });
      expect(response.text).not.toContain(upstreamModel(provider));
    }

    const stream = await instance.http.stream(instance.path, {
      headers: instance.headers,
      json: instance.body({
        ...session,
        stream: true,
        stream_options: { include_usage: true },
      }),
    });

    expect(stream.status).toBe(200);
    const frames = await stream.dataFrames();
    expect(frames.at(-1)).toBe("[DONE]");
    const chunks = chatChunks(frames);
    expect(chunks.every((chunk) => chunk.model === model)).toBe(true);
    expect(chunks.at(-1)?.usage).toMatchObject({
      prompt_tokens: 100,
      completion_tokens: 3,
    });
    expect(requests.slice(2)).toEqual([{ ...requests[1], stream: true }]);

    const releaseDigest = `sha256:${createHash("sha256")
      .update(JSON.stringify({ capacity: "fallback", model }))
      .digest("hex")}`;
    const winner = requests[1]!.model.split("/").at(-1);
    const usageLogs = (await gateway.log())
      .split("\n")
      .filter((line) => line.includes('"event":"external_usage"'))
      .map((line) => JSON.parse(line).fields);

    for (const served of [response, stream]) {
      await instance.settled(served, { releaseDigest, charge: 900 });
      expect(usageLogs).toContainEqual(
        expect.objectContaining({
          generation_id: served.headers["x-gradiated-generation-id"],
          upstream_provider: winner,
          upstream_cost_nano_usd: 28_200,
        }),
      );
    }
  } finally {
    await gateway?.stop();
    await new Promise<void>((resolve) => upstream.close(() => resolve()));
  }
});
