import { WorkloadBenchmarkSchema } from "./workload-benchmark.js";
import { CronExpressionParser } from "cron-parser";
import { z } from "@hono/zod-openapi";

import {
  ModelIdSchema,
  pageFields,
  TimestampSchema,
  UuidSchema,
} from "./common.js";

import { isEvaluationModelId } from "./model-catalog.js";
import { RUN_STAGES, TERMINAL_RUN_STAGES } from "./training-stages.js";

export * from "./training-stages.js";

export const EvaluationJudgeSchema = ModelIdSchema.refine(
  isEvaluationModelId,
  "Choose a supported evaluation model.",
).openapi("EvaluationJudge");
export type EvaluationJudge = z.infer<typeof EvaluationJudgeSchema>;

export const TRAINING_TRIGGERS = ["automation", "manual"] as const;
export const TASK_VERSION_STATUSES = ["available", "unavailable"] as const;

export const RunStageSchema = z.enum(RUN_STAGES).openapi("RunStage");

const TerminalStageSchema = z.enum(TERMINAL_RUN_STAGES);
const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const CountSchema = z.number().int().nonnegative();
const FractionSchema = z.number().min(0).max(1);

export const RunDatasetSummarySchema = z
  .object({
    oldest_trace_at: TimestampSchema.optional(),
    newest_trace_at: TimestampSchema.optional(),
    eligible_examples: CountSchema,
    duplicates_removed: CountSchema,
    train: CountSchema,
    validation: CountSchema,
    test: CountSchema,
    evaluation_examples: CountSchema.optional(),
  })
  .openapi("RunDatasetSummary");
export type RunDatasetSummary = z.infer<typeof RunDatasetSummarySchema>;

const JudgeOutcomeSchema = z.object({
  comparator_model_id: ModelIdSchema,
  win: FractionSchema,
  tie: FractionSchema,
  loss: FractionSchema,
  unresolved: FractionSchema,
});

const PairSchema = z.object({
  fine_tuned: z.number().nonnegative(),
  comparison: z.number().nonnegative(),
});

export const RunEvaluationSchema = z
  .object({
    judging_method: z.enum(["randomized_single", "both_orders"]).optional(),
    holdout_groups: CountSchema,
    holdout_examples: CountSchema,
    comparison_model_id: ModelIdSchema,
    judge_model_id: EvaluationJudgeSchema,
    vs_comparison: JudgeOutcomeSchema,
    cost_per_request_nano_usd: PairSchema.nullable(),
    cost_basis: z
      .enum(["placeholder_output_only", "catalog_token_estimate"])
      .optional(),
    output_tokens_per_second: PairSchema,
    error_rate: FractionSchema,
  })
  .openapi("RunEvaluation");
export type RunEvaluation = z.infer<typeof RunEvaluationSchema>;

const AdapterArtifactFields = {
  artifact_uri: z.string().startsWith("s3://"),
  sha256: Sha256Schema,
  size_bytes: CountSchema,
  base_model_revision: z
    .string()
    .min(1)
    .max(300)
    .optional()
    .describe(
      "Immutable training checkpoint declared in the adapter config, when known.",
    ),
  declared_base_model_revision: z.string().max(300).optional(),
  validated_base_model_revision: z
    .string()
    .regex(/^[0-9a-f]{40}$/)
    .optional()
    .describe(
      "Supported base checkpoint used for deterministic tensor validation; this is not proof of training provenance.",
    ),
};
export const PeftLoraAdapterSchema = z
  .object({
    format: z.literal("peft_lora"),
    ...AdapterArtifactFields,
    rank: z.number().int().positive(),
  })
  .openapi("PeftLoraAdapter");
export const CARTRIDGE_FILE = "cartridge.safetensors";
export const CARTRIDGE_FORMAT = "gradiated.cartridge/1";
export const CartridgeAdapterSchema = z
  .object({
    format: z.literal("cartridge"),
    ...AdapterArtifactFields,
    num_tokens: z
      .number()
      .int()
      .positive()
      .describe("Prompt positions the cartridge occupies."),
    hidden_size: z.number().int().positive(),
    placement: z.literal("system_prompt_start"),
    separator: z
      .string()
      .max(64)
      .describe("Text placed between the cartridge and the system prompt."),
    has_slot_token_ids: z
      .boolean()
      .describe(
        "Whether the cartridge records the token IDs it was trained behind.",
      ),
  })
  .openapi("CartridgeAdapter");
