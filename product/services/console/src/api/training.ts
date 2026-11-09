import { api, requireData, requireOk } from "./client";
import type { components } from "./schema";

export const listTasks = (workspace_id: string, signal?: AbortSignal) =>
  requireData(
    api.GET("/api/v1/workspaces/{workspace_id}/tasks", {
      params: { path: { workspace_id } },
      signal: signal ?? null,
    }),
  );

export const getTask = (
  workspace_id: string,
  task: string,
  signal?: AbortSignal,
) =>
  requireData(
    api.GET("/api/v1/workspaces/{workspace_id}/tasks/{task}", {
      params: { path: { workspace_id, task } },
      signal: signal ?? null,
    }),
  );

export const listTaskRuns = (
  workspace_id: string,
  task_id: string,
  signal?: AbortSignal,
) =>
  requireData(
    api.GET("/api/v1/workspaces/{workspace_id}/training-runs", {
      params: { path: { workspace_id }, query: { task_id } },
      signal: signal ?? null,
    }),
  );

export const listTaskVersions = (
  workspace_id: string,
  task: string,
  signal?: AbortSignal,
) =>
  requireData(
    api.GET("/api/v1/workspaces/{workspace_id}/tasks/{task}/versions", {
      params: { path: { workspace_id, task } },
      signal: signal ?? null,
    }),
  );

export const listRunEvents = (
  workspace_id: string,
  run_id: string,
  after?: number,
  signal?: AbortSignal,
) =>
  requireData(
    api.GET("/api/v1/workspaces/{workspace_id}/training-runs/{run_id}/events", {
      params: {
        path: { workspace_id, run_id },
        query: { ...(after === undefined ? {} : { after }), limit: 1000 },
      },
      signal: signal ?? null,
    }),
  );

export const updateTask = (
  workspace_id: string,
  task: string,
  body: components["schemas"]["UpdateTask"],
) =>
  requireData(
    api.PATCH("/api/v1/workspaces/{workspace_id}/tasks/{task}", {
      params: { path: { workspace_id, task } },
      body,
    }),
  );

export const promoteVersion = (
  workspace_id: string,
  task: string,
  version_id: string,
) =>
  requireData(
    api.PUT("/api/v1/workspaces/{workspace_id}/tasks/{task}/production", {
      params: { path: { workspace_id, task } },
      body: { version_id },
    }),
  );

export const getAdapterDownload = (
  workspace_id: string,
  task: string,
  version_id: string,
) =>
  requireData(
    api.GET(
      "/api/v1/workspaces/{workspace_id}/tasks/{task}/versions/{version_id}/adapter",
      {
        params: { path: { workspace_id, task, version_id } },
      },
    ),
  );

export const startTrainingRun = (workspace_id: string, task_id: string) =>
  requireData(
    api.POST("/api/v1/workspaces/{workspace_id}/training-runs", {
      params: { path: { workspace_id } },
      body: { task_id },
    }),
  );

export const cancelTrainingRun = (workspace_id: string, run_id: string) =>
  requireOk(
    api.DELETE("/api/v1/workspaces/{workspace_id}/training-runs/{run_id}", {
      params: { path: { workspace_id, run_id } },
    }),
  );

export const getEvaluationResults = (
  workspace_id: string,
  task: string,
  version_id: string,
  signal?: AbortSignal,
) =>
  requireData(
    api.GET(
      "/api/v1/workspaces/{workspace_id}/tasks/{task}/versions/{version_id}/evaluation",
      {
        params: { path: { workspace_id, task, version_id } },
        signal: signal ?? null,
      },
    ),
  );

export const createModelUpload = (
  workspace_id: string,
  body: components["schemas"]["CreateModelUpload"],
) =>
  requireData(
    api.POST("/api/v1/workspaces/{workspace_id}/model-uploads", {
      params: { path: { workspace_id } },
      body,
    }),
  );

export const completeModelUpload = (workspace_id: string, upload_id: string) =>
  requireData(
    api.PUT(
      "/api/v1/workspaces/{workspace_id}/model-uploads/{upload_id}/version",
      { params: { path: { workspace_id, upload_id } } },
    ),
  );

export const getAdapterConfiguration = (
  workspace_id: string,
  model_id: string,
  signal?: AbortSignal,
) =>
  requireData(
    api.GET(
      "/api/v1/workspaces/{workspace_id}/adapter-configurations/{model_id}",
      {
        params: { path: { workspace_id, model_id } },
        signal: signal ?? null,
      },
    ),
  );
