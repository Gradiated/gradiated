import { TaskNameSchema } from "@gradiated/contracts";
import { readManifest, traceTaskKey, workspacePrefix } from "./content.js";
import type { ContentStore } from "./storage.js";

const hashedKey = /^h-[0-9a-f]{32}$/;

const listTaskKeys = async (store: ContentStore, workspace: string) => {
  const prefix = `${workspacePrefix(workspace)}task=`;
  const keys: string[] = [];
  let cursor: string | undefined;
  do {
    const page = await store.list(prefix, { cursor, delimiter: "/" });
    keys.push(...page.prefixes.map((path) => path.slice(prefix.length, -1)));
    cursor = page.cursor;
  } while (cursor);

  return keys;
};

const readTaskName = async (
  store: ContentStore,
  workspace: string,
  key: string,
) => {
  const { keys } = await store.list(
    `${workspacePrefix(workspace)}task=${key}/`,
    { limit: 10 },
  );
  const manifest = keys.find((path) => path.endsWith(".manifest.json"));
  if (!manifest) return undefined;

  const [row] = await readManifest(store, manifest);
  return row && traceTaskKey(row.task) === key ? row.task : undefined;
};

export const discoverTraceTasks = async (
  store: ContentStore,
  workspace: string,
  known: ReadonlySet<string>,
): Promise<string[]> => {
  const unknown = (await listTaskKeys(store, workspace)).filter(
    (key) => !known.has(key),
  );
  const names = await Promise.all(
    unknown.map((key) =>
      hashedKey.test(key) ? readTaskName(store, workspace, key) : key,
    ),
  );

  return names.filter(
    (name): name is string =>
      name !== undefined && TaskNameSchema.safeParse(name).success,
  );
};
