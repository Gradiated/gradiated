import { and, eq, lt, isNull, isNotNull, or } from "drizzle-orm";
import { z } from "zod";
import { v7 as uuidv7 } from "uuid";
import {
  CreateModelUploadSchema,
  UuidSchema,
  EvaluationJudgeSchema,
  type TaskVersionAdapter,
} from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import {
  modelUploads,
  tasks,
  taskVersions,
  workspaces,
} from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";
import {
  TaskRecordSchema,
  VersionInsertSchema,
  VersionRecordSchema,
} from "./records.js";

const UploadSchema = z.object({
  id: UuidSchema,
  workspaceId: UuidSchema,
  input: CreateModelUploadSchema,
  createdAt: z.date(),
  versionId: UuidSchema.nullable(),
});

export const createModelUploadStore = (database: ControlDatabase) => ({
  async cleanupCandidate(before: Date) {
    const [row] = await database
      .select({ upload: modelUploads })
      .from(modelUploads)
      .innerJoin(workspaces, eq(workspaces.id, modelUploads.workspaceId))
      .where(
        and(
          lt(modelUploads.createdAt, before),
          or(isNull(modelUploads.versionId), isNotNull(workspaces.archivedAt)),
        ),
      )
      .limit(1);
    return row ? UploadSchema.parse(row.upload) : null;
  },
  async delete(id: string) {
    await database
      .delete(modelUploads)
      .where(eq(modelUploads.id, UuidSchema.parse(id)));
  },
  async create(
    workspaceId: string,
    input: z.input<typeof CreateModelUploadSchema>,
  ) {
    const value = UploadSchema.parse({
      id: uuidv7(),
      workspaceId,
      input,
      createdAt: new Date(),
      versionId: null,
    });
    const [row] = await database.insert(modelUploads).values(value).returning();
    return UploadSchema.parse(row);
  },
  async get(workspaceId: string, id: string) {
    const [row] = await database
      .select()
      .from(modelUploads)
      .where(
        and(
          eq(modelUploads.workspaceId, UuidSchema.parse(workspaceId)),
          eq(modelUploads.id, UuidSchema.parse(id)),
        ),
      );
    return row ? UploadSchema.parse(row) : null;
  },
  async publish(workspaceId: string, id: string, adapter: TaskVersionAdapter) {
    return database.transaction(async (tx) => {
      const [raw] = await tx
        .select()
        .from(modelUploads)
        .where(
          and(
            eq(modelUploads.workspaceId, UuidSchema.parse(workspaceId)),
            eq(modelUploads.id, UuidSchema.parse(id)),
          ),
        )
        .for("update");
      const upload = UploadSchema.parse(raw);
      const input = upload.input;
      if (upload.versionId) {
        const [version] = await tx
          .select()
          .from(taskVersions)
          .where(eq(taskVersions.id, upload.versionId));
        return VersionRecordSchema.parse(version);
      }
      if (Date.now() - upload.createdAt.getTime() > 3600_000)
        throw new ControlServiceError(
          "conflict",
          "This upload has expired. Start a new upload.",
        );

      if (input.create_task) {
        const [workspace] = await tx
          .select({ judge: workspaces.defaultJudgeModel })
          .from(workspaces)
          .where(eq(workspaces.id, workspaceId));
        if (!workspace)
          throw new ControlServiceError(
            "not_found",
            "The workspace was not found.",
          );

        const judgeModelId = EvaluationJudgeSchema.parse(workspace.judge);
        const [created] = await tx
          .insert(tasks)
          .values(
            TaskRecordSchema.omit({ createdAt: true, updatedAt: true }).parse({
              id: uuidv7(),
              workspaceId,
              name: input.task,
              baseModelId: input.base_model_id,
              comparisonModelId: null,
              judgeModelId,
              productionVersionId: null,
              trainingSchedule: null,
            }),
          )
          .onConflictDoNothing()
          .returning();
        if (!created)
          throw new ControlServiceError(
            "conflict",
            "A task with this name already exists.",
          );
      }
      const [rawTask] = await tx
        .select()
        .from(tasks)
        .where(
          and(eq(tasks.workspaceId, workspaceId), eq(tasks.name, input.task)),
        )
        .for("update");
      if (!rawTask)
        throw new ControlServiceError("not_found", "The task was not found.");

      const task = TaskRecordSchema.parse(rawTask);
      if (task.baseModelId !== input.base_model_id)
        throw new ControlServiceError(
          "conflict",
          "The adapter base model must match the task base model.",
        );

      const [version] = await tx
        .insert(taskVersions)
        .values(
          VersionInsertSchema.parse({
            id: upload.id,
            workspaceId,
            taskId: task.id,
            trainingRunId: null,
            name: input.name,
            baseModelId: input.base_model_id,
            adapter,
            status: "unavailable",
          }),
        )
        .onConflictDoNothing()
        .returning();
      if (!version)
        throw new ControlServiceError(
          "conflict",
          "A model version with this name already exists. Choose another name.",
        );

      await tx
        .update(modelUploads)
        .set(
          UploadSchema.pick({ versionId: true }).parse({
            versionId: upload.id,
          }),
        )
        .where(eq(modelUploads.id, upload.id));
      return VersionRecordSchema.parse(version);
    });
  },
});
