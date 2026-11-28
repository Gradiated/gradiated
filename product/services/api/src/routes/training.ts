import { changedFields } from "@gradiated/analytics";
import { z, createRoute, type OpenAPIHono } from "@hono/zod-openapi";
import {
  CreateModelUploadSchema,
  CreateTaskVersionFileSchema,
  TaskVersionFileContentSchema,
  TaskVersionFileDownloadSchema,
  TaskVersionFileListSchema,
  TaskVersionFilePathSchema,
  TaskVersionFileSchema,
  TaskVersionFileUploadSchema,
  ModelUploadSchema,
  ModelUploadPathSchema,
  TaskVersionSchema,
  StartTrainingRunResponseSchema,
  StartTrainingRunSchema,
  PromoteVersionSchema,
  ProductionChangeListSchema,
  PublishedTaskVersionSchema,
  PublishTaskVersionSchema,
  TaskVersionPathSchema,
  AdapterDownloadSchema,
  AdapterWeightsSchema,
  EvaluationResultsSchema,
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
  SharedReportFilePathSchema,
  SharedReportPathSchema,
  SharedReportSchema,
  TaskVersionShareSchema,
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
import { ApiProblem, problems, requireUser } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";

const base = "/api/v1/workspaces/{workspace_id}";
const errors = {
  409: {
    description: "Upload conflict or invalid adapter.",
    content: problemContent,
  },
  401: { description: "Authentication required.", content: problemContent },
  403: { description: "Not allowed.", content: problemContent },
  404: { description: "Not found.", content: problemContent },
  422: {
    description: "Invalid request parameters or body.",
    content: problemContent,
  },
  503: { description: "Storage unavailable.", content: problemContent },
};
const json = <Schema>(schema: Schema, description: string) => ({
  description,
  content: { "application/json": { schema } },
});

const AdapterConfigurationSchema = z
  .object({
    layerCount: z
      .number()
      .int()
      .min(1)
      .max(4096)
      .describe("Number of transformer layers."),
    expertCount: z
      .number()
      .int()
      .min(0)
      .max(4096)
      .describe("Routed experts per layer."),
    expertLayers: z
      .array(z.number().int().min(0).max(4095))
      .max(4096)
      .optional()
      .describe("Layers that have routed experts; absent for dense models."),
    projectionShapes: z
      .record(z.string(), z.tuple([z.number(), z.number()]).readonly())
      .optional()
      .describe("Output and input dimensions keyed by layer and module."),
  })
  .openapi("AdapterConfiguration");
const adapterConfiguration = createRoute({
  method: "get",
  path: `${base}/adapter-configurations/{model_id}`,
  operationId: "getAdapterConfiguration",
  summary: "Get adapter configuration",
  description:
    "Gets the pinned base checkpoint dimensions used to validate an adapter.",
  tags: ["Training"],
  request: {
    params: WorkspacePathSchema.extend({
      model_id: z.string().min(1).describe("Exact catalog base model ID."),
    }),
  },
  responses: {
    200: json(AdapterConfigurationSchema, "Pinned checkpoint structure."),
    ...errors,
  },
});
const createUpload = createRoute({
  method: "post",
  path: `${base}/model-uploads`,
  operationId: "createModelUpload",
  summary: "Create model upload",
  description:
    "Creates a workspace-scoped upload for PEFT LoRA config and safetensors files. Grants expire after one hour. Once uploads move to grad this answers 410 `use_grad_artifacts_upload`; uploads already started still complete.",
  tags: ["Training"],
  request: {
    params: WorkspacePathSchema,
    body: {
      required: true,
      content: { "application/json": { schema: CreateModelUploadSchema } },
    },
  },
  responses: {
    201: json(ModelUploadSchema, "Private file upload grants."),
    410: {
      description: "New uploads go through `grad artifacts upload`.",
      content: problemContent,
    },
    ...errors,
  },
});
const completeUpload = createRoute({
  method: "put",
  path: `${base}/model-uploads/{upload_id}/version`,
  operationId: "completeModelUpload",
  summary: "Complete model upload",
  description:
    "Validates adapter files and creates an unavailable model version. Retries return the same version. Promoting the version tests it on serving capacity and enables serving when that passes.",
  tags: ["Training"],
  request: { params: ModelUploadPathSchema },
  responses: {
    200: json(TaskVersionSchema, "Uploaded model version."),
    ...errors,
  },
});

const listTasks = createRoute({
  method: "get",
  path: `${base}/tasks`,
  operationId: "listTasks",
  summary: "List tasks",
  description: "Lists the workspace's tasks.",
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
  summary: "Get task",
  description: "Gets a task.",
  tags: ["Training"],
  request: { params: TaskPathSchema },
  responses: { 200: json(TaskSchema, "The task."), ...errors },
});
const updateTask = createRoute({
  method: "patch",
  path: `${base}/tasks/{task}`,
  operationId: "updateTask",
  summary: "Update task",
  description: "Changes a task's settings.",
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
  summary: "List training runs",
  description: "Lists the workspace's training runs.",
  tags: ["Training"],
  request: { params: WorkspacePathSchema, query: TrainingRunListQuerySchema },
  responses: {
    200: json(TrainingRunListSchema, "Runs, newest first."),
    ...errors,
  },
});
const startRun = createRoute({
  method: "post",
  path: `${base}/training-runs`,
  operationId: "startTrainingRun",
  summary: "Start training run",
  description: "Starts training a task.",
  tags: ["Training"],
  request: {
    params: WorkspacePathSchema,
    body: {
      required: true,
      content: { "application/json": { schema: StartTrainingRunSchema } },
    },
  },
  responses: {
    ...errors,
    202: json(StartTrainingRunResponseSchema, "Training accepted."),
    409: { description: "Already training.", content: problemContent },
    422: {
      description: "Training prerequisites are not met.",
      content: problemContent,
    },
  },
});
const cancelRun = createRoute({
  method: "delete",
  path: `${base}/training-runs/{run_id}`,
  operationId: "cancelTrainingRun",
  summary: "Cancel training run",
  description: "Cancels a training run.",
  tags: ["Training"],
  request: { params: TrainingRunPathSchema },
  responses: { 202: { description: "Cancellation requested." }, ...errors },
});
const getRun = createRoute({
  method: "get",
  path: `${base}/training-runs/{run_id}`,
  operationId: "getTrainingRun",
  summary: "Get training run",
  description: "Gets a training run.",
  tags: ["Training"],
  request: { params: TrainingRunPathSchema },
  responses: { 200: json(TrainingRunSchema, "The run."), ...errors },
});
const listRunEvents = createRoute({
  method: "get",
  path: `${base}/training-runs/{run_id}/events`,
  operationId: "listTrainingRunEvents",
  summary: "List training run events",
  description: "Lists a training run's progress events.",
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
  summary: "List task versions",
  description: "Lists a task's trained versions.",
  tags: ["Training"],
  request: { params: TaskPathSchema },
  responses: {
    200: json(TaskVersionListSchema, "Versions, newest first."),
    ...errors,
  },
});
const publishVersion = createRoute({
  method: "post",
  path: `${base}/tasks/{task}/versions`,
  operationId: "publishTaskVersion",
  summary: "Publish an artifact as a version",
  description:
    "Publishes a grad artifact as a version of this model, creating the model on first publish. Callers name the model after the artifact unless they choose another name. The artifact is pinned so training never deletes it, and the version reads its bundle in place. The version is then tested on serving capacity, as promote does; it is not promoted. Publishing the same artifact again returns the existing version. 422 `format_not_servable_yet` names the formats serving supports.",
  tags: ["Training"],
  request: {
    params: TaskPathSchema,
    body: {
      content: { "application/json": { schema: PublishTaskVersionSchema } },
    },
  },
  responses: {
    200: json(PublishedTaskVersionSchema, "The artifact's existing version."),
    201: json(PublishedTaskVersionSchema, "The new version."),
    ...errors,
  },
});
const deleteVersion = createRoute({
  method: "delete",
  path: `${base}/tasks/{task}/versions/{version_id}`,
  operationId: "deleteTaskVersion",
  summary: "Delete task version",
  description:
    "Deletes a version that is not in production and releases its artifact's pin. 409 when the version serves production.",
  tags: ["Training"],
  request: { params: TaskVersionPathSchema },
  responses: {
    204: { description: "The version was deleted." },
    ...errors,
  },
});
const listProductionChanges = createRoute({
  method: "get",
  path: `${base}/tasks/{task}/production-changes`,
  operationId: "listProductionChanges",
  summary: "List production changes",
  description:
    "Lists the last 100 moves of the task's production pointer, newest first. Rollback promotes a change's `from_version_id`.",
  tags: ["Training"],
  request: { params: TaskPathSchema },
  responses: {
    200: json(ProductionChangeListSchema, "Changes, newest first."),
    ...errors,
  },
});
const getVersion = createRoute({
  method: "get",
  path: `${base}/tasks/{task}/versions/{version_id}`,
  operationId: "getTaskVersion",
  summary: "Get task version",
  description: "Gets one of a task's versions by its name or ID.",
  tags: ["Training"],
  request: { params: TaskVersionPathSchema },
  responses: {
    200: json(TaskVersionSchema, "The version."),
    ...errors,
  },
});
const evaluationResults = createRoute({
  method: "get",
  path: `${base}/tasks/{task}/versions/{version_id}/evaluation`,
  operationId: "getEvaluationResults",
  summary: "Get evaluation results",
  description: "Gets a task version's evaluation results.",
  tags: ["Training"],
  request: { params: TaskVersionPathSchema },
  responses: {
    200: json(
      EvaluationResultsSchema,
      "Held-out responses and judge decisions.",
    ),
    ...errors,
  },
});
const downloadAdapter = createRoute({
  method: "get",
  path: `${base}/tasks/{task}/versions/{version_id}/adapter`,
  operationId: "getAdapterDownload",
  summary: "Download adapter",
  description: "Gets a download link for a task version's adapter.",
  tags: ["Training"],
  request: { params: TaskVersionPathSchema },
  responses: {
    200: json(
      AdapterDownloadSchema,
      "A short-lived adapter archive download link.",
    ),
    ...errors,
  },
});
const adapterWeights = createRoute({
  method: "get",
  path: `${base}/tasks/{task}/versions/{version_id}/adapter/weights`,
  operationId: "getAdapterWeights",
  summary: "Get adapter weight summary",
  description:
    "Summarizes how a task version's LoRA adapter changes each projection of the base model: the norm and singular values of each update and a coarse block heatmap. The first request for a version reads the whole adapter and can take several seconds; later requests are served from a cache.",
  tags: ["Training"],
  request: { params: TaskVersionPathSchema },
  responses: {
    200: json(AdapterWeightsSchema, "Per-projection adapter weight summary."),
    ...errors,
  },
});
const promote = createRoute({
  method: "put",
  path: `${base}/tasks/{task}/production`,
  operationId: "promoteTaskVersion",
  summary: "Promote task version",
  description:
    "Sets which task version serves requests. A version that is not yet available, such as an uploaded adapter, is first loaded and tested on a LoRA-enabled serving allocation of its base model and becomes available only when that succeeds; this can take up to a few minutes. 409 means the serving runtime rejected the adapter; 503 means no allocation could test it.",
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
  judge_model_id: task.judgeModelId,
  production_version_id: task.productionVersionId,
  training_schedule: task.trainingSchedule,
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

export const versionResponse = (
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

const listVersionFiles = createRoute({
  method: "get",
  path: `${base}/tasks/{task}/versions/{version_id}/files`,
  operationId: "listTaskVersionFiles",
  summary: "List version files",
  description:
    "Lists the files delivered with a task version, such as its report.md and the data files the report references.",
  tags: ["Training"],
  request: { params: TaskVersionPathSchema },
  responses: {
    200: json(TaskVersionFileListSchema, "The version's files."),
    ...errors,
  },
});
const createVersionFile = createRoute({
  method: "post",
  path: `${base}/tasks/{task}/versions/{version_id}/files`,
  operationId: "createTaskVersionFile",
  summary: "Create version file upload",
  description:
    "Staff only. Reserves a file on a task version and returns a signed upload URL that expires after one hour.",
  tags: ["Training"],
  request: {
    params: TaskVersionPathSchema,
    body: {
      required: true,
      content: { "application/json": { schema: CreateTaskVersionFileSchema } },
    },
  },
  responses: {
    201: json(TaskVersionFileUploadSchema, "A signed file upload URL."),
    ...errors,
  },
});
const completeVersionFile = createRoute({
  method: "put",
  path: `${base}/tasks/{task}/versions/{version_id}/files/{file_id}`,
  operationId: "completeTaskVersionFile",
  summary: "Complete version file upload",
  description:
    "Staff only. Publishes an uploaded file, replacing any file with the same name on the version.",
  tags: ["Training"],
  request: { params: TaskVersionFilePathSchema },
  responses: {
    200: json(TaskVersionFileSchema, "The published file."),
    ...errors,
  },
});
const deleteVersionFile = createRoute({
  method: "delete",
  path: `${base}/tasks/{task}/versions/{version_id}/files/{file_id}`,
  operationId: "deleteTaskVersionFile",
  summary: "Delete version file",
  description: "Staff only. Removes a file from a task version.",
  tags: ["Training"],
  request: { params: TaskVersionFilePathSchema },
  responses: {
    204: { description: "The file was deleted." },
    ...errors,
  },
});
const versionFileContent = createRoute({
  method: "get",
  path: `${base}/tasks/{task}/versions/{version_id}/files/{file_id}/content`,
  operationId: "getTaskVersionFileContent",
  summary: "Read version file",
  description:
    "Returns the text of a Markdown, CSV, JSON or plain-text file of at most 2 MiB, or a .eval.json file of at most 32 MiB.",
  tags: ["Training"],
  request: { params: TaskVersionFilePathSchema },
  responses: {
    200: json(TaskVersionFileContentSchema, "The file's text."),
    ...errors,
  },
});
const downloadVersionFile = createRoute({
  method: "get",
  path: `${base}/tasks/{task}/versions/{version_id}/files/{file_id}/download`,
  operationId: "getTaskVersionFileDownload",
  summary: "Download version file",
  description: "Gets a short-lived download link for a version file.",
  tags: ["Training"],
  request: { params: TaskVersionFilePathSchema },
  responses: {
    200: json(TaskVersionFileDownloadSchema, "A short-lived download link."),
    ...errors,
  },
});

const getVersionShare = createRoute({
  method: "get",
  path: `${base}/tasks/{task}/versions/{version_id}/share`,
  operationId: "getTaskVersionShare",
  summary: "Get public report link",
  description:
    "Gets the version's public, read-only report link. Anyone with the link can read report.md and the files it names; the signature cannot be derived without a server-side key.",
  tags: ["Training"],
  request: { params: TaskVersionPathSchema },
  responses: {
    200: json(TaskVersionShareSchema, "The public link."),
    ...errors,
  },
});
const sharedErrors = { 404: errors[404], 422: errors[422], 503: errors[503] };
const getSharedReport = createRoute({
  method: "get",
  path: "/api/v1/shared-reports/{version_id}/{signature}",
  operationId: "getSharedReport",
  summary: "Get shared report",
  description:
    "Public. Gets a shared version report's summary and the files it can read. Needs no authentication.",
  tags: ["Shared reports"],
  request: { params: SharedReportPathSchema },
  responses: {
    200: json(SharedReportSchema, "The shared report."),
    ...sharedErrors,
  },
});
const sharedAdapterWeights = createRoute({
  method: "get",
  path: "/api/v1/shared-reports/{version_id}/{signature}/adapter/weights",
  operationId: "getSharedAdapterWeights",
  summary: "Get shared adapter weight summary",
  description:
    "Public. Summarizes how a shared version's adapter changes each projection of the base model, as the workspace route does. Needs no authentication.",
  tags: ["Shared reports"],
  request: { params: SharedReportPathSchema },
  responses: {
    200: json(AdapterWeightsSchema, "Per-projection adapter weight summary."),
    ...sharedErrors,
  },
});
const sharedAdapterConfiguration = createRoute({
  method: "get",
  path: "/api/v1/shared-reports/{version_id}/{signature}/adapter/configuration",
  operationId: "getSharedAdapterConfiguration",
  summary: "Get shared adapter base structure",
  description:
    "Public. Gets the layer structure of a shared version's base model. Needs no authentication.",
  tags: ["Shared reports"],
  request: { params: SharedReportPathSchema },
  responses: {
    200: json(AdapterConfigurationSchema, "Pinned checkpoint structure."),
    ...sharedErrors,
  },
});
const sharedReportFileContent = createRoute({
  method: "get",
  path: "/api/v1/shared-reports/{version_id}/{signature}/files/{file_id}/content",
  operationId: "getSharedReportFileContent",
  summary: "Read shared report file",
  description:
    "Public. Returns the text of a shared report's Markdown, CSV, JSON or plain-text file.",
  tags: ["Shared reports"],
  request: { params: SharedReportFilePathSchema },
  responses: {
    200: json(TaskVersionFileContentSchema, "The file's text."),
    409: errors[409],
    ...sharedErrors,
  },
});
const sharedReportFileDownload = createRoute({
  method: "get",
  path: "/api/v1/shared-reports/{version_id}/{signature}/files/{file_id}/download",
  operationId: "getSharedReportFileDownload",
  summary: "Download shared report file",
  description:
    "Public. Gets a short-lived download link for a file a shared report names, such as an image.",
  tags: ["Shared reports"],
  request: { params: SharedReportFilePathSchema },
  responses: {
    200: json(TaskVersionFileDownloadSchema, "A short-lived download link."),
    ...sharedErrors,
  },
});

const fileResponse = (file: {
  id: string;
  name: string;
  contentType: string;
  sizeBytes: number;
  createdAt: Date;
}) => ({
  id: file.id,
  name: file.name,
  content_type: file.contentType,
  size_bytes: file.sizeBytes,
  created_at: file.createdAt.toISOString(),
});

const requireStaff = (user: {
  isStaff: boolean;
  emailVerified: boolean;
  impersonatedBy?: string | null;
}) => {
  if (!(user.isStaff && user.emailVerified) && !user.impersonatedBy)
    throw new ApiProblem(
      problems.forbidden("Only Gradiated staff can manage version files."),
    );
};

export const registerTrainingRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  training: TrainingService,
) => {
  app.openapi(adapterConfiguration, async (c) => {
    const user = await requireUser(c);
    const { workspace_id, model_id } = c.req.valid("param");
    return c.json(
      await training.uploads.configuration(user.id, workspace_id, model_id),
      200,
    );
  });
  app.openapi(createUpload, async (c) => {
    const user = await requireUser(c);
    const { workspace_id } = c.req.valid("param");
    c.header("Cache-Control", "no-store");
    return c.json(
      await training.uploads.create(user.id, workspace_id, c.req.valid("json")),
      201,
    );
  });
  app.openapi(completeUpload, async (c) => {
    const user = await requireUser(c);
    const { workspace_id, upload_id } = c.req.valid("param");
    const { task, version } = await training.uploads.complete(
      user.id,
      workspace_id,
      upload_id,
    );
    return c.json(versionResponse(task, version), 200);
  });
  app.openapi(startRun, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");

    const taskId = c.req.valid("json").task_id;
    const run = await training.startRun(user.id, p.workspace_id, taskId);
    c.get("analytics")?.trackWorkspace(user.id, "training_run_requested", {
      workspace_id: p.workspace_id,
      task_id: taskId,
      run_id: run.id,
    });

    return c.json(run, 202);
  });
  app.openapi(cancelRun, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    await training.cancelRun(user.id, p.workspace_id, p.run_id);

    c.get("analytics")?.trackWorkspace(
      user.id,
      "training_run_cancellation_requested",
      {
        workspace_id: p.workspace_id,
        run_id: p.run_id,
      },
    );

    return c.body(null, 202);
  });
  app.openapi(listTasks, async (c) => {
    const user = await requireUser(c);
    const { workspace_id } = c.req.valid("param");
    const tasks = await training.listTasks(user.id, workspace_id);
    return c.json(
      {
        data: tasks.map((task) => ({
          ...taskResponse(task),
          workload_benchmark: task.workloadBenchmark ?? null,
          latest_version: task.latestVersion
            ? versionResponse(task, task.latestVersion)
            : null,
          latest_run: task.latestRun
            ? {
                ...runResponse(task.latestRun),
                version_name: task.latestRun.versionName,
              }
            : null,
        })),
      },
      200,
    );
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
    c.get("analytics")?.trackWorkspace(user.id, "task_settings_updated", {
      workspace_id: p.workspace_id,
      task_id: task.id,
      changed_fields: changedFields(c.req.valid("json")),
    });

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
  app.openapi(getVersion, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const { task, version } = await training.getVersion(
      user.id,
      p.workspace_id,
      p.task,
      p.version_id,
    );
    return c.json(versionResponse(task, version), 200);
  });
  app.openapi(evaluationResults, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const results = await training.evaluationResults(
      user.id,
      p.workspace_id,
      p.task,
      p.version_id,
    );
    c.header("Cache-Control", "no-store");
    return c.json(results, 200);
  });
  app.openapi(downloadAdapter, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const download = await training.downloadAdapter(
      user.id,
      p.workspace_id,
      p.task,
      p.version_id,
    );
    c.header("Cache-Control", "no-store");
    return c.json(download, 200);
  });
  app.openapi(adapterWeights, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const weights = await training.adapterWeights(
      user.id,
      p.workspace_id,
      p.task,
      p.version_id,
    );
    // Versions never change their adapter, but membership can change.
    c.header("Cache-Control", "private, max-age=300");
    return c.json(weights, 200);
  });
  app.openapi(publishVersion, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const body = c.req.valid("json");
    const published = await training.artifacts.publish(
      user.id,
      p.workspace_id,
      {
        artifact: body.artifact,
        task: p.task,
        ...(body.name ? { name: body.name } : {}),
      },
    );
    if (published.created)
      c.get("analytics")?.trackWorkspace(user.id, "task_version_published", {
        workspace_id: p.workspace_id,
        task_id: published.task.id,
        version_id: published.version.id,
      });

    return c.json(
      {
        ...versionResponse(published.task, published.version),
        qualification: published.qualification,
      },
      published.created ? 201 : 200,
    );
  });
  app.openapi(deleteVersion, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    await training.artifacts.deleteVersion(
      user.id,
      p.workspace_id,
      p.task,
      p.version_id,
    );

    return c.body(null, 204);
  });
  app.openapi(listProductionChanges, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const changes = await training.listProductionChanges(
      user.id,
      p.workspace_id,
      p.task,
    );

    return c.json(
      {
        data: changes.map((change) => ({
          id: change.id,
          from_version_id: change.fromVersionId,
          to_version_id: change.toVersionId,
          actor: change.actor,
          created_at: change.createdAt.toISOString(),
        })),
      },
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
    c.get("analytics")?.trackWorkspace(user.id, "task_version_promoted", {
      workspace_id: p.workspace_id,
      task_id: task.id,
      // Promotion has just set it.
      version_id: task.productionVersionId!,
    });

    return c.json(taskResponse(task), 200);
  });
  app.openapi(getVersionShare, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const share = await training.shares.get(
      user.id,
      p.workspace_id,
      p.task,
      p.version_id,
    );
    c.header("Cache-Control", "no-store");
    return c.json(
      { version_id: share.versionId, signature: share.signature },
      200,
    );
  });
  const sharedHeaders = (c: {
    header: (name: string, value: string) => void;
  }) => {
    c.header("Cache-Control", "no-store");
    c.header("X-Robots-Tag", "noindex, nofollow");
    c.header("Referrer-Policy", "no-referrer");
  };
  app.openapi(getSharedReport, async (c) => {
    const { version_id, signature } = c.req.valid("param");
    const report = await training.shares.shared(version_id, signature);
    sharedHeaders(c);
    return c.json(
      {
        task: report.task,
        version: report.version,
        base_model_id: report.baseModelId,
        created_at: report.createdAt.toISOString(),
        adapter: {
          format: report.adapter.format,
          rank:
            report.adapter.format === "peft_lora" ? report.adapter.rank : null,
          num_tokens:
            report.adapter.format === "cartridge"
              ? report.adapter.num_tokens
              : null,
          size_bytes: report.adapter.size_bytes,
          checkpoint:
            report.adapter.validated_base_model_revision ??
            report.adapter.base_model_revision ??
            null,
        },
        files: report.files.map(fileResponse),
      },
      200,
    );
  });
  app.openapi(sharedAdapterWeights, async (c) => {
    const { version_id, signature } = c.req.valid("param");
    const weights = await training.sharedAdapterWeights(version_id, signature);
    sharedHeaders(c);
    return c.json(weights, 200);
  });
  app.openapi(sharedAdapterConfiguration, async (c) => {
    const { version_id, signature } = c.req.valid("param");
    const structure = await training.sharedAdapterConfiguration(
      version_id,
      signature,
    );
    sharedHeaders(c);
    return c.json(structure, 200);
  });
  app.openapi(sharedReportFileContent, async (c) => {
    const { version_id, signature, file_id } = c.req.valid("param");
    const content = await training.shares.sharedContent(
      version_id,
      signature,
      file_id,
    );
    sharedHeaders(c);
    return c.json(content, 200);
  });
  app.openapi(sharedReportFileDownload, async (c) => {
    const { version_id, signature, file_id } = c.req.valid("param");
    const download = await training.shares.sharedDownload(
      version_id,
      signature,
      file_id,
    );
    sharedHeaders(c);
    return c.json(download, 200);
  });
  app.openapi(listVersionFiles, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const files = await training.files.list(
      user.id,
      p.workspace_id,
      p.task,
      p.version_id,
    );
    return c.json({ data: files.map(fileResponse) }, 200);
  });
  app.openapi(createVersionFile, async (c) => {
    const user = await requireUser(c);
    requireStaff(user);
    const p = c.req.valid("param");
    c.header("Cache-Control", "no-store");
    return c.json(
      await training.files.create(
        user.id,
        p.workspace_id,
        p.task,
        p.version_id,
        c.req.valid("json"),
      ),
      201,
    );
  });
  app.openapi(completeVersionFile, async (c) => {
    const user = await requireUser(c);
    requireStaff(user);
    const p = c.req.valid("param");
    const file = await training.files.complete(
      user.id,
      p.workspace_id,
      p.task,
      p.version_id,
      p.file_id,
    );
    return c.json(fileResponse(file), 200);
  });
  app.openapi(deleteVersionFile, async (c) => {
    const user = await requireUser(c);
    requireStaff(user);
    const p = c.req.valid("param");
    await training.files.remove(
      user.id,
      p.workspace_id,
      p.task,
      p.version_id,
      p.file_id,
    );
    return c.body(null, 204);
  });
  app.openapi(versionFileContent, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    c.header("Cache-Control", "no-store");
    return c.json(
      await training.files.content(
        user.id,
        p.workspace_id,
        p.task,
        p.version_id,
        p.file_id,
      ),
      200,
    );
  });
  app.openapi(downloadVersionFile, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    c.header("Cache-Control", "no-store");
    return c.json(
      await training.files.download(
        user.id,
        p.workspace_id,
        p.task,
        p.version_id,
        p.file_id,
      ),
      200,
    );
  });
};
