import { createHash } from "node:crypto";
import { open, type FileHandle } from "node:fs/promises";
import { join } from "node:path";
import { createGunzip } from "node:zlib";
import { Readable } from "node:stream";
import { TextDecoder } from "node:util";
import { z } from "zod";
import { GRAD_ARTIFACT_BUNDLE } from "@gradiated/contracts";

// The limits of grad's hardened reader (docs/ARTIFACT_FORMATS.md, "The bundle").
const MAX_MEMBERS = 1024;
const MAX_MANIFEST_BYTES = 1024 * 1024;
const RESERVED = new Set(["manifest.json", "eval_report.json"]);
const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);

const BundlePathSchema = z
  .string()
  .min(1)
  .max(1024)
  .refine(
    (path) =>
      !path.startsWith("/") &&
      !/[\\\0]/.test(path) &&
      path.split("/").every((part) => part && part !== "." && part !== ".."),
    "Bundle paths must be relative POSIX paths.",
  );

export const GradManifestSchema = z
  .object({
    schema: z.literal(GRAD_ARTIFACT_BUNDLE),
    kind: z.enum(["final", "checkpoint"]),
    format: z.string().min(1),
    format_version: z.number().int().positive(),
    recipe_kind: z.string().min(1),
    base_model: z.string().min(1),
    base_model_repo: z.string().min(1).nullable(),
    base_model_revision: z.string().nullable(),
    deployable: z.boolean(),
    files: z.record(BundlePathSchema, Sha256Schema),
    eval_report_sha256: Sha256Schema.optional(),
  })
  .passthrough();
export type GradManifest = z.infer<typeof GradManifestSchema>;

export type GradBundleFile = {
  path: string;
  sha256: string;
  sizeBytes: number;
};

export type GradBundle = {
  manifest: GradManifest;
  // Payload files written to the directory, by bundle path.
  files: Map<string, GradBundleFile>;
};

class BundleError extends Error {
  override name = "BundleError";
}

const fail = (message: string): never => {
  throw new BundleError(message);
};

class Chunks {
  private chunk: Uint8Array = new Uint8Array(0);
  private offset = 0;

  constructor(private readonly source: AsyncIterator<Uint8Array>) {}

  private async fill() {
    while (this.offset >= this.chunk.length) {
      const next = await this.source.next();
      if (next.done) fail("The bundle is truncated.");

      this.chunk = next.value as Uint8Array;
      this.offset = 0;
    }
  }

  async exact(length: number) {
    const bytes = new Uint8Array(length);
    let filled = 0;
    while (filled < length) {
      await this.fill();
      const take = Math.min(length - filled, this.chunk.length - this.offset);
      bytes.set(this.chunk.subarray(this.offset, this.offset + take), filled);
      this.offset += take;
      filled += take;
    }
    return bytes;
  }

  async *take(length: number) {
    let left = length;
    while (left > 0) {
      await this.fill();
      const take = Math.min(left, this.chunk.length - this.offset);
      yield this.chunk.subarray(this.offset, this.offset + take);
      this.offset += take;
      left -= take;
    }
  }

  async drain() {
    for (;;) {
      if (this.chunk.subarray(this.offset).some((byte) => byte !== 0))
        fail("The bundle has data after its end.");

      const next = await this.source.next();
      if (next.done) return;

      this.chunk = next.value as Uint8Array;
      this.offset = 0;
    }
  }
}

const text = (bytes: Uint8Array) => {
  const end = bytes.indexOf(0);
  return new TextDecoder("utf-8", { fatal: true }).decode(
    end < 0 ? bytes : bytes.subarray(0, end),
  );
};

const octal = (bytes: Uint8Array) => {
  const value = text(bytes).trim();
  if (!/^[0-7]*$/.test(value)) fail("Invalid tar header number.");

  const number = Number.parseInt(value || "0", 8);
  if (!Number.isSafeInteger(number)) fail("Invalid tar header number.");

  return number;
};

const checksumMatches = (block: Uint8Array) => {
  let sum = 0;
  for (let index = 0; index < 512; index++)
    sum += index >= 148 && index < 156 ? 32 : block[index]!;

  return sum === octal(block.subarray(148, 156));
};

// PAX records are `<length> <key>=<value>\n`; only path and size change a member.
const paxRecords = (body: Uint8Array) => {
  const records = new Map<string, string>();
  let offset = 0;
  while (offset < body.length) {
    const space = body.indexOf(0x20, offset);
    if (space < 0) fail("Invalid PAX header.");

    const length = Number(text(body.subarray(offset, space)));
    if (!Number.isSafeInteger(length) || length <= space - offset)
      fail("Invalid PAX header.");

    const record = text(body.subarray(space + 1, offset + length - 1));
    const equals = record.indexOf("=");
    if (equals < 0) fail("Invalid PAX header.");

    records.set(record.slice(0, equals), record.slice(equals + 1));
    offset += length;
  }
  return records;
};

/**
 * Reads a `grad.artifact/1` bundle with the rules grad's own reader applies:
 * regular files only, safe relative paths, no duplicates, capped members and
 * bytes, and every payload file checked against `manifest.files`. Files whose
 * bundle path is in `keep` are written to `directory`; the rest are hashed only.
 */
