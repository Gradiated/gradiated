import { createHash } from "node:crypto";
import * as zlib from "node:zlib";
import { z } from "zod";
import { DAY } from "../constants.js";
import { ControlServiceError } from "../errors.js";
import type { ContentStore } from "./storage.js";

const rowSchema = z.object({
  workspace_id: z.string().uuid(),
  generation_id: z.string().uuid(),
  task: z.string(),
  trace_id: z.string().nullable(),
  model: z.string(),
  source: z.enum(["relay", "hosted", "import"]),
  trainable: z.boolean(),
  started_at: z.string().datetime(),
  completed_at: z.string().datetime().nullable(),
  status: z.number().int().optional(),
  outcome: z.string().optional(),
  usage: z.record(z.string(), z.unknown()).nullable(),
  retention_days: z.number().int(),
  offset: z.number().int().nonnegative(),
  length: z
    .number()
    .int()
    .positive()
    .max(32 * 1024 * 1024),
});

export type TraceManifestRow = z.infer<typeof rowSchema>;
type Row = TraceManifestRow;
const manifestSchema = z.object({
  schema: z.literal("gradiated.generation-content-manifest/1"),
  generations: z.array(rowSchema).max(100_000),
});
export const workspacePrefix = (workspace: string) => `v1/ws=${workspace}/`;
export const traceTaskKey = (task: string) =>
  /^[a-z0-9_-]{1,64}$/.test(task)
    ? task
    : `h-${createHash("sha256").update(task).digest("hex").slice(0, 32)}`;
export const encode = (value: unknown) =>
  Buffer.from(JSON.stringify(value)).toString("base64url");
export const contentNotFound = () =>
  new ControlServiceError("not_found", "Generation content was not found.");
const generationTime = (id: string) =>
  Number.parseInt(id.replaceAll("-", "").slice(0, 12), 16);
export const isRetained = (row: Row, now: number) =>
  generationTime(row.generation_id) >= now - row.retention_days * DAY;
export const readManifest = async (store: ContentStore, key: string) => {
  try {
    return manifestSchema.parse(
      JSON.parse(Buffer.from(await store.read(key)).toString("utf8")),
    ).generations;
  } catch {
    throw new ControlServiceError(
      "unavailable",
      "Generation manifest is unavailable.",
    );
  }
};

export const readTraceContent = async (
  store: ContentStore,
  workspace: string,
  generation: string,
  reference: string,
) => {
  if (generationTime(generation) < Date.now() - 180 * DAY)
    throw contentNotFound();

  let key: string;
  try {
    key = z
      .string()
      .parse(JSON.parse(Buffer.from(reference, "base64url").toString()));
  } catch {
    throw contentNotFound();
  }

  if (
    !key.startsWith(workspacePrefix(workspace)) ||
    !/^v1\/ws=[\da-f-]+\/task=[a-z0-9_-]+\/dt=\d{4}-\d{2}-\d{2}\/hr=\d{2}\/[^/]+\.manifest\.json$/.test(
      key,
    )
  )
    throw contentNotFound();

  const row = (await readManifest(store, key)).find(
    (row) => row.generation_id === generation && row.workspace_id === workspace,
  );
  if (!row || !isRetained(row, Date.now())) throw contentNotFound();

  return readTraceRecord(store, key, row);
};

export const readTraceRecord = async (
  store: ContentStore,
  key: string,
  row: Row,
) => {
  const generation = row.generation_id;
  const workspace = row.workspace_id;
  const bytes = await store.read(
    key.replace(/\.manifest\.json$/, ".jsonl.zst"),
    row,
  );
  const decompress = (
    zlib as unknown as {
      zstdDecompress: (
        input: Uint8Array,
        options: { maxOutputLength: number },
        callback: (error: Error | null, result: Buffer) => void,
      ) => void;
    }
  ).zstdDecompress;

  try {
    const decoded = await new Promise<Buffer>((resolve, reject) =>
      decompress(
        bytes,
        // The collector appends a newline to each admitted JSON record.
        { maxOutputLength: 32 * 1024 * 1024 + 1 },
        (error, result) => (error ? reject(error) : resolve(result)),
      ),
    );
    const record = z
      .object({
        generation_id: z.literal(generation),
        workspace_id: z.literal(workspace),
        raw: z.record(z.string(), z.unknown()).nullable().default(null),
        canonical: z.unknown().nullable().default(null),
      })
      .parse(JSON.parse(decoded.toString()));

    return {
      generation_id: record.generation_id,
      raw: record.raw,
      canonical: record.canonical,
    };
  } catch {
    throw new ControlServiceError(
      "unavailable",
      "Generation content could not be decoded.",
    );
  }
};