export const TaskVersionAdapterSchema = z
  .discriminatedUnion("format", [PeftLoraAdapterSchema, CartridgeAdapterSchema])
  .openapi("TaskVersionAdapter");
export type TaskVersionAdapter = z.infer<typeof TaskVersionAdapterSchema>;
export type PeftLoraAdapter = z.infer<typeof PeftLoraAdapterSchema>;
export type CartridgeAdapter = z.infer<typeof CartridgeAdapterSchema>;

const GpuSchema = z.object({
  type: z.string(),
  count: z.number().int().positive(),
});

export const TrainingMetricsSchema = z
  .record(z.string().min(1).max(128), z.number())
  .refine(
    (metrics) => Object.keys(metrics).length <= 64,
    "At most 64 metrics per event",
  )
  .describe(
    "Additional finite numeric measurements; metric names are extensible.",
  );

export const RunProgressSchema = z
  .object({
    step: CountSchema.describe(
      "Completed optimizer updates, cumulative across checkpoint resumes.",
    ),
    total_steps: z.number().int().positive().optional(),
    train_loss: z
      .number()
      .optional()
      .describe(
        "Primary training objective loss for this logging interval; its definition and aggregation belong to the training recipe.",
      ),
    tokens_per_second: z
      .number()
      .nonnegative()
      .optional()
      .describe(
        "Non-padding input tokens per second across all training devices in this logging interval.",
      ),
    eta_seconds: z.number().nonnegative().optional(),
    metrics: TrainingMetricsSchema.optional(),
  })
  .openapi("RunProgress");
export type RunProgress = z.infer<typeof RunProgressSchema>;

export const TrainerObservationSchema = z
  .object({
    name: z.string().min(1).max(128),
    message: z.string().min(1),
    level: z.enum(["debug", "info", "warning", "error"]).optional(),
    step: CountSchema.optional(),
    metrics: TrainingMetricsSchema.optional(),
    details: z.record(z.string(), z.unknown()).optional(),
  })
  .openapi("TrainerObservation");
export type TrainerObservation = z.infer<typeof TrainerObservationSchema>;

const event = <Type extends string, Shape extends z.ZodRawShape>(
  type: Type,
  shape: Shape,
) => z.object({ type: z.literal(type), ...shape });

export const TrainerEventPayloadSchema = z.discriminatedUnion("type", [
  event("trainer_progress", RunProgressSchema.shape),
  event("trainer_observation", TrainerObservationSchema.shape),
  event("trainer_checkpoint", {
    step: CountSchema,
    key: z.string().min(1),
    sha256: Sha256Schema,
    size_bytes: z.number().int().positive(),
  }),
]);
export type TrainerEventPayload = z.infer<typeof TrainerEventPayloadSchema>;

export const TrainingRunEventPayloadSchema = z
  .discriminatedUnion("type", [
    event("run_created", {
      trigger: z.enum(TRAINING_TRIGGERS),
      requested_by: UuidSchema.nullable(),
      base_model_id: ModelIdSchema,
    }),
    event("stage_entered", { stage: RunStageSchema }),
    event("dataset_built", RunDatasetSummarySchema.shape),
    event("capacity_granted", { host_id: z.string(), gpu: GpuSchema }),
    event("job_submitted", {
      runner: z.string(),
      provider_job_id: z.string(),
      host_id: z.string(),
      gpu: GpuSchema,
    }),
    event("job_status", {
      state: z.enum(["running", "complete", "lost", "failed"]),
      message: z.string().optional(),
    }),
    event("artifact_verified", {
      version_id: UuidSchema,
      sha256: Sha256Schema,
      size_bytes: CountSchema,
    }),
    event("adapter_loaded", { host_id: z.string() }),
    event("evaluation_progress", {
      completed: CountSchema,
      total: CountSchema,
    }),
    event("evaluation_completed", {
      judge: EvaluationJudgeSchema,
      groups: CountSchema,
      win: FractionSchema,
      tie: FractionSchema,
      loss: FractionSchema,
      unresolved: FractionSchema,
    }),
    event("published", { version_id: UuidSchema, name: z.string() }),
    event("cancel_requested", { requested_by: UuidSchema }),
    event("run_finished", {
      stage: TerminalStageSchema,
      error_code: z.enum(["internal", "attempt_deadline"]).optional(),
      message: z.string().optional(),
    }),
    event("note", {
      level: z.enum(["info", "warning", "error"]),
      message: z.string(),
    }),
    ...TrainerEventPayloadSchema.options,
  ])
  .openapi("TrainingRunEventPayload");
