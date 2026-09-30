import { and, eq, sql } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";
import {
  RUN_STAGE_ORDER,
  UuidSchema,
  RunStageSchema,
  TrainingRunEventSchema,
  TrainingRunEventPayloadSchema,
  RunDatasetSummarySchema,
  RunEvaluationSchema,
  isTerminalRunStage,
  type RunDatasetSummary,
  type RunEvaluation,
  type RunStage,
  type TaskVersionAdapter,
  type TrainingRunEventPayload,
} from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import {
  tasks,
  taskVersions,
  trainingRuns,
  trainingRunEvents,
} from "../db/schema/index.js";
import { TrainingInputSchema, type TrainingInput } from "./types.js";
import {
  TaskRecordSchema,
  RunRecordSchema,
  VersionRecordSchema,
  RunInsertSchema,
  RunUpdateSchema,
  RunResultFieldSchema,
  VersionInsertSchema,
  EventInsertSchema,
} from "./records.js";

type Transaction = Parameters<Parameters<ControlDatabase["transaction"]>[0]>[0];

const lockRun = async (tx: Transaction, runId: string) => {
  const [row] = await tx
    .select()
    .from(trainingRuns)
    .where(eq(trainingRuns.id, runId))
    .for("update");

  return row && RunRecordSchema.parse(row);
};

const insertEvents = async (
  tx: Transaction,
  runId: string,
  payloads: TrainingRunEventPayload[],
  {
    at = new Date(),
    source = "temporal-worker",
    attempt = 1,
  }: { at?: Date; source?: string; attempt?: number } = {},
) => {
  const events = EventInsertSchema.array().parse(
    payloads.map((payload) => ({ runId, at, source, attempt, payload })),
  );

  await tx.insert(trainingRunEvents).values(events);
};

const canTransition = (current: RunStage, next: RunStage) => {
  if (isTerminalRunStage(current) || current === next) return false;
  if (current === "cancelling") return next === "cancelled";
  if (isTerminalRunStage(next) || next === "cancelling") return true;

  return RUN_STAGE_ORDER.indexOf(next) > RUN_STAGE_ORDER.indexOf(current);
};

