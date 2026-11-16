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

it("persists a binary multipart upload and audio response byte for byte", async () => {
  const instance = await makeCase("vllm");
  await instance.database.query(
    "update workspaces set trace_capture_enabled = true where id = $1",
    [instance.workspace],
  );
  const proxy = await fixture.startProxy({
    PROXY_COLLECTOR_URL: collector.url,
    PROXY_COLLECTOR_TOKEN: token,
  });
  const upload = Buffer.concat([
    Buffer.from(
      '--b0und\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n' +
        '--b0und\r\nContent-Disposition: form-data; name="file"; filename="tone.wav"\r\nContent-Type: audio/wav\r\n\r\n',
    ),
    Buffer.from([0x52, 0x49, 0x46, 0x46, 0xff, 0xfe, 0x00, 0x80]),
    Buffer.from("\r\n--b0und--\r\n"),
  ]);
  const audio = Buffer.from([0x49, 0x44, 0x33, 0x04, 0xff, 0xfb, 0x90, 0x00]);
  fixture.provider.reply({
    body: audio,
    headers: { "content-type": "audio/mpeg" },
  });
  const response = await proxy.client.post("/v1/audio/translations", {
    headers: {
      ...relayHeaders(instance, "openai"),
      "content-type": "multipart/form-data; boundary=b0und",
      "x-gradiated-task": "binary-storage",
    },
    content: upload,
  });
  expect(response.status).toBe(200);
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
      "binary capture persisted",
    );
    const manifest = JSON.parse(
      await (
        await client.send(new GetObjectCommand({ Bucket: bucket, Key: key }))
      ).Body!.transformToString(),
    );
    const row = manifest.generations[0];
    expect(row).toMatchObject({
      generation_id: response.headers["x-gradiated-generation-id"],
      protocol: "openai.http",
      model: "whisper-1",
      source: "relay",
    });
    const frame = await client.send(
      new GetObjectCommand({
        Bucket: bucket,
        Key: key.replace(/\.manifest\.json$/, ".jsonl.zst"),
        Range: `bytes=${row.offset}-${row.offset + row.length - 1}`,
      }),
    );
    const decompress = (
      zlib as unknown as { zstdDecompressSync(bytes: Uint8Array): Buffer }
    ).zstdDecompressSync;
    const record = JSON.parse(
      decompress(await frame.Body!.transformToByteArray()).toString(),
    );
    expect(record.raw.path).toBe("/v1/audio/translations");
    expect(record.raw.request_content_type).toBe(
      "multipart/form-data; boundary=b0und",
    );
    expect(Buffer.from(record.raw.request.data, "base64")).toEqual(upload);
    expect(record.raw.response_content_type).toBe("audio/mpeg");
    expect(Buffer.from(record.raw.response.data, "base64")).toEqual(audio);
  } finally {
    client.destroy();
  }
});

it("persists a request near the 32 MB body limit whole", async () => {
  const instance = await makeCase("vllm");
  await instance.database.query(
    "update workspaces set trace_capture_enabled = true where id = $1",
    [instance.workspace],
  );
  const proxy = await fixture.startProxy({
    PROXY_COLLECTOR_URL: collector.url,
    PROXY_COLLECTOR_TOKEN: token,
  });
  const attachment = Buffer.alloc(23_000_000, 7).toString("base64");
  const request = JSON.stringify({
    ...CHAT.body(providerModel("openai")),
    messages: [
      {
        role: "user",
        content: [
          {
            type: "image_url",
            image_url: { url: `data:image/png;base64,${attachment}` },
          },
        ],
      },
    ],
  });
  expect(request.length).toBeGreaterThan(30_000_000);
  fixture.provider.reply({
    body: '{"choices":[{"message":{"content":"Large"}}]}',
    headers: { "content-type": "application/json" },
  });
  const response = await proxy.client.post(CHAT.path, {
    headers: {
      ...relayHeaders(instance, "openai"),
      "content-type": "application/json",
      "x-gradiated-task": "large-storage",
    },
    content: request,
  });
  expect(response.status).toBe(200);
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
      30_000,
      "large capture persisted",
    );
    const manifest = JSON.parse(
      await (
        await client.send(new GetObjectCommand({ Bucket: bucket, Key: key }))
      ).Body!.transformToString(),
    );
    const row = manifest.generations[0];
    const frame = await client.send(
      new GetObjectCommand({
        Bucket: bucket,
        Key: key.replace(/\.manifest\.json$/, ".jsonl.zst"),
        Range: `bytes=${row.offset}-${row.offset + row.length - 1}`,
      }),
    );
    const decompress = (
      zlib as unknown as {
        zstdDecompressSync(
          bytes: Uint8Array,
          options: { maxOutputLength: number },
        ): Buffer;
      }
    ).zstdDecompressSync;
    const record = JSON.parse(
      decompress(await frame.Body!.transformToByteArray(), {
        maxOutputLength: 128 * 1024 * 1024,
      }).toString(),
    );
    expect(record.generation_id).toBe(
      response.headers["x-gradiated-generation-id"],
    );
    expect(record.raw.request.messages[0].content[0].image_url.url).toBe(
      `data:image/png;base64,${attachment}`,
    );
  } finally {
    client.destroy();
  }
}, 120_000);