export type TrainingRunEventPayload = z.infer<
  typeof TrainingRunEventPayloadSchema
>;

export const TrainingRunEventSchema = z
  .object({
    id: z.number().int().positive(),
    at: TimestampSchema,
    source: z
      .string()
      .regex(/^[a-z][a-z0-9_-]{0,63}$/)
      .describe(
        "Service that emitted the event, such as api, worker or trainer.",
      ),
    attempt: z.number().int().positive(),
    payload: TrainingRunEventPayloadSchema,
  })
  .openapi("TrainingRunEvent");

export const TrainingRunSchema = z
  .object({
    id: UuidSchema,
    task: z.string(),
    trigger: z.enum(TRAINING_TRIGGERS),
    requested_by: UuidSchema.nullable(),
    stage: RunStageSchema,
    base_model_id: ModelIdSchema,
    input_cutoff: TimestampSchema,
    dataset: RunDatasetSummarySchema.nullable(),
    evaluation: RunEvaluationSchema.nullable(),
    version_id: UuidSchema.nullable(),
    cancel_requested_at: TimestampSchema.nullable(),
    created_at: TimestampSchema,
    finished_at: TimestampSchema.nullable(),
  })
  .openapi("TrainingRun");
export type TrainingRun = z.infer<typeof TrainingRunSchema>;

export const TaskVersionSchema = z
  .object({
    id: UuidSchema,
    name: z.string(),
    task: z.string(),
    training_run_id: UuidSchema.nullable(),
    base_model_id: ModelIdSchema,
    adapter: TaskVersionAdapterSchema,
    status: z
      .enum(TASK_VERSION_STATUSES)
      .describe(
        "Durable serving eligibility. Available versions may be called or promoted after serving validation; this does not indicate runtime health or adapter cache residency.",
      ),
    is_production: z.boolean(),
    created_at: TimestampSchema,
  })
  .openapi("TaskVersion");
export type TaskVersion = z.infer<typeof TaskVersionSchema>;

export const TaskTrainingScheduleSchema = z
  .string()
  .trim()
  .min(1)
  .max(256)
  .refine((expression) => {
    const fields = expression.split(/\s+/);
    const numeric = expression
      .toUpperCase()
      .replace(
        /JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|SUN|MON|TUE|WED|THU|FRI|SAT/g,
        "1",
      );
    if (fields.length !== 5 || !/^[\d*,/\-\s]+$/.test(numeric)) return false;

    try {
      CronExpressionParser.parse(expression, { tz: "UTC" });
      return true;
    } catch {
      return false;
    }
  }, "Provide a valid five-field cron expression.")
  .nullable()
  .describe(
    "Automatic training cron in UTC (minute, hour, day of month, month, day of week). Supports lists, ranges, steps and month/day names. Day of month and day of week must both match when restricted. Null disables automatic training.",
  )
  .openapi("TaskTrainingSchedule");
export type TaskTrainingSchedule = z.infer<typeof TaskTrainingScheduleSchema>;

export const TaskSchema = z
  .object({
    id: UuidSchema,
    name: z.string(),
    base_model_id: ModelIdSchema.nullable(),
    comparison_model_id: ModelIdSchema.nullable(),
    production_version_id: UuidSchema.nullable(),
    judge_model_id: EvaluationJudgeSchema,
    training_schedule: TaskTrainingScheduleSchema,
  })
  .openapi("Task");
export type Task = z.infer<typeof TaskSchema>;

export const UpdateTaskSchema = z
  .strictObject({
    base_model_id: ModelIdSchema.describe(
      "The catalog model ID that new versions are trained from.",
    ),
    comparison_model_id: ModelIdSchema.refine(
      isEvaluationModelId,
      "Choose a supported comparison model.",
    ).describe(
      "The catalog model ID that evaluations compare trained versions against.",
    ),
    judge_model_id: EvaluationJudgeSchema.describe(
      "The catalog model ID that judges evaluations.",
    ),
    training_schedule: TaskTrainingScheduleSchema,
  })
  .partial()
  .refine(
    (input) => Object.keys(input).length > 0,
    "Provide at least one task field.",
  )
  .openapi("UpdateTask");
