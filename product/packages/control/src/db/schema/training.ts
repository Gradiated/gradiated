import { sql } from "drizzle-orm";
import {
  bigint,
  boolean,
  check,
  foreignKey,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  timestamp,
  unique,
  uniqueIndex,
  uuid,
  type AnyPgColumn,
} from "drizzle-orm/pg-core";

import {
  RUN_STAGES,
  DEFAULT_EVALUATION_JUDGE,
  DEFAULT_COMPARISON_MODEL,
  type EvaluationJudge,
  TASK_VERSION_STATUSES,
  TRAINING_TRIGGERS,
  type RunDatasetSummary,
  type RunEvaluation,
  type TaskVersionAdapter,
  type TrainingRunEventPayload,
} from "@gradiated/contracts";

import { users } from "./auth.js";
import { models, workspaces } from "./organizations.js";

const timestamps = {
  createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
    .defaultNow()
    .notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
    .defaultNow()
    .notNull(),
};

const inList = (values: readonly string[]) =>
  sql.raw(values.map((value) => `'${value}'`).join(", "));

export const tasks = pgTable(
  "tasks",
  {
    id: uuid("id").primaryKey(),
    // Null for trace-only tasks. Set when the task first trains or takes an
    // upload, which makes its name a model name, unique across the organization.
    organizationId: uuid("organization_id"),
    workspaceId: uuid("workspace_id")
      .notNull()
      .references(() => workspaces.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    trainingSchedule: text("training_schedule").default(
      sql`floor(random() * 60)::integer::text || ' ' || floor(random() * 24)::integer::text || ' * * ' || floor(random() * 7)::integer::text`,
    ),
    baseModelId: text("base_model_id").references(() => models.id, {
      onDelete: "restrict",
    }),
    comparisonModelId: text("comparison_model_id").default(
      DEFAULT_COMPARISON_MODEL,
    ),
    judgeModelId: text("judge_model_id")
      .$type<EvaluationJudge>()
      .notNull()
      .default(DEFAULT_EVALUATION_JUDGE),
    productionVersionId: uuid("production_version_id").references(
      (): AnyPgColumn => taskVersions.id,
      { onDelete: "set null" },
    ),
    ...timestamps,
  },
  (table) => [
    foreignKey({
      name: "tasks_organization_workspace_fk",
      columns: [table.organizationId, table.workspaceId],
      foreignColumns: [workspaces.organizationId, workspaces.id],
    }).onDelete("cascade"),
    // Models are named `<organization slug>/<task>/<version>`.
    unique("tasks_organization_name_unique").on(
      table.organizationId,
      table.name,
    ),
    unique("tasks_workspace_name_unique").on(table.workspaceId, table.name),
    unique("tasks_id_workspace_unique").on(table.id, table.workspaceId),
    check("tasks_name_routable_check", sql`${table.name} not in ('.', '..')`),
    check(
      "tasks_model_name_check",
      sql`${table.organizationId} is null or (strpos(${table.name}, '/') = 0 and char_length(${table.name}) <= 128)`,
    ),
  ],
);

export const trainingRuns = pgTable(
  "training_runs",
  {
    id: uuid("id").primaryKey(),
    taskId: uuid("task_id")
      .notNull()
      .references(() => tasks.id, { onDelete: "cascade" }),
    workflowId: text("workflow_id"),
    trigger: text("trigger", { enum: TRAINING_TRIGGERS }).notNull(),
    requestedBy: uuid("requested_by").references(() => users.id, {
      onDelete: "set null",
    }),
    stage: text("stage", { enum: RUN_STAGES }).notNull(),
    baseModelId: text("base_model_id")
      .notNull()
      .references(() => models.id, { onDelete: "restrict" }),
    inputCutoff: timestamp("input_cutoff", {
      withTimezone: true,
      mode: "date",
    }).notNull(),
    dataset: jsonb("dataset").$type<RunDatasetSummary>(),
    evaluation: jsonb("evaluation").$type<RunEvaluation>(),
    cancelRequestedAt: timestamp("cancel_requested_at", {
      withTimezone: true,
      mode: "date",
    }),
    finishedAt: timestamp("finished_at", { withTimezone: true, mode: "date" }),
    ...timestamps,
  },
  (table) => [
    check(
      "training_runs_trigger_check",
      sql`${table.trigger} in (${inList(TRAINING_TRIGGERS)})`,
    ),
    check(
      "training_runs_stage_check",
      sql`${table.stage} in (${inList(RUN_STAGES)})`,
    ),
    unique("training_runs_id_task_unique").on(table.id, table.taskId),
    uniqueIndex("training_runs_one_active_per_task")
      .on(table.taskId)
      .where(sql`${table.finishedAt} is null`),
    index("training_runs_task_created_index").on(table.taskId, table.createdAt),
  ],
);

export const trainingRunEvents = pgTable(
  "training_run_events",
  {
    id: bigint("id", { mode: "number" })
      .primaryKey()
      .generatedAlwaysAsIdentity(),
    runId: uuid("run_id")
      .notNull()
      .references(() => trainingRuns.id, { onDelete: "cascade" }),
    at: timestamp("at", { withTimezone: true, mode: "date" }).notNull(),
    source: text("source").notNull(),
    attempt: integer("attempt").notNull(),
    payload: jsonb("payload").$type<TrainingRunEventPayload>().notNull(),
  },
  (table) => [
    check(
      "training_run_events_source_check",
      sql`${table.source} ~ '^[a-z][a-z0-9_-]{0,63}$'`,
    ),
    index("training_run_events_run_index").on(table.runId, table.id),
  ],
);

export const taskVersions = pgTable(
  "task_versions",
  {
    id: uuid("id").primaryKey(),
    workspaceId: uuid("workspace_id")
      .notNull()
      .references(() => workspaces.id, { onDelete: "cascade" }),
    taskId: uuid("task_id")
      .notNull()
      .references(() => tasks.id, { onDelete: "cascade" }),
    trainingRunId: uuid("training_run_id")
      .unique()
      .references(() => trainingRuns.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    baseModelId: text("base_model_id")
      .notNull()
      .references(() => models.id, { onDelete: "restrict" }),
    adapter: jsonb("adapter").$type<TaskVersionAdapter>().notNull(),
    status: text("status", { enum: TASK_VERSION_STATUSES }).notNull(),
    ...timestamps,
  },
  (table) => [
    check(
      "task_versions_status_check",
      sql`${table.status} in (${inList(TASK_VERSION_STATUSES)})`,
    ),
    foreignKey({
      name: "task_versions_task_workspace_fk",
      columns: [table.taskId, table.workspaceId],
      foreignColumns: [tasks.id, tasks.workspaceId],
    }).onDelete("cascade"),
    foreignKey({
      name: "task_versions_run_task_fk",
      columns: [table.trainingRunId, table.taskId],
      foreignColumns: [trainingRuns.id, trainingRuns.taskId],
    }).onDelete("cascade"),
    unique("task_versions_task_name_unique").on(table.taskId, table.name),
    index("task_versions_task_created_index").on(table.taskId, table.createdAt),
  ],
);

export const modelUploads = pgTable("model_uploads", {
  id: uuid("id").primaryKey(),
  workspaceId: uuid("workspace_id")
    .notNull()
    .references(() => workspaces.id, { onDelete: "cascade" }),
  input: jsonb("input")
    .$type<import("@gradiated/contracts").CreateModelUpload>()
    .notNull(),
  createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
    .defaultNow()
    .notNull(),
  versionId: uuid("version_id").references(() => taskVersions.id, {
    onDelete: "set null",
  }),
});
