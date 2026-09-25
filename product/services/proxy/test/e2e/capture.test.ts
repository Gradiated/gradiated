import { gzipSync } from "node:zlib";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import type { Case } from "../../../gateway/test/integration/case.js";
import { useCases } from "../../../gateway/test/integration/case.js";
import { eventually } from "../../../gateway/test/integration/eventually.js";
import { COLLECTOR_TOKEN, MockCollector } from "./support/collector.js";
import {
  CHAT,
  MESSAGES,
  providerModel,
  relayHeaders,
  useProxy,
} from "./support/fixtures.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);

let collector: MockCollector;

beforeAll(async () => {
  collector = await MockCollector.start();
});

afterAll(async () => {
  await collector.close();
});

const enableCapture = async (instance: Case, retentionDays = 30) => {
  await instance.database.query(
    `update workspaces
     set trace_capture_enabled = true, trace_retention_days = $2, updated_at = now()
     where id = $1`,
    [instance.workspace, retentionDays],
  );
};

const STREAM = [
  'event: message_start\ndata: {"type":"message_start"}\n\n',
  'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}\n\n',
  'event: message_stop\ndata: {"type":"message_stop"}\n\n',
];

const capturedFor = (generationId: string) =>
  eventually(
    () => collector.lines.find((line) => line.generation_id === generationId),
    5000,
    `the collector never received ${generationId}`,
  );