export const createTrainingRunStore = (database: ControlDatabase) => ({
  async create(runId: string, input: TrainingInput) {
    runId = UuidSchema.parse(runId);
    input = TrainingInputSchema.parse(input);

    await database.transaction(async (tx) => {
      const [created] = await tx
        .insert(trainingRuns)
        .values(
          RunInsertSchema.parse({
            id: runId,
            taskId: input.taskId,
            trigger: input.trigger,
            requestedBy: input.requestedBy,
            stage: "queued",
            baseModelId: input.baseModelId,
            inputCutoff: new Date(input.inputCutoff),
          }),
        )
        .onConflictDoNothing({ target: trainingRuns.id })
        .returning();
      if (!created) return;

      RunRecordSchema.parse(created);

      await insertEvents(tx, runId, [
        {
          type: "run_created",
          trigger: input.trigger,
          requested_by: input.requestedBy,
          base_model_id: input.baseModelId,
        },
        { type: "stage_entered", stage: "queued" },
      ]);
    });
  },

  async requestCancellation(runId: string, requestedBy: string) {
    runId = UuidSchema.parse(runId);
    requestedBy = UuidSchema.parse(requestedBy);

    await database.transaction(async (tx) => {
      const run = await lockRun(tx, runId);

      if (!run) throw new Error("Training run not found.");

      const [event] = await tx
        .select({ id: trainingRunEvents.id })
        .from(trainingRunEvents)
        .where(
          and(
            eq(trainingRunEvents.runId, runId),
            sql`${trainingRunEvents.payload}->>'type' = 'cancel_requested'`,
          ),
        )
        .limit(1);

      if (event) {
        TrainingRunEventSchema.pick({ id: true }).parse(event);
        return;
      }

      const now = new Date();
      await tx
        .update(trainingRuns)
        .set(
          RunUpdateSchema.parse({
            cancelRequestedAt: run.cancelRequestedAt ?? now,
            updatedAt: now,
          }),
        )
        .where(eq(trainingRuns.id, runId));

      await insertEvents(
        tx,
        runId,
        [{ type: "cancel_requested", requested_by: requestedBy }],
        { at: now, source: "api" },
      );
    });
  },

  async transition(runId: string, stage: RunStage, attempt = 1) {
    runId = UuidSchema.parse(runId);
    stage = RunStageSchema.parse(stage);
    attempt = TrainingRunEventSchema.shape.attempt.parse(attempt);

    await database.transaction(async (tx) => {
      const run = await lockRun(tx, runId);

      if (!run) throw new Error("Training run not found.");
      if (!canTransition(run.stage, stage)) return;

      const now = new Date();
      await tx
        .update(trainingRuns)
        .set(
          RunUpdateSchema.parse({
            stage,
            updatedAt: now,
            ...(isTerminalRunStage(stage) ? { finishedAt: now } : {}),
            ...(stage === "cancelling"
              ? { cancelRequestedAt: run.cancelRequestedAt ?? now }
              : {}),
          }),
        )
        .where(eq(trainingRuns.id, runId));

      const payloads: TrainingRunEventPayload[] = [
        { type: "stage_entered", stage },
      ];
      if (isTerminalRunStage(stage))
        payloads.push({ type: "run_finished", stage });

      await insertEvents(tx, runId, payloads, { at: now, attempt });
    });
  },

  async result(
    runId: string,
    field: "dataset" | "evaluation",
    value: RunDatasetSummary | RunEvaluation,
    payload: TrainingRunEventPayload,
    attempt: number,
  ) {
    runId = UuidSchema.parse(runId);
    field = RunResultFieldSchema.parse(field);
    value = (
      field === "dataset" ? RunDatasetSummarySchema : RunEvaluationSchema
    ).parse(value);
    payload = TrainingRunEventPayloadSchema.parse(payload);
    attempt = TrainingRunEventSchema.shape.attempt.parse(attempt);

    await database.transaction(async (tx) => {
      const run = await lockRun(tx, runId);

      if (
        !run ||
        isTerminalRunStage(run.stage) ||
        run.stage === "cancelling" ||
        run[field] !== null
      )
        return;

      await tx
        .update(trainingRuns)
        .set(RunUpdateSchema.parse({ [field]: value, updatedAt: new Date() }))
        .where(eq(trainingRuns.id, runId));

      await insertEvents(tx, runId, [payload], { attempt });
    });
  },

  async publish(
    runId: string,
    input: TrainingInput,
    adapter: TaskVersionAdapter,
    status: "available" | "unavailable",
  ) {
    runId = UuidSchema.parse(runId);
    input = TrainingInputSchema.parse(input);

    return database.transaction(async (tx) => {
      const [rawTask] = await tx
        .select()
        .from(tasks)
        .where(eq(tasks.id, input.taskId))
        .for("update");
      if (rawTask) TaskRecordSchema.parse(rawTask);

      const [rawExisting] = await tx
        .select()
        .from(taskVersions)
        .where(eq(taskVersions.trainingRunId, runId));
      const existing = rawExisting && VersionRecordSchema.parse(rawExisting);
      if (existing) return existing.id;

      const run = await lockRun(tx, runId);

      if (!run || run.stage !== "publishing")
        throw new Error("Run is not publishing.");

      const day = input.inputCutoff.slice(0, 10).replaceAll("-", "");
      const prefix = `${input.name}-${day}`;
      const versions = await tx
        .select({ name: taskVersions.name })
        .from(taskVersions)
        .where(eq(taskVersions.workspaceId, input.workspaceId));
      const names = new Set(
        VersionRecordSchema.pick({ name: true })
          .array()
          .parse(versions)
          .map(({ name }) => name),
      );
      let name = prefix;
      for (let ordinal = 2; names.has(name); ordinal++)
        name = `${prefix}-${ordinal}`;

      const id = uuidv7();

      await tx.insert(taskVersions).values(
        VersionInsertSchema.parse({
          id,
          workspaceId: input.workspaceId,
          taskId: input.taskId,
          trainingRunId: runId,
          name,
          baseModelId: input.baseModelId,
          adapter,
          status,
        }),
      );
      await insertEvents(tx, runId, [
        { type: "published", version_id: id, name },
      ]);

      return id;
    });
  },
});
