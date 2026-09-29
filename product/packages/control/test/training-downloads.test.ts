import { createHash } from "node:crypto";
import { beforeEach, expect, it, vi } from "vitest";

const { send, sign } = vi.hoisted(() => ({ send: vi.fn(), sign: vi.fn() }));
vi.mock("@aws-sdk/client-s3", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@aws-sdk/client-s3")>()),
  S3Client: class {
    send = send;
  },
}));
vi.mock("@aws-sdk/s3-request-presigner", () => ({ getSignedUrl: sign }));
import { createAdapterDownloads } from "../src/training/downloads.js";

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
  const result = await createAdapterDownloads("artifacts").sign(
    uri,
    run,
    123,
    sha,
  );
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
    createAdapterDownloads("artifacts").sign(candidate, run, 123, sha),
  ).rejects.toThrow("unavailable");
  expect(send).not.toHaveBeenCalled();
  expect(sign).not.toHaveBeenCalled();
});
it("does not sign missing or truncated objects", async () => {
  send.mockRejectedValueOnce(new Error("NoSuchKey"));
  await expect(
    createAdapterDownloads("artifacts").sign(uri, run, 123, sha),
  ).rejects.toThrow("could not be downloaded");
  send.mockResolvedValueOnce({ ContentLength: 12 });
  await expect(
    createAdapterDownloads("artifacts").sign(uri, run, 123, sha),
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
    createAdapterDownloads("artifacts").sign(uri, run, 123, sha),
  ).rejects.toThrow("could not be downloaded");
  send.mockResolvedValueOnce({ ContentLength: 123 });
  await expect(
    createAdapterDownloads("artifacts").sign(uri, run, 123, sha),
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
  await createAdapterDownloads("artifacts").sign(
    uri,
    run,
    bytes.length,
    digest,
  );
  expect(send.mock.calls[1]![0].input.VersionId).toBe("original");
  expect(sign.mock.calls[0]![1].input.VersionId).toBe("original");
});