export type UpdateTask = z.infer<typeof UpdateTaskSchema>;

// Versions are named uniquely within their task, so either the name or the ID finds one.
export const VersionReferenceSchema = z
  .string()
  .min(1)
  .max(256)
  .describe("The version's name or ID.");

export const PromoteVersionSchema = z
  .strictObject({ version_id: VersionReferenceSchema })
  .openapi("PromoteVersion");

const WorkspacePathSchema = z.object({ workspace_id: UuidSchema });

export const TaskNameSchema = z
  .string()
  .min(1)
  .max(256)
  .refine(
    (name) => name !== "." && name !== "..",
    "Task names cannot be URL dot segments.",
  );
// `<organization slug>/<task>/<version>` must fit the 300-character model ID.
export const MAX_MODEL_NAME_SEGMENT_LENGTH = 128;
export const ModelNameSegmentSchema = TaskNameSchema.max(
  MAX_MODEL_NAME_SEGMENT_LENGTH,
).refine((name) => !name.includes("/"), "Names cannot contain '/'.");

export const TaskPathSchema = WorkspacePathSchema.extend({
  task: TaskNameSchema.describe(
    "The task's name, as sent in the capture header and shown in the console.",
  ),
});
export const TrainingRunPathSchema = WorkspacePathSchema.extend({
  run_id: UuidSchema,
});
export const TrainingRunListQuerySchema = z.object({
  task_id: UuidSchema.optional().describe(
    "Filter runs by task ID within this workspace.",
  ),
});
export type TrainingRunListQuery = z.infer<typeof TrainingRunListQuerySchema>;

export const TrainingRunEventsQuerySchema = z.object({
  after: z.coerce.number().int().nonnegative().optional(),
  limit: z.coerce.number().int().min(1).max(1_000).default(500),
});

export const TaskListItemSchema = TaskSchema.extend({
  workload_benchmark: WorkloadBenchmarkSchema.nullable()
    .optional()
    .describe(
      "Manual workload benchmark for the latest version, if available.",
    ),
  latest_version: TaskVersionSchema.nullable()
    .optional()
    .describe("Latest model version, including externally uploaded adapters."),
  latest_run: TrainingRunSchema.extend({ version_name: z.string().nullable() })
    .nullable()
    .describe(
      "Latest training run by creation time, with its own recorded evaluation and published version name.",
    ),
}).openapi("TaskListItem");
export const TaskListSchema = z
  .object({ data: z.array(TaskListItemSchema) })
  .openapi("TaskList");
export const TrainingRunListSchema = z
  .object({ data: z.array(TrainingRunSchema) })
  .openapi("TrainingRunList");
export const TaskVersionListSchema = z
  .object({ data: z.array(TaskVersionSchema) })
  .openapi("TaskVersionList");
export const TrainingRunEventListSchema = z
  .object(pageFields(TrainingRunEventSchema))
  .openapi("TrainingRunEventList");

export const TaskVersionPathSchema = TaskPathSchema.extend({
  version_id: VersionReferenceSchema,
});
export const AdapterDownloadSchema = z
  .object({
    url: z.url().describe("Short-lived signed URL for the adapter archive."),
    expires_at: TimestampSchema.describe(
      "Latest expiry of the download URL; temporary storage credentials may expire sooner.",
    ),
  })
  .openapi("AdapterDownload");
const FeatureCountSchema = z.number().int().positive().max(1_000_000);
export const AdapterWeightModuleSchema = z
  .object({
    module: z
      .string()
      .min(1)
      .max(256)
      .describe(
        "Module path inside a decoder layer, such as self_attn.q_proj, or lm_head. Expert indices are folded into one module.",
      ),
    layer: z
      .number()
      .int()
      .nonnegative()
      .nullable()
      .describe("Decoder layer index; null for lm_head."),
    shape: z
      .tuple([FeatureCountSchema, FeatureCountSchema])
      .describe("Output and input features of the adapted projection."),
    experts: z
      .number()
      .int()
      .positive()
      .describe("Experts folded into this module; 1 for a dense projection."),
    rank: z.number().int().positive(),
    norm: z
      .number()
      .nonnegative()
      .describe(
        "Frobenius norm of the update the adapter adds: ΔW = scale · B · A.",
      ),
    singular_values: z
      .array(z.number().nonnegative())
      .max(1024)
      .describe(
        "Singular values of ΔW, largest first. Empty when the module folds several experts or the rank is above 64.",
      ),
    heatmap_shape: z
      .tuple([FeatureCountSchema, FeatureCountSchema])
      .describe("Rows (output blocks) and columns (input blocks) of heatmap."),
    heatmap: z
      .string()
      .max(8192)
      .describe(
        "Base64 bytes, row-major. Each byte is the Frobenius norm of one block of ΔW, with 255 at heatmap_max.",
      ),
    heatmap_max: z.number().nonnegative(),
  })
  .openapi("AdapterWeightModule");
