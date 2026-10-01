import { createHash } from "node:crypto";
import { beforeEach, expect, it, vi } from "vitest";

const { send } = vi.hoisted(() => ({ send: vi.fn() }));
vi.mock("@aws-sdk/client-s3", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@aws-sdk/client-s3")>()),
  S3Client: class {
    send = send;
  },
}));
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
