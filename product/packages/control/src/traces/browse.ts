import { z } from "zod";
import type { TraceGeneration } from "@gradiated/contracts";
import { DAY, HOUR } from "../constants.js";
import {
  encode,
  contentNotFound,
  workspacePrefix,
  readManifest,
  traceTaskKey,
  isRetained,
} from "./content.js";
import type { ContentStore } from "./storage.js";

const cursorSchema = z.object({
  hour: z.number().int().nonnegative(),
  continuation: z.string().optional(),
  task: z.string(),
  manifests: z.array(z.string().max(1024)).max(2).optional(),
  offset: z.number().int().nonnegative().optional(),
});

const readCursor = (encoded: string | undefined, task: string, now: number) => {
  let cursor: z.infer<typeof cursorSchema>;
  try {
    cursor = encoded
      ? cursorSchema.parse(
          JSON.parse(Buffer.from(encoded, "base64url").toString()),
        )
      : { hour: Math.floor(now / HOUR) * HOUR, task: task };
  } catch {
    throw contentNotFound();
  }

  if (
    cursor.task !== task ||
    cursor.hour % HOUR !== 0 ||
    cursor.hour > Math.floor(now / HOUR) * HOUR
  )
    throw contentNotFound();

  return cursor;
};

export const listTraceGenerations = async (
  store: ContentStore,
  workspace: string,
  query: { task: string; cursor?: string | undefined },
) => {
  const now = Date.now();
  let cursor = readCursor(query.cursor, query.task, now);
  const cutoff = now - 180 * DAY;
  let scanned = 0;
  while (true) {
    if (cursor.hour + HOUR <= cutoff) return { data: [], next_cursor: null };

    const hour = new Date(cursor.hour).toISOString();
    const path = `${workspacePrefix(workspace)}task=${traceTaskKey(query.task)}/dt=${hour.slice(0, 10)}/hr=${hour.slice(11, 13)}/`;
    const page = cursor.manifests
      ? { keys: cursor.manifests, cursor: cursor.continuation }
      : await store.list(path, { cursor: cursor.continuation, limit: 2 });
    const keys = page.keys.filter((key) => key.endsWith(".manifest.json"));
    if (
      keys.some(
        (key) => !key.startsWith(path) || key.slice(path.length).includes("/"),
      )
    )
      throw contentNotFound();

    const key = keys[0];
    const generations = new Map<string, TraceGeneration>();
    let next: z.infer<typeof cursorSchema> = page.cursor
      ? { hour: cursor.hour, task: query.task, continuation: page.cursor }
      : { hour: cursor.hour - HOUR, task: query.task };
    if (key) {
      const rows = await readManifest(store, key);
      const offset = cursor.offset ?? 0;
      const end = Math.min(offset + 100, rows.length);
      for (const row of rows.slice(offset, end)) {
        if (
          row.workspace_id !== workspace ||
          row.task !== query.task ||
          !isRetained(row, now)
        )
          continue;
        generations.set(row.generation_id, {
          generation_id: row.generation_id,
          trace_id: row.trace_id ?? row.generation_id,
          task: row.task,
          model: row.model,
          source: row.source,
          trainable: row.trainable,
          started_at: row.started_at,
          completed_at: row.completed_at,
          status: row.status ?? null,
          outcome: row.outcome ?? null,
          usage: row.usage,
          content_ref: encode(key),
        });
      }

      const remaining = end < rows.length ? keys : keys.slice(1);
      if (remaining.length)
        next = {
          hour: cursor.hour,
          task: query.task,
          manifests: remaining,
          offset: end < rows.length ? end : 0,
          ...(page.cursor ? { continuation: page.cursor } : {}),
        };
    }

    const result = {
      data: [...generations.values()].sort((a, b) =>
        b.generation_id.localeCompare(a.generation_id),
      ),
      next_cursor: next.hour + HOUR <= cutoff ? null : encode(next),
    };
    if (result.data.length || !result.next_cursor || ++scanned >= 24)
      return result;

    cursor = next;
  }
};
