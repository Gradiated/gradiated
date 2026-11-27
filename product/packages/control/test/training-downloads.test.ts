import { createHash } from "node:crypto";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { send, sign } = vi.hoisted(() => ({ send: vi.fn(), sign: vi.fn() }));
vi.mock("@aws-sdk/client-s3", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@aws-sdk/client-s3")>()),
  S3Client: class {
    send = send;
  },
}));
vi.mock("@aws-sdk/s3-request-presigner", () => ({ getSignedUrl: sign }));
import { ObjectStorage } from "../src/storage/object-storage.js";
import { createAdapterDownloads } from "../src/training/downloads.js";
import {
  archive,
  matrix,
  random,
  safetensors,
  tarEntry,
} from "./support/adapter-archive.js";

const run = "0198ae50-94d8-7d4d-a8be-9f9b44b8c774";
const sha = "a".repeat(64);
const checksum = Buffer.from(sha, "hex").toString("base64");
const uri = `s3://artifacts/runs/${run}/output/1/adapter.tar.gz`;
beforeEach(() => {
  vi.resetAllMocks();
  send.mockResolvedValue({
    ContentLength: 123,
    VersionId: "published-revision",
    ChecksumSHA256: checksum,
    ChecksumType: "FULL_OBJECT",
  });
  sign.mockResolvedValue("https://storage.example/archive?signature=test");
});
it("signs a bounded attachment link for the verified archive", async () => {
  const result = await createAdapterDownloads(
    new ObjectStorage("artifacts"),
  ).sign(uri, run, 123, sha);
  expect(send.mock.calls[0]![0].input).toEqual({
    ChecksumMode: "ENABLED",
    Bucket: "artifacts",
    Key: `runs/${run}/output/1/adapter.tar.gz`,
  });
  expect(sign.mock.calls[0]![1].input).toMatchObject({
    VersionId: "published-revision",
    ResponseContentDisposition: 'attachment; filename="adapter.tar.gz"',
    ResponseContentType: "application/gzip",
  });
  expect(sign.mock.calls[0]![2]).toEqual({ expiresIn: 300 });
  expect(Date.parse(result.expires_at) - Date.now()).toBeLessThanOrEqual(
    300_000,
  );
  expect(result.url).toContain("https://storage.example/");
});
it.each([
  uri.replace("artifacts", "foreign"),
  uri.replace(run, "another-run"),
  `s3://artifacts/runs/${run}/../private.tar.gz`,
  `https://example.com/adapter.tar.gz`,
  uri.replace("adapter.tar.gz", "adapter/"),
])("rejects an archive outside the configured run: %s", async (candidate) => {
  await expect(
    createAdapterDownloads(new ObjectStorage("artifacts")).sign(
      candidate,
      run,
      123,
      sha,
    ),
  ).rejects.toThrow("unavailable");
  expect(send).not.toHaveBeenCalled();
  expect(sign).not.toHaveBeenCalled();
});
it("signs a grad artifact bundle in the training bucket for its workspace only", async () => {
  const workspace = "0198ae50-94d8-7d4d-a8be-9f9b44b8c775";
  const bundle = `s3://grad-training/artifacts/${workspace}/${sha}.grad.tar.gz`;
  const downloads = createAdapterDownloads(
    new ObjectStorage("artifacts"),
    new ObjectStorage("grad-training"),
  );

  await downloads.sign(bundle, run, 123, sha, workspace);
  expect(send.mock.calls[0]![0].input).toMatchObject({
    Bucket: "grad-training",
    Key: `artifacts/${workspace}/${sha}.grad.tar.gz`,
  });

  for (const [candidate, scope, digest] of [
    [bundle, run, sha],
    [bundle.replace(sha, "b".repeat(64)), workspace, sha],
    [bundle.replace("grad-training", "artifacts"), workspace, sha],
  ] as const)
    await expect(
      downloads.sign(candidate, run, 123, digest, scope),
    ).rejects.toThrow("unavailable");
  expect(send).toHaveBeenCalledTimes(1);
});
it("signs a cartridge file under its version", async () => {
  const cartridge = `s3://artifacts/cartridges/${run}/${sha}/cartridge.safetensors`;
  await createAdapterDownloads(new ObjectStorage("artifacts")).sign(
    cartridge,
    run,
    123,
    sha,
  );

  expect(sign.mock.calls[0]![1].input).toMatchObject({
    Key: `cartridges/${run}/${sha}/cartridge.safetensors`,
    ResponseContentDisposition: 'attachment; filename="cartridge.safetensors"',
    ResponseContentType: "application/octet-stream",
  });
});
it.each([
  `s3://artifacts/cartridges/another-run/${sha}/cartridge.safetensors`,
  `s3://artifacts/cartridges/${run}/${sha}/other.safetensors`,
])(
  "rejects a cartridge outside the configured version: %s",
  async (candidate) => {
    await expect(
      createAdapterDownloads(new ObjectStorage("artifacts")).sign(
        candidate,
        run,
        123,
        sha,
      ),
    ).rejects.toThrow("unavailable");
    expect(sign).not.toHaveBeenCalled();
  },
);
it("does not sign missing or truncated objects", async () => {
  send.mockRejectedValueOnce(new Error("NoSuchKey"));
  await expect(
    createAdapterDownloads(new ObjectStorage("artifacts")).sign(
      uri,
      run,
      123,
      sha,
    ),
  ).rejects.toThrow("could not be downloaded");
  send.mockResolvedValueOnce({ ContentLength: 12 });
  await expect(
    createAdapterDownloads(new ObjectStorage("artifacts")).sign(
      uri,
      run,
      123,
      sha,
    ),
  ).rejects.toThrow("could not be downloaded");
  expect(sign).not.toHaveBeenCalled();
});

