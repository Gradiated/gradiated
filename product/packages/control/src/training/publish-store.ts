import { and, asc, eq, lt, sql } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";
import { z } from "zod";
import {
  EvaluationJudgeSchema,
  GradArtifactIdSchema,
  UuidSchema,
  type TaskVersionAdapter,
} from "@gradiated/contracts";
import type { TaskPurpose, TaskVersionRecord } from "./records.js";
import type { ControlDatabase } from "../db/client.js";
import {
  tasks,
  taskVersionPinReleases,
  taskVersions,
  workspaces,
} from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";
import {
  TaskRecordSchema,
  VersionInsertSchema,
  VersionRecordSchema,
  VersionUpdateSchema,
} from "./records.js";
import { isTakenModelName, TAKEN_MODEL_NAME } from "./model-names.js";

const PinReleaseSchema = z.object({
  versionId: UuidSchema,
  workspaceId: UuidSchema,
  artifactId: GradArtifactIdSchema,
  createdAt: z.date(),
});
export type PinRelease = z.infer<typeof PinReleaseSchema>;

const artifactIdOf = sql`${taskVersions.adapter}->'source'->>'artifact_id'`;

export const createPublishStore = (database: ControlDatabase) => ({
  async findArtifactVersion(taskId: string, artifactId: string) {
    const [row] = await database
      .select()
      .from(taskVersions)
      .where(
        and(
          eq(taskVersions.taskId, UuidSchema.parse(taskId)),
          eq(artifactIdOf, GradArtifactIdSchema.parse(artifactId)),
        ),
      );

    return row && VersionRecordSchema.parse(row);
  },

  // The task is created by the first publish into it.
  async insertVersion(input: {
    id: string;
    workspaceId: string;
    task: string;
    baseModelId: string;
    name: string;
    adapter: TaskVersionAdapter;
    purpose: TaskPurpose;
    expiresAt: Date | null;
    status: TaskVersionRecord["status"];
  }) {
    return database
      .transaction(async (tx) => {
        const [workspace] = await tx
          .select({ judge: workspaces.defaultJudgeModel })
          .from(workspaces)
          .where(eq(workspaces.id, UuidSchema.parse(input.workspaceId)));
        if (!workspace)
          throw new ControlServiceError(
            "not_found",
            "The workspace was not found.",
          );

        await tx
          .insert(tasks)
          .values(
            TaskRecordSchema.omit({ createdAt: true, updatedAt: true }).parse({
              id: uuidv7(),
              organizationId: null,
              workspaceId: input.workspaceId,
              name: input.task,
              baseModelId: input.baseModelId,
              comparisonModelId: null,
              judgeModelId: EvaluationJudgeSchema.parse(workspace.judge),
              productionVersionId: null,
              trainingSchedule: null,
              purpose: input.purpose,
            }),
          )
          .onConflictDoNothing();
        const [rawTask] = await tx
          .select()
          .from(tasks)
          .where(
            and(
              eq(tasks.workspaceId, input.workspaceId),
              eq(tasks.name, input.task),
            ),
          )
          .for("update");
        const task = TaskRecordSchema.parse(rawTask);
        if (task.purpose !== input.purpose)
          return { outcome: "purpose_mismatch" as const, task };
        if (
          input.purpose === "serving" &&
          task.baseModelId !== input.baseModelId
        )
          return { outcome: "base_mismatch" as const, task };

        const artifactId = input.adapter.source?.artifact_id;
        if (artifactId) {
          const [existing] = await tx
            .select()
            .from(taskVersions)
            .where(
              and(
                eq(taskVersions.taskId, task.id),
                eq(artifactIdOf, artifactId),
              ),
            );
          if (existing)
            return {
              outcome: "existing" as const,
              task,
              version: VersionRecordSchema.parse(existing),
            };
        }

        const [version] = await tx
          .insert(taskVersions)
          .values(
            VersionInsertSchema.parse({
              id: input.id,
              workspaceId: input.workspaceId,
              taskId: task.id,
              trainingRunId: null,
              name: input.name,
              baseModelId: input.baseModelId,
              adapter: input.adapter,
              status: input.status,
              expiresAt: input.expiresAt,
            }),
          )
          .onConflictDoNothing()
          .returning();
        if (!version) return { outcome: "name_taken" as const, task };

        return {
          outcome: "created" as const,
          task,
          version: VersionRecordSchema.parse(version),
        };
      })
      .catch((error: unknown) => {
        if (isTakenModelName(error))
          throw new ControlServiceError("conflict", TAKEN_MODEL_NAME, error);
        throw error;
      });
  },

  async markAvailable(versionId: string) {
    const [row] = await database
      .update(taskVersions)
      .set(
        VersionUpdateSchema.parse({
          status: "available",
          updatedAt: new Date(),
        }),
      )
      .where(eq(taskVersions.id, UuidSchema.parse(versionId)))
      .returning();

    return row && VersionRecordSchema.parse(row);
  },

  async extendExpiry(versionId: string, expiresAt: Date) {
    const [row] = await database
      .update(taskVersions)
      .set({ expiresAt, updatedAt: new Date() })
      .where(
        and(
          eq(taskVersions.id, UuidSchema.parse(versionId)),
          lt(taskVersions.expiresAt, expiresAt),
        ),
      )
      .returning();

    return row && VersionRecordSchema.parse(row);
  },

  async expiredVersions(now: Date, limit = 50) {
    return VersionRecordSchema.array().parse(
      await database
        .select()
        .from(taskVersions)
        .where(lt(taskVersions.expiresAt, now))
        .orderBy(asc(taskVersions.expiresAt))
        .limit(limit),
    );
  },

  // Deletes a version that is not in production, recording the pin its
  // artifact holds in the same transaction so the release survives a crash.
  async deleteVersion(taskId: string, versionId: string) {
    return database.transaction(async (tx) => {
      const [deleted] = await tx
        .delete(taskVersions)
        .where(
          and(
            eq(taskVersions.id, UuidSchema.parse(versionId)),
            eq(taskVersions.taskId, UuidSchema.parse(taskId)),
            sql`not exists (select 1 from ${tasks} where ${tasks.productionVersionId} = ${taskVersions.id})`,
          ),
        )
        .returning();
      if (!deleted) return undefined;

      const version = VersionRecordSchema.parse(deleted);
      const artifactId = version.adapter.source?.artifact_id;
      if (!artifactId) return { version, release: undefined };

      const [release] = await tx
        .insert(taskVersionPinReleases)
        .values(
          PinReleaseSchema.omit({ createdAt: true }).parse({
            versionId: version.id,
            workspaceId: version.workspaceId,
            artifactId,
          }),
        )
        .onConflictDoNothing()
        .returning();

      return {
        version,
        release: release ? PinReleaseSchema.parse(release) : undefined,
      };
    });
  },

  async pendingPinReleases(before: Date, limit = 50) {
    return PinReleaseSchema.array().parse(
      await database
        .select()
        .from(taskVersionPinReleases)
        .where(lt(taskVersionPinReleases.createdAt, before))
        .orderBy(asc(taskVersionPinReleases.createdAt))
        .limit(limit),
    );
  },

  async completePinRelease(versionId: string) {
    await database
      .delete(taskVersionPinReleases)
      .where(eq(taskVersionPinReleases.versionId, UuidSchema.parse(versionId)));
  },
});
