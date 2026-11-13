import { requireWorkspaceMembership } from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { listTraceGenerations } from "./browse.js";
import {
  contentNotFound,
  findTraceContent,
  readTraceContent,
} from "./content.js";
import type { ContentStore } from "./storage.js";

export type TraceService = ReturnType<typeof createTraceService>;

export const createTraceService = (
  database: ControlDatabase,
  store: ContentStore,
) => {
  const access = async (userId: string, workspaceId: string) => {
    const result = await requireWorkspaceMembership(database, {
      userId,
      workspaceId,
    });
    if (result.workspace.archivedAt) throw contentNotFound();

    return result.workspace;
  };

  return {
    async list(
      user: string,
      workspace: string,
      query: { task: string; cursor?: string | undefined },
    ) {
      await access(user, workspace);

      return listTraceGenerations(store, workspace, query);
    },
    async content(
      user: string,
      workspace: string,
      generation: string,
      // A content_ref from a listed generation, or the generation's task name.
      locator: { content_ref: string } | { task: string },
    ) {
      await access(user, workspace);

      return "content_ref" in locator
        ? readTraceContent(store, workspace, generation, locator.content_ref)
        : findTraceContent(store, workspace, locator.task, generation);
    },
  };
};