export const readGradBundle = async (
  gzipped: AsyncIterable<Uint8Array>,
  {
    directory,
    keep,
    sizeBytes,
    sha256,
    maxUnpackedBytes,
  }: {
    directory: string;
    keep: ReadonlySet<string>;
    sizeBytes: number;
    sha256: string;
    maxUnpackedBytes: number;
  },
): Promise<GradBundle> => {
  const digest = createHash("sha256");
  let received = 0;
  const counted = async function* () {
    for await (const chunk of gzipped) {
      received += chunk.length;
      if (received > sizeBytes) fail("The bundle exceeds its declared size.");

      digest.update(chunk);
      yield chunk;
    }
  };
  const source = Readable.from(counted());
  const gunzip = createGunzip();
  source.on("error", (error) => gunzip.destroy(error));
  source.pipe(gunzip);
  const tar = new Chunks(gunzip[Symbol.asyncIterator]());

  try {
    return await readMembers(tar, { directory, keep, maxUnpackedBytes }).then(
      (bundle) => {
        if (received !== sizeBytes || digest.digest("hex") !== sha256)
          fail("The bundle does not match its SHA-256 and size.");

        return bundle;
      },
    );
  } finally {
    source.destroy();
    gunzip.destroy();
  }
};

const readMembers = async (
  tar: Chunks,
  {
    directory,
    keep,
    maxUnpackedBytes,
  }: {
    directory: string;
    keep: ReadonlySet<string>;
    maxUnpackedBytes: number;
  },
): Promise<GradBundle> => {
  const seen = new Map<string, string>();
  const written = new Map<string, GradBundleFile>();
  let manifestBytes: Uint8Array | undefined;
  let evalReportSha: string | undefined;
  let unpacked = 0;
  let pax: Map<string, string> | undefined;

  for (let members = 0; ;) {
    const block = await tar.exact(512);
    if (block.every((byte) => byte === 0)) break;
    if (!checksumMatches(block)) fail("Invalid tar header checksum.");

    const type = String.fromCharCode(block[156]!);
    let size = octal(block.subarray(124, 136));
    const padding = () => (512 - (size % 512)) % 512;
    if (type === "x") {
      if (size > 64 * 1024) fail("Oversized PAX header.");

      pax = paxRecords(await tar.exact(size));
      await tar.exact(padding());
      continue;
    }
    if (type !== "0" && type !== "\0")
      fail("Bundles may contain regular files only.");

    const prefix = text(block.subarray(345, 500));
    const base = text(block.subarray(0, 100));
    const path = pax?.get("path") ?? (prefix ? `${prefix}/${base}` : base);
    if (pax?.has("size")) size = Number(pax.get("size"));
    pax = undefined;
    if (!Number.isSafeInteger(size) || size < 0) fail("Invalid member size.");
    if (++members > MAX_MEMBERS) fail("The bundle has too many members.");
    if (!BundlePathSchema.safeParse(path).success)
      fail("The bundle has an unsafe path.");
    if (seen.has(path)) fail("The bundle has a duplicate entry.");

    unpacked += size;
    if (unpacked > maxUnpackedBytes) fail("The bundle unpacks too large.");

    const hash = createHash("sha256");
    if (path === "manifest.json") {
      if (size > MAX_MANIFEST_BYTES) fail("The manifest is too large.");

      manifestBytes = await tar.exact(size);
      hash.update(manifestBytes);
    } else if (keep.has(path) && !path.includes("/")) {
      const target = join(directory, path);
      let file: FileHandle | undefined;
      try {
        file = await open(target, "wx", 0o600);
        for await (const chunk of tar.take(size)) {
          hash.update(chunk);
          await file.write(chunk);
        }
      } finally {
        await file?.close();
      }
      written.set(path, { path: target, sha256: "", sizeBytes: size });
    } else {
      for await (const chunk of tar.take(size)) hash.update(chunk);
    }
    await tar.exact(padding());

    const fileSha = hash.digest("hex");
    seen.set(path, fileSha);
    if (path === "eval_report.json") evalReportSha = fileSha;
    const kept = written.get(path);
    if (kept) kept.sha256 = fileSha;
  }
  await tar.drain();

  if (!manifestBytes) fail("The bundle has no manifest.json.");

  let parsed: unknown;
  try {
    parsed = JSON.parse(text(manifestBytes!));
  } catch {
    fail("The bundle's manifest.json is not JSON.");
  }
  const manifest = GradManifestSchema.safeParse(parsed);
  if (!manifest.success) fail("The bundle's manifest.json is invalid.");

  const { files, eval_report_sha256 } = manifest.data!;
  const payload = [...seen.keys()].filter((path) => !RESERVED.has(path));
  if (
    payload.length !== Object.keys(files).length ||
    payload.some((path) => files[path] !== seen.get(path))
  )
    fail("The bundle's files don't match manifest.json.");
  if ((evalReportSha === undefined) !== (eval_report_sha256 === undefined))
    fail("eval_report.json and eval_report_sha256 must come together.");
  if (evalReportSha !== undefined && evalReportSha !== eval_report_sha256)
    fail("eval_report.json does not match its checksum.");

  return { manifest: manifest.data!, files: written };
};

export const isBundleError = (error: unknown) => error instanceof BundleError;