it.each(["json", "stream"] as const)(
  "decodes a gzip %s response the client receives compressed",
  async (kind) => {
    const instance = await makeCase("vllm");
    await instance.database.query(
      "update workspaces set trace_capture_enabled = true where id = $1",
      [instance.workspace],
    );
    const proxy = await fixture.startProxy({
      PROXY_COLLECTOR_URL: collector.url,
      PROXY_COLLECTOR_TOKEN: token,
    });
    const plain =
      kind === "json"
        ? '{"choices":[{"message":{"role":"assistant","content":"Unzipped"},"finish_reason":"stop"}]}'
        : 'data: {"id":"c","choices":[{"index":0,"delta":{"role":"assistant","content":"Unzipped"},"finish_reason":null}]}\n\n' +
          'data: {"id":"c","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n';
    const compressed = zlib.gzipSync(plain);
    fixture.provider.reply({
      body: compressed,
      headers: {
        "content-type":
          kind === "json" ? "application/json" : "text/event-stream",
        "content-encoding": "gzip",
      },
    });
    const response = await proxy.client.stream(CHAT.path, {
      headers: {
        ...relayHeaders(instance, "openai"),
        "x-gradiated-task": `gzip-${kind}`,
        "accept-encoding": "gzip, deflate, br",
      },
      json: {
        ...CHAT.body(providerModel("openai")),
        ...(kind === "stream" ? { stream: true } : {}),
      },
    });
    const chunks: Buffer[] = [];
    for await (const chunk of response.message) chunks.push(Buffer.from(chunk));
    expect(response.status).toBe(200);
    expect(response.headers["content-encoding"]).toBe("gzip");
    expect(Buffer.concat(chunks)).toEqual(compressed);
    expect(fixture.provider.requests.at(-1)?.headers["accept-encoding"]).toBe(
      "gzip, deflate, br",
    );
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
        "gzip capture persisted",
      );
      const manifest = JSON.parse(
        await (
          await client.send(new GetObjectCommand({ Bucket: bucket, Key: key }))
        ).Body!.transformToString(),
      );
      const row = manifest.generations[0];
      expect(row).toMatchObject({
        protocol: "openai.chat",
        streamed: kind === "stream",
      });
      const frame = await client.send(
        new GetObjectCommand({
          Bucket: bucket,
          Key: key.replace(/\.manifest\.json$/, ".jsonl.zst"),
          Range: `bytes=${row.offset}-${row.offset + row.length - 1}`,
        }),
      );
      const decompress = (
        zlib as unknown as { zstdDecompressSync(bytes: Uint8Array): Buffer }
      ).zstdDecompressSync;
      const record = JSON.parse(
        decompress(await frame.Body!.transformToByteArray()).toString(),
      );
      expect(record.raw.response.choices[0].message.content).toBe("Unzipped");
    } finally {
      client.destroy();
    }
  },
);