it("rejects equal-sized replacement bytes and unversioned storage", async () => {
  send.mockResolvedValueOnce({
    ContentLength: 123,
    VersionId: "replacement",
    ChecksumSHA256: "different",
    ChecksumType: "FULL_OBJECT",
  });
  await expect(
    createAdapterDownloads(new ObjectStorage("artifacts")).sign(
      uri,
      run,
      123,
      sha,
    ),
  ).rejects.toThrow("could not be downloaded");
  send.mockResolvedValueOnce({ ContentLength: 123 });
  await expect(
    createAdapterDownloads(new ObjectStorage("artifacts")).sign(
      uri,
      run,
      123,
      sha,
    ),
  ).rejects.toThrow("could not be downloaded");
  expect(sign).not.toHaveBeenCalled();
});

it("hashes archives without an S3 SHA256 and signs the verified version", async () => {
  const bytes = Buffer.from("published bytes");
  const digest = createHash("sha256").update(bytes).digest("hex");
  send.mockResolvedValueOnce({
    ContentLength: bytes.length,
    VersionId: "original",
  });
  send.mockResolvedValueOnce({
    Body: {
      transformToWebStream: () =>
        new ReadableStream({
          start(controller) {
            controller.enqueue(bytes);
            controller.close();
          },
        }),
    },
  });
  await createAdapterDownloads(new ObjectStorage("artifacts")).sign(
    uri,
    run,
    bytes.length,
    digest,
  );
  expect(send.mock.calls[1]![0].input.VersionId).toBe("original");
  expect(sign.mock.calls[0]![1].input.VersionId).toBe("original");
});

describe("adapter weight summaries", () => {
  const next = random(9);
  const gz = archive(
    tarEntry(
      "adapter_config.json",
      Buffer.from(JSON.stringify({ r: 2, lora_alpha: 4 })),
    ),
    tarEntry(
      "adapter_model.safetensors",
      safetensors([
        {
          name: "model.layers.0.self_attn.q_proj.lora_A.weight",
          matrix: matrix(2, 8, next),
        },
        {
          name: "model.layers.0.self_attn.q_proj.lora_B.weight",
          matrix: matrix(8, 2, next),
        },
      ]),
    ),
  );
  const digest = createHash("sha256").update(gz).digest("hex");
  const cacheKey = `runs/${run}/output/adapter-weights/${digest}.v1.json`;
  const body = (bytes: Uint8Array) => ({
    ContentLength: bytes.length,
    Body: {
      transformToWebStream: () =>
        new ReadableStream({
          start(controller) {
            controller.enqueue(bytes);
            controller.close();
          },
        }),
    },
  });
  const objects = new Map<string, Uint8Array>();
  const storage = (archiveBytes: Uint8Array = gz) => {
    send.mockImplementation(
      async (command: { input: Record<string, unknown> }) => {
        const { Key, Body } = command.input as {
          Key: string;
          Body?: Uint8Array;
        };
        const name = command.constructor.name;
        if (name === "HeadObjectCommand")
          return { ContentLength: archiveBytes.length, VersionId: "published" };
        if (name === "PutObjectCommand") {
          objects.set(Key, Body!);
          return {};
        }
        if (Key.endsWith(".tar.gz")) return body(archiveBytes);
        const cached = objects.get(Key);
        if (!cached)
          throw Object.assign(new Error("NoSuchKey"), { name: "NoSuchKey" });
        return body(cached);
      },
    );
    return createAdapterDownloads(new ObjectStorage("artifacts"));
  };
  const reads = () =>
    send.mock.calls.filter(
      ([command]) =>
        command.constructor.name === "GetObjectCommand" &&
        String(command.input.Key).endsWith(".tar.gz"),
    );

  beforeEach(() => objects.clear());

  it("summarizes the verified archive version once, then serves the cache", async () => {
    const downloads = storage();
    const [first, concurrent] = await Promise.all([
      downloads.weights!(uri, run, gz.length, digest),
      downloads.weights!(uri, run, gz.length, digest),
    ]);
    expect(first).toEqual(concurrent);
    expect(first.modules).toMatchObject([
      { layer: 0, module: "self_attn.q_proj", shape: [8, 8], rank: 2 },
    ]);
    expect(reads()).toHaveLength(1);
    expect(reads()[0]![0].input.VersionId).toBe("published");
    expect(JSON.parse(Buffer.from(objects.get(cacheKey)!).toString())).toEqual(
      first,
    );

    expect(await storage().weights!(uri, run, gz.length, digest)).toEqual(
      first,
    );
    expect(reads()).toHaveLength(1);
  });

  it("refuses and does not cache an archive whose bytes differ from the version", async () => {
    const tampered = Buffer.from(gz);
    tampered[tampered.length - 1]! ^= 1;
    await expect(
      storage(tampered).weights!(uri, run, gz.length, digest),
    ).rejects.toThrow("could not be summarized");
    await expect(
      storage().weights!(uri, run, gz.length, "b".repeat(64)),
    ).rejects.toThrow("could not be summarized");
    expect(objects.size).toBe(0);
  });

  it("does not read archives outside the version's run", async () => {
    await expect(
      storage().weights!(
        uri.replace(run, "another-run"),
        run,
        gz.length,
        digest,
      ),
    ).rejects.toThrow("unavailable");
    expect(send).not.toHaveBeenCalled();
  });
});