describe("relay capture", () => {
  it("sends a streamed relay to the collector with its raw bodies", async () => {
    const proxy = await fixture.startProxy(collector.env());
    const instance = await makeCase("vllm");
    await enableCapture(instance, 90);
    const body = `{"model":"${providerModel("anthropic")}", "stream":true,"max_tokens":16,"messages":[{"role":"user","content":"Synthetic ticket"}]}`;
    fixture.provider.reply({ chunks: STREAM });

    const response = await proxy.client.post(MESSAGES.path, {
      headers: {
        ...relayHeaders(instance, "anthropic"),
        "content-type": "application/json",
        "x-gradiated-task": "support-triage",
        "x-gradiated-trace-id": "trace-1",
        "x-gradiated-session-id": "session-1",
      },
      content: body,
    });

    expect(response.status, response.text).toBe(200);
    expect(response.text).toBe(STREAM.join(""));
    const generationId = response.headers["x-gradiated-generation-id"];
    const line = await capturedFor(String(generationId));

    expect(line).toEqual({
      schema: "gradiated.relay/1",
      generation_id: generationId,
      workspace_id: instance.workspace,
      task: "support-triage",
      trace_id: "trace-1",
      session_id: "session-1",
      provider: "anthropic",
      path: "/v1/messages",
      retention_days: 90,
      status: 200,
      outcome: "complete",
      completed_at: expect.any(String),
      request: body,
      response_content_type: "text/event-stream",
      response: STREAM.join(""),
    });
    const post = collector.posts.find((candidate) =>
      candidate.lines.includes(line),
    );
    expect(post?.headers.authorization).toBe(`Bearer ${COLLECTOR_TOKEN}`);
    expect(post?.headers["content-type"]).toBe("application/x-ndjson");
    const [sent] = fixture.provider.requests;
    expect(Object.keys(sent!.headers)).not.toContain("x-gradiated-task");
  });

  it.each([
    { name: "a workspace without capture", enabled: false, task: "triage" },
    { name: "a request without a task", enabled: true, task: undefined },
    { name: "an empty task", enabled: true, task: "" },
  ])("records nothing for $name", async ({ enabled, task }) => {
    const proxy = await fixture.startProxy(collector.env());
    const skipped = await makeCase("vllm");
    const sentinel = await makeCase("vllm");
    if (enabled) await enableCapture(skipped);
    await enableCapture(sentinel);

    const send = (instance: Case, taskHeader: string | undefined) =>
      proxy.client.post(CHAT.path, {
        headers: {
          ...relayHeaders(instance, "openai"),
          ...(taskHeader === undefined
            ? {}
            : { "x-gradiated-task": taskHeader }),
        },
        json: CHAT.body(providerModel("openai")),
      });

    const skippedResponse = await send(skipped, task);
    const sentinelResponse = await send(sentinel, "sentinel");

    expect(skippedResponse.status).toBe(200);
    await capturedFor(
      String(sentinelResponse.headers["x-gradiated-generation-id"]),
    );
    expect(
      collector.lines.filter((line) => line.workspace_id === skipped.workspace),
    ).toEqual([]);
  });

  it("streams to the client at full speed while the collector hangs", async () => {
    const proxy = await fixture.startProxy(collector.env());
    const instance = await makeCase("vllm");
    await enableCapture(instance);
    collector.hang = true;

    try {
      for (let request = 0; request < 3; request += 1) {
        fixture.provider.reply({ chunks: STREAM });
        const started = Date.now();

        const response = await proxy.client.post(MESSAGES.path, {
          headers: {
            ...relayHeaders(instance, "anthropic"),
            "x-gradiated-task": "hung-collector",
          },
          json: { ...MESSAGES.body(providerModel("anthropic")), stream: true },
        });

        expect(response.status).toBe(200);
        expect(response.text).toBe(STREAM.join(""));
        expect(Date.now() - started).toBeLessThan(1000);
      }

      await eventually(() =>
        collector.lines.some((line) => line.task === "hung-collector"),
      );
    } finally {
      collector.hang = false;
    }
  });

  it("drops oversized capture metadata without changing the client response", async () => {
    const proxy = await fixture.startProxy({
      ...collector.env(),
      PROXY_CAPTURE_BUFFER_BYTES: "1024",
    });
    const instance = await makeCase("vllm");
    await enableCapture(instance);
    fixture.provider.reply({ chunks: STREAM });

    const response = await proxy.client.post(MESSAGES.path, {
      headers: {
        ...relayHeaders(instance, "anthropic"),
        "x-gradiated-task": "metadata-budget",
        "x-gradiated-session-id": "s".repeat(2048),
      },
      json: { ...MESSAGES.body(providerModel("anthropic")), stream: true },
    });

    expect(response.status).toBe(200);
    expect(response.text).toBe(STREAM.join(""));
    const metrics = (await proxy.admin.get("/metrics")).text;
    expect(metrics).toContain(
      'gradiated_proxy_captures_total{result="full"} 1',
    );
    expect(
      collector.lines.some(
        (line) =>
          line.generation_id === response.headers["x-gradiated-generation-id"],
      ),
    ).toBe(false);
  });

  it("forwards compressed bytes unchanged and counts the unsupported capture", async () => {
    const proxy = await fixture.startProxy(collector.env());
    const instance = await makeCase("vllm");
    await enableCapture(instance);
    const compressed = gzipSync(
      '{"choices":[{"message":{"content":"Synthetic"}}]}',
    );
    fixture.provider.reply({
      body: compressed,
      headers: {
        "content-type": "application/json",
        "content-encoding": "gzip",
      },
    });

    const response = await proxy.client.stream(CHAT.path, {
      headers: {
        ...relayHeaders(instance, "openai"),
        "x-gradiated-task": "compressed",
        "accept-encoding": "gzip",
      },
      json: CHAT.body(providerModel("openai")),
    });
    const chunks: Buffer[] = [];
    for await (const chunk of response.message) chunks.push(Buffer.from(chunk));

    expect(response.status).toBe(200);
    expect(response.headers["content-encoding"]).toBe("gzip");
    expect(Buffer.concat(chunks)).toEqual(compressed);
    expect((await proxy.admin.get("/metrics")).text).toContain(
      'gradiated_proxy_captures_total{result="unsupported"} 1',
    );
    expect(
      collector.lines.some(
        (line) =>
          line.generation_id === response.headers["x-gradiated-generation-id"],
      ),
    ).toBe(false);
  });

  it("sends queued generations before the proxy exits on SIGTERM", async () => {
    const proxy = await fixture.startProxy(collector.env());
    const instance = await makeCase("vllm");
    await enableCapture(instance);

    const response = await proxy.client.post(CHAT.path, {
      headers: {
        ...relayHeaders(instance, "openai"),
        "x-gradiated-task": "drain",
      },
      json: CHAT.body(providerModel("openai")),
    });
    proxy.signal("SIGTERM");

    expect(await proxy.exit(20_000)).toEqual({ code: 0, signal: null });
    expect(collector.lines.map((line) => line.generation_id)).toContain(
      response.headers["x-gradiated-generation-id"],
    );
  });
});
