import { createHash } from "node:crypto";
import { expect, it, vi } from "vitest";
import { createTrainingArtifacts } from "../src/training/artifacts.js";

const key = "runs/0198ae50-94d8-7d4d-a8be-9f9b44b8c774/output/adapter.tar.gz";
const storage = () => ({
  put: vi.fn(async (_key: string, _bytes: Uint8Array, _options?: object) => {}),
  tag: vi.fn(async (_key: string, _tags: object) => {}),
  read: vi.fn(async () => Buffer.from("adapter")),
  exists: vi.fn(async () => true),
  signDownload: vi.fn(async () => "https://storage.example/download"),
  signUpload: vi.fn(async () => "https://storage.example/upload"),
  uri: (key: string) => `s3://objects/${key}`,
});

it("uses injected storage while retaining artifact integrity checks", async () => {
  const objects = storage();
  const artifacts = createTrainingArtifacts(objects);
  const bytes = Buffer.from("adapter");
  const artifact = await artifacts.put(key, bytes);
  expect(artifact).toEqual({
    key,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    size_bytes: bytes.length,
  });
  expect(objects.put).toHaveBeenCalledWith(key, bytes, {});
  await artifacts.verify(artifact);
  expect(objects.read).toHaveBeenCalledWith(key, {
    maxBytes: 256 * 1024 * 1024,
  });
  objects.read.mockResolvedValueOnce(Buffer.from("corrupt"));
  await expect(artifacts.verify(artifact)).rejects.toThrow("integrity");
});

it.each(["private/key", key.replace("output", "../private")])(
  "rejects invalid artifact paths before touching storage: %s",
  async (invalid) => {
    const objects = storage();
    const artifacts = createTrainingArtifacts(objects);
    await expect(
      artifacts.put(invalid, Buffer.from("adapter")),
    ).rejects.toThrow("Invalid training artifact key");
    expect(objects.put).not.toHaveBeenCalled();
    await expect(artifacts.upload(invalid)).rejects.toThrow(
      "Invalid training artifact key",
    );
    expect(objects.signUpload).not.toHaveBeenCalled();
    await expect(artifacts.markExpiring(invalid)).rejects.toThrow(
      "Invalid training artifact key",
    );
    expect(objects.tag).not.toHaveBeenCalled();
  },
);

it("tags expiring training inputs for the 90-day lifecycle rule", async () => {
  const objects = storage();
  const artifacts = createTrainingArtifacts(objects);
  const dataset = key.replace(
    "output/adapter.tar.gz",
    "dataset/v1/train.jsonl",
  );
  await artifacts.put(dataset, Buffer.from("rows"), { expiring: true });
  expect(objects.put).toHaveBeenCalledWith(dataset, Buffer.from("rows"), {
    tags: { retention: "90d" },
  });

  const checkpoint = key.replace("output/adapter", "checkpoints/0/10");
  await artifacts.markExpiring(checkpoint);
  expect(objects.tag).toHaveBeenCalledWith(checkpoint, { retention: "90d" });
});
