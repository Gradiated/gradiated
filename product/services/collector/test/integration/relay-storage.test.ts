import * as zlib from "node:zlib";
import {
  GetObjectCommand,
  GetObjectTaggingCommand,
  ListObjectsV2Command,
} from "@aws-sdk/client-s3";
import { afterAll, beforeAll, expect, it } from "vitest";

import { useCases } from "../../../gateway/test/integration/case.js";
import {
  deferred,
  eventually,
} from "../../../gateway/test/integration/eventually.js";
import {
  CHAT,
  providerModel,
  relayHeaders,
  useProxy,
} from "../../../proxy/test/e2e/support/fixtures.js";
import { startCollector, token } from "../support/process.js";
import { bucket, connectS3 } from "../support/s3.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);
const s3 = () => connectS3();
let collector: Awaited<ReturnType<typeof startCollector>>;

beforeAll(async () => {
  collector = await startCollector();
});
afterAll(async () => {
  await collector?.close();
});

it.each([200, 500])(
  "persists a real proxy relay with status %i through collector validation and S3 range reads",
  async (status) => {
    const instance = await makeCase("vllm");
    await instance.database.query(
      "update workspaces set trace_capture_enabled = true, trace_retention_days = 90 where id = $1",
      [instance.workspace],
    );
    const proxy = await fixture.startProxy({
      PROXY_COLLECTOR_URL: collector.url,
      PROXY_COLLECTOR_TOKEN: token,
    });
    const request = JSON.stringify(CHAT.body(providerModel("openai")));
    const body =
      status === 200
        ? '{"choices":[{"message":{"content":"Captured answer"}}]}'
        : '{"error":{"message":"Synthetic failure"}}';
    fixture.provider.reply({
      status,
      body,
      headers: { "content-type": "application/json" },
    });
    const response = await proxy.client.post(CHAT.path, {
      headers: {
        ...relayHeaders(instance, "openai"),
        "content-type": "application/json",
        "x-gradiated-task": "capture-storage",
        "x-gradiated-trace-id": "integration-trace",
      },
      content: request,
    });
    expect(response.status).toBe(status);
    expect(response.text).toBe(body);
    const generation = response.headers["x-gradiated-generation-id"];
    const client = s3();

    try {
      const key = await eventually(
        async () => {
          const listed = await client.send(
            new ListObjectsV2Command({
              Bucket: bucket,
              Prefix: `v1/ws=${instance.workspace}/`,
            }),
          );
          return listed.Contents?.find((object) =>
            object.Key?.endsWith(".manifest.json"),
          )?.Key;
        },
        10_000,
        "collector uploaded the captured manifest",
      );
      const manifestResponse = await client.send(
        new GetObjectCommand({ Bucket: bucket, Key: key }),
      );
      const manifest = JSON.parse(
        await manifestResponse.Body!.transformToString(),
      ) as {
        generations: {
          generation_id: string;
          offset: number;
          length: number;
          workspace_id: string;
          source: string;
          trainable: boolean;
          status: number;
          retention_days: number;
        }[];
      };
      expect(manifest.generations).toHaveLength(1);
      const row = manifest.generations[0]!;
      expect(row).toMatchObject({
        generation_id: generation,
        workspace_id: instance.workspace,
        source: "relay",
        status,
        retention_days: 90,
        trainable: false,
      });
      const dataKey = key.replace(/\.manifest\.json$/, ".jsonl.zst");
      const frame = await client.send(
        new GetObjectCommand({
          Bucket: bucket,
          Key: dataKey,
          Range: `bytes=${row.offset}-${row.offset + row.length - 1}`,
        }),
      );
      const decompress = (
        zlib as unknown as { zstdDecompressSync(bytes: Uint8Array): Buffer }
      ).zstdDecompressSync;
      const record = JSON.parse(
        decompress(await frame.Body!.transformToByteArray()).toString(),
      );
      expect(record).toMatchObject({
        generation_id: generation,
        workspace_id: instance.workspace,
        task: "capture-storage",
        trace_id: "integration-trace",
        raw: { request: JSON.parse(request), response: JSON.parse(body) },
      });
      expect(JSON.stringify(record)).not.toContain(instance.key);
      expect(JSON.stringify(record)).not.toContain("Bearer");
      const tags = await client.send(
        new GetObjectTaggingCommand({ Bucket: bucket, Key: dataKey }),
      );
      expect(tags.TagSet).toEqual(
        expect.arrayContaining([
          { Key: "retention", Value: "90d" },
          { Key: "trainable", Value: "false" },
        ]),
      );
      const task = await eventually(
        async () =>
          (
            await instance.database.query(
              "select name from tasks where workspace_id = $1",
              [instance.workspace],
            )
          ).rows[0],
      );
      expect(task.name).toBe("capture-storage");
    } finally {
      client.destroy();
    }
  },
);

