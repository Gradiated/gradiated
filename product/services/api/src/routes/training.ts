import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";
import {
  PromoteVersionSchema,
  TaskListSchema,
  TaskPathSchema,
  TaskSchema,
  TaskVersionListSchema,
  TrainingRunEventListSchema,
  TrainingRunEventsQuerySchema,
  TrainingRunListSchema,
  TrainingRunListQuerySchema,
  TrainingRunPathSchema,
  TrainingRunSchema,
  UpdateTaskSchema,
  WorkspacePathSchema,
  problemContent,
  type Task,
  type TaskVersion,
  type TrainingRun,
} from "@gradiated/contracts";
import type {
  TaskRecord,
  TaskVersionRecord,
  TrainingRunRecord,
  TrainingService,
} from "@gradiated/control";
import { requireUser } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";

const base = "/api/v1/workspaces/{workspace_id}";
const errors = {
  401: { description: "Authentication required.", content: problemContent },
  403: { description: "Not allowed.", content: problemContent },
  404: { description: "Not found.", content: problemContent },
  422: {
    description: "Invalid request parameters or body.",
    content: problemContent,
  },
  503: { description: "Trace storage unavailable.", content: problemContent },
};
const json = <Schema>(schema: Schema, description: string) => ({
  description,
  content: { "application/json": { schema } },
});

const listTasks = createRoute({
  method: "get",
  path: `${base}/tasks`,
  operationId: "listTasks",
  tags: ["Training"],
  request: { params: WorkspacePathSchema },
  responses: {
    200: json(TaskListSchema, "Tasks with captured traces."),
    ...errors,
  },
});
const getTask = createRoute({
  method: "get",
  path: `${base}/tasks/{task}`,
  operationId: "getTask",
  tags: ["Training"],
  request: { params: TaskPathSchema },
  responses: { 200: json(TaskSchema, "The task."), ...errors },
});
const updateTask = createRoute({
  method: "patch",
  path: `${base}/tasks/{task}`,
  operationId: "updateTask",
  tags: ["Training"],
  request: {
    params: TaskPathSchema,
    body: { content: { "application/json": { schema: UpdateTaskSchema } } },
  },
  responses: { 200: json(TaskSchema, "The updated task."), ...errors },
});
const listRuns = createRoute({
  method: "get",
  path: `${base}/training-runs`,
  operationId: "listTrainingRuns",
  tags: ["Training"],
  request: { params: WorkspacePathSchema, query: TrainingRunListQuerySchema },
  responses: {
    200: json(TrainingRunListSchema, "Runs, newest first."),
    ...errors,
  },
});
const getRun = createRoute({
  method: "get",
  path: `${base}/training-runs/{run_id}`,
  operationId: "getTrainingRun",
  tags: ["Training"],
  request: { params: TrainingRunPathSchema },
  responses: { 200: json(TrainingRunSchema, "The run."), ...errors },
});
const listRunEvents = createRoute({
  method: "get",
  path: `${base}/training-runs/{run_id}/events`,
  operationId: "listTrainingRunEvents",
  tags: ["Training"],
  request: {
    params: TrainingRunPathSchema,
    query: TrainingRunEventsQuerySchema,
  },
  responses: {
    200: json(TrainingRunEventListSchema, "Events in order, after the cursor."),
    ...errors,
  },
});
const listVersions = createRoute({
  method: "get",
  path: `${base}/tasks/{task}/versions`,
  operationId: "listTaskVersions",
  tags: ["Training"],
  request: { params: TaskPathSchema },
  responses: {
    200: json(TaskVersionListSchema, "Versions, newest first."),
    ...errors,
  },
});
const promote = createRoute({
  method: "put",
  path: `${base}/tasks/{task}/production`,
  operationId: "promoteTaskVersion",
  tags: ["Training"],
  request: {
    params: TaskPathSchema,
    body: { content: { "application/json": { schema: PromoteVersionSchema } } },
  },
  responses: {
    200: json(TaskSchema, "The task with its new production version."),
    ...errors,
  },
});

const taskResponse = (task: TaskRecord): Task => ({
  id: task.id,
  name: task.name,
  base_model_id: task.baseModelId,
  comparison_model_id: task.comparisonModelId,
  production_version_id: task.productionVersionId,
});

const runResponse = (run: TrainingRunRecord): TrainingRun => ({
  id: run.id,
  task: run.task,
  trigger: run.trigger,
  requested_by: run.requestedBy,
  stage: run.stage,
  base_model_id: run.baseModelId,
  input_cutoff: run.inputCutoff.toISOString(),
  dataset: run.dataset,
  evaluation: run.evaluation,
  version_id: run.versionId,
  cancel_requested_at: run.cancelRequestedAt?.toISOString() ?? null,
  created_at: run.createdAt.toISOString(),
  finished_at: run.finishedAt?.toISOString() ?? null,
});

const versionResponse = (
  task: TaskRecord,
  version: TaskVersionRecord,
): TaskVersion => ({
  id: version.id,
  name: version.name,
  task: task.name,
  training_run_id: version.trainingRunId,
  base_model_id: version.baseModelId,
  adapter: version.adapter,
  status: version.status,
  is_production: task.productionVersionId === version.id,
  created_at: version.createdAt.toISOString(),
});

export const registerTrainingRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  training: TrainingService,
) => {
  app.openapi(listTasks, async (c) => {
    const user = await requireUser(c);
    const { workspace_id } = c.req.valid("param");
    const tasks = await training.listTasks(user.id, workspace_id);
    return c.json({ data: tasks.map(taskResponse) }, 200);
  });
  app.openapi(getTask, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    return c.json(
      taskResponse(await training.getTask(user.id, p.workspace_id, p.task)),
      200,
    );
  });
  app.openapi(updateTask, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const task = await training.updateTask(
      user.id,
      p.workspace_id,
      p.task,
      c.req.valid("json"),
    );
    return c.json(taskResponse(task), 200);
  });
  app.openapi(listRuns, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const runs = await training.listRuns(
      user.id,
      p.workspace_id,
      c.req.valid("query"),
    );
    return c.json({ data: runs.map(runResponse) }, 200);
  });
  app.openapi(getRun, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    return c.json(
      runResponse(await training.getRun(user.id, p.workspace_id, p.run_id)),
      200,
    );
  });
  app.openapi(listRunEvents, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const page = c.req.valid("query");
    const events = await training.listRunEvents(
      user.id,
      p.workspace_id,
      p.run_id,
      page,
    );
    return c.json(
      {
        data: events.map((event) => ({
          id: event.id,
          at: event.at.toISOString(),
          source: event.source,
          attempt: event.attempt,
          payload: event.payload,
        })),
        next_cursor:
          events.length === page.limit ? String(events.at(-1)!.id) : null,
      },
      200,
    );
  });
  app.openapi(listVersions, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const { task, versions } = await training.listVersions(
      user.id,
      p.workspace_id,
      p.task,
    );
    return c.json(
      { data: versions.map((version) => versionResponse(task, version)) },
      200,
    );
  });
  app.openapi(promote, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const task = await training.promote(
      user.id,
      p.workspace_id,
      p.task,
      c.req.valid("json").version_id,
    );
    return c.json(taskResponse(task), 200);
  });
};
