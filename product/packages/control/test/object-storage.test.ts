import { createHash } from "node:crypto";
import { beforeEach, expect, it, vi } from "vitest";

const { send } = vi.hoisted(() => ({ send: vi.fn() }));
vi.mock("@aws-sdk/client-s3", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@aws-sdk/client-s3")>()),
  S3Client: class {
    send = send;
  },
}));
import { PutObjectTaggingCommand } from "@aws-sdk/client-s3";
import { ObjectStorage } from "../src/storage/object-storage.js";

beforeEach(() => vi.resetAllMocks());

it.each([undefined, 1, 20])(
  "bounds streamed reads regardless of advertised length: %s",
  async (length) => {
    const cancelled = vi.fn();
    send.mockResolvedValue({
      ContentLength: length,
      Body: {
        transformToWebStream: () =>
          new ReadableStream({
            start(controller) {
              controller.enqueue(Buffer.from("abc"));
              controller.enqueue(Buffer.from("def"));
            },
            cancel: cancelled,
          }),
      },
    });
    await expect(
      new ObjectStorage("objects").read("key", { maxBytes: 4 }),
    ).rejects.toThrow("read limit");
    expect(cancelled).toHaveBeenCalledOnce();
  },
);

it("hashes the requested immutable version across stream chunks", async () => {
  send.mockResolvedValue({
    Body: {
      transformToWebStream: () =>
        new ReadableStream({
          start(controller) {
            controller.enqueue(Buffer.from("abc"));
            controller.enqueue(Buffer.from("def"));
            controller.close();
          },
        }),
    },
  });
  expect(
    await new ObjectStorage("objects").checksum("key", {
      versionId: "original",
      maxBytes: 6,
    }),
  ).toEqual({
    sha256: createHash("sha256").update("abcdef").digest("hex"),
    sizeBytes: 6,
  });
  expect(send.mock.calls[0]![0].input.VersionId).toBe("original");
});

it("distinguishes missing objects from authorization or storage failures", async () => {
  const storage = new ObjectStorage("objects");
  send.mockRejectedValueOnce(
    Object.assign(new Error("missing"), { name: "NotFound" }),
  );
  expect(await storage.exists("key")).toBe(false);
  const error = Object.assign(new Error("denied"), { name: "AccessDenied" });
  send.mockRejectedValueOnce(error);
  await expect(storage.exists("key")).rejects.toBe(error);
});

it("ignores multipart checksum metadata rather than treating it as a file digest", async () => {
  send.mockResolvedValue({
    ContentLength: 10,
    VersionId: "original",
    ChecksumSHA256: "multipart",
    ChecksumType: "COMPOSITE",
  });
  expect(await new ObjectStorage("objects").head("key", true)).toEqual({
    sizeBytes: 10,
    versionId: "original",
    sha256: undefined,
  });
});

it("writes S3 lifecycle tags only when a write asks for them", async () => {
  send.mockResolvedValue({});
  const storage = new ObjectStorage("objects");
  await storage.put("plain", Buffer.from("a"));
  await storage.put("expiring", Buffer.from("b"), {
    tags: { retention: "90d", "a b": "c&d" },
  });
  expect(send.mock.calls[0]![0].input).not.toHaveProperty("Tagging");
  expect(send.mock.calls[1]![0].input.Tagging).toBe("retention=90d&a+b=c%26d");
});

it("replaces an existing object's tag set", async () => {
  send.mockResolvedValue({});
  await new ObjectStorage("objects").tag("key", { retention: "90d" });
  const command = send.mock.calls[0]![0];
  expect(command).toBeInstanceOf(PutObjectTaggingCommand);
  expect(command.input).toEqual({
    Bucket: "objects",
    Key: "key",
    Tagging: { TagSet: [{ Key: "retention", Value: "90d" }] },
  });
});

it("streams a download to disk and enforces its read limit", async () => {
  const { mkdtemp, readFile, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const directory = await mkdtemp(join(tmpdir(), "object-download-test-"));
  const cancelled = vi.fn();
  const response = () => ({
    Body: {
      transformToWebStream: () =>
        new ReadableStream({
          start(controller) {
            controller.enqueue(Buffer.from("abc"));
            controller.enqueue(Buffer.from("def"));
            controller.close();
          },
          cancel: cancelled,
        }),
    },
  });
  try {
    send.mockResolvedValue(response());
    const storage = new ObjectStorage("objects");
    const path = join(directory, "download");
    expect(await storage.downloadFile("key", path, { maxBytes: 6 })).toBe(6);
    expect(await readFile(path, "utf8")).toBe("abcdef");
    send.mockResolvedValue(response());
    await expect(
      storage.downloadFile("key", join(directory, "oversize"), { maxBytes: 4 }),
    ).rejects.toThrow("read limit");
    expect(await readFile(join(directory, "oversize"), "utf8")).toBe("abc");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

it("uploads from a file stream with a fixed length and checksum and closes it on failure", async () => {
  const { mkdtemp, writeFile, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const directory = await mkdtemp(join(tmpdir(), "object-upload-test-"));
  try {
    const path = join(directory, "archive");
    await writeFile(path, "abcdef");
    const sha256 = createHash("sha256").update("abcdef").digest("hex");
    let body: import("node:fs").ReadStream | undefined;
    send.mockImplementationOnce(async (command) => {
      expect(command.input.ContentLength).toBe(6);
      expect(command.input.ChecksumSHA256).toBe(
        Buffer.from(sha256, "hex").toString("base64"),
      );
      body = command.input.Body;
      const chunks: Buffer[] = [];
      for await (const chunk of body!) chunks.push(chunk as Buffer);
      expect(Buffer.concat(chunks).toString()).toBe("abcdef");
    });
    const storage = new ObjectStorage("objects");
    await storage.putFile("key", path, { sizeBytes: 6, sha256 });
    expect(body!.destroyed).toBe(true);
    send.mockImplementationOnce(async (command) => {
      body = command.input.Body;
      throw new Error("Storage failed");
    });
    await expect(
      storage.putFile("key", path, { sizeBytes: 6, sha256 }),
    ).rejects.toThrow("Storage failed");
    expect(body!.destroyed).toBe(true);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

it("deletes only the requested staging keys and rejects partial deletion failures", async () => {
  const storage = new ObjectStorage("objects");
  const keys = [
    "uploads/id/adapter_config.json",
    "uploads/id/adapter_model.safetensors",
  ];
  send.mockResolvedValueOnce({});
  await storage.delete(keys);
  expect(send.mock.calls[0]![0].input).toMatchObject({
    Bucket: "objects",
    Delete: { Objects: keys.map((Key) => ({ Key })), Quiet: true },
  });
  send.mockResolvedValueOnce({
    Errors: [{ Key: keys[0], Code: "AccessDenied" }],
  });
  await expect(storage.delete(keys)).rejects.toThrow("Object deletion failed");
});

it("copies the exact uploaded version without retaining staging tags", async () => {
  send.mockResolvedValue({});
  await new ObjectStorage("objects").copy(
    "uploads/a b/report.md",
    "version-files/version/file",
    "v+1/2",
  );
  expect(send.mock.calls[0]![0].input).toEqual({
    Bucket: "objects",
    Key: "version-files/version/file",
    CopySource: "objects/uploads/a%20b/report.md?versionId=v%2B1%2F2",
    TaggingDirective: "REPLACE",
  });
});