it.each(["complete", "cancelled"] as const)(
  "persists a %s streamed relay through the real collector",
  async (outcome) => {
    const instance = await makeCase("vllm");
    await instance.database.query(
      "update workspaces set trace_capture_enabled = true where id = $1",
      [instance.workspace],
    );
    const proxy = await fixture.startProxy({
      PROXY_COLLECTOR_URL: collector.url,
      PROXY_COLLECTOR_TOKEN: token,
    });
    const gate = deferred();
    const first =
      'data: {"id":"chat-integration","choices":[{"index":0,"delta":{"role":"assistant","content":"Partial"},"finish_reason":null}]}\n\n';
    const end =
      'data: {"id":"chat-integration","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n';
    fixture.provider.reply({
      chunks: [first, end],
      ...(outcome === "cancelled" ? { afterFirstChunk: gate } : {}),
    });
    const response = await proxy.client.stream(CHAT.path, {
      headers: {
        ...relayHeaders(instance, "openai"),
        "x-gradiated-task": "stream-storage",
      },
      json: { ...CHAT.body(providerModel("openai")), stream: true },
    });
    try {
      let text = "";
      for await (const chunk of response.message) {
        text += String(chunk);
        if (outcome === "cancelled") break;
      }
      expect(text).toContain("Partial");
      if (outcome === "complete") expect(text).toBe(first + end);
      else await fixture.provider.requests[0]!.abandoned.promise;

      const client = s3();
      try {
        const key = await eventually(
          async () => {
            const listed = await client.send(
              new ListObjectsV2Command({
                Bucket: bucket,
                Prefix: `v1/ws=${instance.workspace}/`,
              }),
            );
            return listed.Contents?.find((object) =>
              object.Key?.endsWith(".manifest.json"),
            )?.Key;
          },
          10_000,
          "stream capture persisted",
        );
        const manifestResponse = await client.send(
          new GetObjectCommand({ Bucket: bucket, Key: key }),
        );
        const manifest = JSON.parse(
          await manifestResponse.Body!.transformToString(),
        );
        expect(manifest.generations).toHaveLength(1);
        const row = manifest.generations[0];
        expect(row).toMatchObject({
          generation_id: response.headers["x-gradiated-generation-id"],
          outcome,
          trainable: false,
        });
        const dataKey = key.replace(/\.manifest\.json$/, ".jsonl.zst");
        const frame = await client.send(
          new GetObjectCommand({
            Bucket: bucket,
            Key: dataKey,
            Range: `bytes=${row.offset}-${row.offset + row.length - 1}`,
          }),
        );
        const decompress = (
          zlib as unknown as { zstdDecompressSync(bytes: Uint8Array): Buffer }
        ).zstdDecompressSync;
        const record = JSON.parse(
          decompress(await frame.Body!.transformToByteArray()).toString(),
        );
        expect(record).toMatchObject({
          outcome,
          streamed: true,
          raw: { response: { choices: [{ message: { content: "Partial" } }] } },
        });
      } finally {
        client.destroy();
      }
    } finally {
      gate.resolve();
    }
  },
);
