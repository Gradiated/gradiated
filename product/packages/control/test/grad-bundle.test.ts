import { mkdtemp, readdir, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { readGradBundle } from "../src/training/grad-bundle.js";
import { gradBundle, tarGz } from "./support/grad-bundle.js";

const files = {
  "adapter_config.json": Buffer.from('{"r":2}'),
  "adapter_model.safetensors": Buffer.from("weights"),
};
const keep = new Set(Object.keys(files));
const directories: string[] = [];

const read = async (
  bundle: { bytes: Buffer; sha256: string; sizeBytes: number },
  overrides: { sha256?: string; sizeBytes?: number } = {},
) => {
  const directory = await mkdtemp(join(tmpdir(), "grad-bundle-test-"));
  directories.push(directory);
  const chunks = async function* () {
    for (let offset = 0; offset < bundle.bytes.length; offset += 7)
      yield bundle.bytes.subarray(offset, offset + 7);
  };
  const result = await readGradBundle(chunks(), {
    directory,
    keep,
    sizeBytes: overrides.sizeBytes ?? bundle.sizeBytes,
    sha256: overrides.sha256 ?? bundle.sha256,
    maxUnpackedBytes: 1024 * 1024,
  });
  return { directory, ...result };
};

afterEach(async () => {
  await Promise.all(
    directories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

describe("grad bundle reader", () => {
  it("extracts the payload it keeps and returns the manifest", async () => {
    const {
      directory,
      manifest,
      files: written,
    } = await read(gradBundle(files));

    expect(manifest).toMatchObject({ format: "peft_lora", format_version: 1 });
    expect((await readdir(directory)).sort()).toEqual(Object.keys(files));
    expect(
      await readFile(written.get("adapter_model.safetensors")!.path, "utf8"),
    ).toBe("weights");
  });

  it("checks the bundle's own SHA-256 and size", async () => {
    const bundle = gradBundle(files);
    await expect(read(bundle, { sha256: "0".repeat(64) })).rejects.toThrow(
      "SHA-256",
    );
    await expect(
      read(bundle, { sizeBytes: bundle.sizeBytes - 1 }),
    ).rejects.toThrow("declared size");
  });

  it.each([
    [
      "a payload checksum mismatch",
      gradBundle(files, {
        manifest: {
          files: {
            ...Object.fromEntries(
              Object.keys(files).map((name) => [name, "0".repeat(64)]),
            ),
          },
        },
      }),
      "don't match",
    ],
    [
      "an undeclared file",
      gradBundle(files, {
        extra: [{ name: "trainer_state/optimizer.pt", body: Buffer.from("x") }],
      }),
      "don't match",
    ],
    [
      "an eval report without its checksum",
      gradBundle(files, {
        extra: [{ name: "eval_report.json", body: Buffer.from("{}") }],
      }),
      "eval_report",
    ],
    [
      "a symlink",
      gradBundle(files, {
        extra: [{ name: "link", body: Buffer.alloc(0), type: "2" }],
      }),
      "regular files",
    ],
    [
      "a path that escapes",
      gradBundle(files, {
        extra: [{ name: "../escape", body: Buffer.from("x") }],
      }),
      "unsafe path",
    ],
    [
      "an unknown envelope",
      gradBundle(files, { manifest: { schema: "grad.artifact/2" } }),
      "manifest.json is invalid",
    ],
  ])("rejects %s", async (_name, bundle, message) => {
    await expect(read(bundle)).rejects.toThrow(message);
  });

  it("rejects duplicate entries and a missing manifest", async () => {
    const duplicate = tarGz([
      { name: "adapter_config.json", body: Buffer.from("{}") },
      { name: "adapter_config.json", body: Buffer.from("{}") },
    ]);
    const missing = tarGz([
      { name: "adapter_config.json", body: Buffer.from("{}") },
    ]);
    const sha = (bytes: Buffer) =>
      import("node:crypto").then(({ createHash }) =>
        createHash("sha256").update(bytes).digest("hex"),
      );

    await expect(
      read({
        bytes: duplicate,
        sha256: await sha(duplicate),
        sizeBytes: duplicate.length,
      }),
    ).rejects.toThrow("duplicate");
    await expect(
      read({
        bytes: missing,
        sha256: await sha(missing),
        sizeBytes: missing.length,
      }),
    ).rejects.toThrow("no manifest");
  });
});
