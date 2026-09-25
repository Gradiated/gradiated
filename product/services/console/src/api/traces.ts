import { api, requireData } from "./client";
import type { components } from "./schema";
export type StoredGeneration = components["schemas"]["TraceGeneration"];
const scope = (workspace_id: string) => ({ workspace_id });
export const listTraceGenerations = (
  organization: string,
  workspace: string,
  task: string,
  cursor?: string,
) =>
  requireData(
    api.GET("/api/v1/workspaces/{workspace_id}/generations", {
      params: {
        path: scope(workspace),
        query: { task_id: task, ...(cursor ? { cursor } : {}) },
      },
    }),
  ).then((page) => ({
    ...page,
    data: page.data.map((row) => {
      if (!("generation_id" in row))
        throw new Error("Expected captured generation metadata.");
      return row;
    }),
  }));
export const getTraceGeneration = (
  organization: string,
  workspace: string,
  generation: StoredGeneration,
) =>
  requireData(
    api.GET("/api/v1/workspaces/{workspace_id}/generations/{generation_id}", {
      params: {
        path: {
          ...scope(workspace),
          generation_id: generation.generation_id,
        },
        query: { content_ref: generation.content_ref },
      },
    }),
  );