export const AdapterWeightsSchema = z
  .object({
    rank: z.number().int().positive(),
    alpha: z.number().positive(),
    scale: z
      .number()
      .positive()
      .describe("Multiplier PEFT applies to B · A: alpha / rank."),
    parameters: CountSchema.describe("LoRA A and B parameters in the adapter."),
    modules: z.array(AdapterWeightModuleSchema).max(16_384),
  })
  .openapi("AdapterWeights");
export type AdapterWeights = z.infer<typeof AdapterWeightsSchema>;
export type AdapterWeightModule = z.infer<typeof AdapterWeightModuleSchema>;
export const StartTrainingRunSchema = z
  .object({
    task_id: UuidSchema.describe("Task to train within this workspace."),
  })
  .openapi("StartTrainingRun");

export const StartTrainingRunResponseSchema = z
  .object({ id: UuidSchema })
  .openapi("StartTrainingRunResponse");

const EvaluationPredictionSchema = z.object({
  cost_nano_usd: CountSchema.optional().describe(
    "Saved token cost estimate in nano-USD.",
  ),
  text: z.string(),
  tokens: z.number().int().nonnegative(),
  seconds: z.number().positive(),
  usage: z
    .object({
      input_tokens: CountSchema,
      output_tokens: CountSchema,
      cached_input_tokens: CountSchema.optional(),
      cache_write_tokens: CountSchema.optional(),
    })
    .optional(),
});
const EvaluationPairSchema = z.object({
  id: z.string(),
  group: z.string(),
  fine_tuned: EvaluationPredictionSchema,
  comparison: EvaluationPredictionSchema,
});
export const EvaluationResultsSchema = z
  .array(
    z.union([
      EvaluationPairSchema.extend({
        judgment: z.string(),
        fine_tuned_first: z.boolean(),
      }),
      EvaluationPairSchema.extend({ judgments: z.array(z.string()).length(2) }),
    ]),
  )
  .min(1)
  .max(64)
  .openapi("EvaluationResults");

export const MAX_UPLOADED_ADAPTER_RANK = 8;
export const MAX_ADAPTER_BYTES = 512 * 1024 * 1024;
export const MAX_CARTRIDGE_BYTES = 4 * 1024 * 1024 * 1024;
const UploadTargetFields = {
  task: ModelNameSegmentSchema,
  create_task: z.boolean().default(false),
  name: z
    .string()
    .trim()
    .min(1)
    .max(MAX_MODEL_NAME_SEGMENT_LENGTH)
    .regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/),
  base_model_id: ModelIdSchema,
};
export const LoraModelUploadSchema = z.strictObject({
  format: z.literal("peft_lora").default("peft_lora"),
  ...UploadTargetFields,
  base_model_revision: z
    .string()
    .regex(/^[0-9a-f]{40}$/)
    .optional()
    .describe(
      "Legacy hint; the uploaded config determines declared training provenance.",
    ),
  config_size: z.number().int().min(2).max(65536),
  weights_size: z.number().int().positive().max(MAX_ADAPTER_BYTES),
});
const CartridgeUploadSchema = z.strictObject({
  format: z.literal("cartridge"),
  ...UploadTargetFields,
  cartridge_size: z
    .number()
    .int()
    .positive()
    .max(MAX_CARTRIDGE_BYTES)
    .describe(`Size of ${CARTRIDGE_FILE} in bytes.`),
});
export const CreateModelUploadSchema = z
  .union([CartridgeUploadSchema, LoraModelUploadSchema])
  .openapi("CreateModelUpload");
