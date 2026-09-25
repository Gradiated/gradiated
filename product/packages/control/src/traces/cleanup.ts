import { eq } from "drizzle-orm";
import type { ControlDatabase } from "../db/client.js";
import { workspaces } from "../db/schema/index.js";
import type { ContentStore } from "./storage.js";

export const createTraceCleanup = (
  database: ControlDatabase,
  store: ContentStore,
) => {
  let workspaceCursor: string | undefined;
  let objectCursor: string | undefined;
  let pending: { id: string; prefix: string }[] = [];
  return async () => {
    if (!pending.length) {
      const page = await store.list("v1/", {
        delimiter: "/",
        cursor: workspaceCursor,
        limit: 10,
      });
      pending = page.prefixes.flatMap((prefix) => {
        const id =
          /^v1\/ws=([\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12})\/$/.exec(
            prefix,
          )?.[1];
        return id ? [{ id, prefix }] : [];
      });
      workspaceCursor = page.cursor;
    }
    const scope = pending[0];
    if (!scope) return;
    const [workspace] = await database
      .select()
      .from(workspaces)
      .where(eq(workspaces.id, scope.id));
    if (workspace && !workspace.archivedAt) {
      pending.shift();
      return;
    }

    const objects = await store.list(scope.prefix, {
      cursor: objectCursor,
      limit: 1000,
    });
    await store.delete(objects.keys);
    objectCursor = objects.cursor;
    if (!objectCursor) pending.shift();
  };
};
