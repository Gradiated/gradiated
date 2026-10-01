import { ControlServiceError } from "../errors.js";
import {
  isRetained,
  readManifest,
  traceTaskKey,
  workspacePrefix,
} from "../traces/content.js";
import type { ContentStore } from "../traces/storage.js";

const prefixes = async (store: ContentStore, prefix: string) => {
  const values: string[] = [];
  let cursor: string | undefined;
  do {
    const page = await store.list(prefix, {
      delimiter: "/",
      cursor,
      limit: 1000,
    });
    values.push(...page.prefixes);
    cursor = page.cursor;
  } while (cursor);

  return values.sort().reverse();
};

export const trainingTraceRows = async function* (
  store: ContentStore,
  input: {
    workspaceId: string;
    task: string;
    since: Date | null;
    cutoff: Date;
  },
) {
  const prefix = `${workspacePrefix(input.workspaceId)}task=${traceTaskKey(input.task)}/`;
  const retentionFloor = input.cutoff.getTime() - 180 * 86_400_000;
  const floor = input.since?.getTime() ?? 0;
  const dates = await prefixes(store, prefix);

  for (const date of dates) {
    const day = date
      .slice(prefix.length)
      .match(/^dt=(\d{4}-\d{2}-\d{2})\/$/)?.[1];
    if (!day || Date.parse(`${day}T00:00:00Z`) > input.cutoff.getTime())
      continue;
    if (Date.parse(`${day}T00:00:00Z`) + 86_400_000 <= retentionFloor) break;

    for (const hour of await prefixes(store, date)) {
      const number = hour.slice(date.length).match(/^hr=(\d{2})\/$/)?.[1];
      if (!number) continue;
      const time = Date.parse(`${day}T${number}:00:00Z`);
      if (time > input.cutoff.getTime() || time + 3_600_000 <= retentionFloor)
        continue;

      let cursor: string | undefined;
      do {
        const page = await store.list(hour, { cursor, limit: 1000 });
        for (const key of page.keys) {
          if (!key.endsWith(".manifest.json")) continue;
          const arrived = Date.parse(page.modifiedAt?.[key] ?? "");
          if (!Number.isFinite(arrived))
            throw new ControlServiceError(
              "unavailable",
              "Manifest arrival time is unavailable.",
            );
          if (arrived <= floor || arrived > input.cutoff.getTime()) continue;

          for (const row of await readManifest(store, key)) {
            if (
              row.workspace_id !== input.workspaceId ||
              row.task !== input.task ||
              !row.trainable ||
              !isRetained(row, input.cutoff.getTime())
            )
              continue;
            yield { key, row };
          }
        }
        cursor = page.cursor;
      } while (cursor);
    }
  }
};

export const countTrainingTraces = async (
  store: ContentStore,
  input: Parameters<typeof trainingTraceRows>[1] & { threshold: number },
) => {
  const seen = new Set<string>();
  for await (const { row } of trainingTraceRows(store, input)) {
    seen.add(row.trace_id ?? row.generation_id);
    if (seen.size >= input.threshold) break;
  }
  return seen.size;
};