export const ModelUploadSchema = z
  .object({
    id: UuidSchema,
    config_url: z.url().optional().describe("LoRA uploads only."),
    weights_url: z.url().optional().describe("LoRA uploads only."),
    cartridge_url: z.url().optional().describe("Cartridge uploads only."),
    expires_at: TimestampSchema,
  })
  .openapi("ModelUpload");
export const ModelUploadPathSchema = WorkspacePathSchema.extend({
  upload_id: UuidSchema,
});
export type CreateModelUpload = z.infer<typeof CreateModelUploadSchema>;
export type CreateModelUploadInput = z.input<typeof CreateModelUploadSchema>;

export const MAX_VERSION_FILE_BYTES = 100 * 1024 * 1024;
export const MAX_VERSION_FILE_CONTENT_BYTES = 2 * 1024 * 1024;
export const VERSION_REPORT_FILE = "report.md";

export const VersionFileNameSchema = z
  .string()
  .regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/)
  .describe(
    "File name within the version, such as report.md or eval-samples.csv. Reports reference data files by this name.",
  );
export const TaskVersionFileSchema = z
  .object({
    id: UuidSchema,
    name: VersionFileNameSchema,
    content_type: z.string().min(1).max(200),
    size_bytes: CountSchema,
    created_at: TimestampSchema,
  })
  .openapi("TaskVersionFile");
export const TaskVersionFileListSchema = z
  .object({ data: z.array(TaskVersionFileSchema) })
  .openapi("TaskVersionFileList");
export const CreateTaskVersionFileSchema = z
  .object({
    name: VersionFileNameSchema,
    size_bytes: z.number().int().positive().max(MAX_VERSION_FILE_BYTES),
    content_type: z
      .string()
      .min(1)
      .max(200)
      .default("application/octet-stream"),
  })
  .openapi("CreateTaskVersionFile");
export const TaskVersionFileUploadSchema = z
  .object({
    id: UuidSchema,
    upload_url: z.url().describe("Signed URL to PUT the file's bytes to."),
    expires_at: TimestampSchema,
  })
  .openapi("TaskVersionFileUpload");
export const TaskVersionFilePathSchema = TaskVersionPathSchema.extend({
  file_id: z
    .string()
    .min(1)
    .max(256)
    .describe("The file's name, such as report.md, or its ID."),
});
export const TaskVersionFileContentSchema = z
  .object({
    name: VersionFileNameSchema,
    content_type: z.string(),
    content: z.string().describe("UTF-8 text of the file."),
  })
  .openapi("TaskVersionFileContent");
export const TaskVersionFileDownloadSchema = z
  .object({
    url: z.url().describe("Short-lived signed URL for the file."),
    expires_at: TimestampSchema,
  })
  .openapi("TaskVersionFileDownload");
export type CreateTaskVersionFile = z.infer<typeof CreateTaskVersionFileSchema>;

export const ReportShareSignatureSchema = z
  .string()
  .regex(/^[A-Za-z0-9_-]{43}$/)
  .describe(
    "HMAC-SHA256 of the version ID under a server-side key, base64url-encoded.",
  );
export const TaskVersionShareSchema = z
  .object({
    version_id: UuidSchema,
    signature: ReportShareSignatureSchema,
  })
  .openapi("TaskVersionShare");
export const SharedReportPathSchema = z.object({
  version_id: UuidSchema,
  signature: ReportShareSignatureSchema,
});
export const SharedReportFilePathSchema = SharedReportPathSchema.extend({
  file_id: UuidSchema,
});
export const SharedReportSchema = z
  .object({
    task: z.string(),
    version: z.string().describe("Version name."),
    base_model_id: ModelIdSchema,
    created_at: TimestampSchema.describe("When the version was delivered."),
    adapter: z.object({
      format: z.enum(["peft_lora", "cartridge"]),
      rank: z
        .number()
        .int()
        .positive()
        .nullable()
        .describe("LoRA rank; null for cartridges."),
      num_tokens: z
        .number()
        .int()
        .positive()
        .nullable()
        .describe("Cartridge positions; null for LoRA adapters."),
      size_bytes: CountSchema,
      checkpoint: z
        .string()
        .nullable()
        .describe("Base model revision the adapter applies to, when known."),
    }),
    files: z
      .array(TaskVersionFileSchema)
      .describe("report.md and the files it references by name."),
  })
  .openapi("SharedReport");
export type SharedReport = z.infer<typeof SharedReportSchema>;
