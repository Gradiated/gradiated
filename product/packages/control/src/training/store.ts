import {
  and,
  asc,
  desc,
  eq,
  gt,
  inArray,
  isNotNull,
  isNull,
  lt,
  notExists,
  or,
  sql,
} from "drizzle-orm";
import { z } from "zod";
import {
  ModelSchema,
  TaskSchema,
  TrainingRunListQuerySchema,
  TrainingRunEventsQuerySchema,
  UpdateTaskSchema,
  UuidSchema,
  WorkspaceSchema,
} from "@gradiated/contracts";
import { ModelRecordSchema } from "../catalog/records.js";
import type { ControlDatabase } from "../db/client.js";
import {
  models,
  tasks,
  taskVersions,
  trainingRuns,
  trainingRunEvents,
  workspaces,
  organizations,
  ORGANIZATION_STATUSES,
} from "../db/schema/index.js";
import {
  TaskRecordSchema,
  RunRecordSchema,
  VersionRecordSchema,
  EventRecordSchema,
  TaskUpdateSchema,
} from "./records.js";

const RunViewSchema = RunRecordSchema.extend({
  task: TaskSchema.shape.name,
  versionId: UuidSchema.nullable(),
});
const LatestRunSchema = RunViewSchema.extend({
  versionName: z.string().nullable(),
});
const WorkspaceTrainingSchema = z.object({
  id: UuidSchema,
  archivedAt: z.date().nullable(),
  traceCaptureEnabled: WorkspaceSchema.shape.trace_capture_enabled,
});
const OrganizationTrainingSchema = z.object({
  status: z.enum(ORGANIZATION_STATUSES),
});
const AdmissionContextSchema = z.object({
  task: TaskRecordSchema,
  workspace: WorkspaceTrainingSchema,
  organization: OrganizationTrainingSchema,
});

export const createTrainingStore = (database: ControlDatabase) => {
  const archivedWorkspaceIds = () =>
    database
      .select({ id: workspaces.id })
      .from(workspaces)
      .where(isNotNull(workspaces.archivedAt));
  const selectRuns = () =>
    database
      .select({
        run: trainingRuns,
        task: tasks.name,
        versionId: taskVersions.id,
      })
      .from(trainingRuns)
      .innerJoin(tasks, eq(tasks.id, trainingRuns.taskId))
      .leftJoin(taskVersions, eq(taskVersions.trainingRunId, trainingRuns.id));
  const flatten = (row: { run: unknown; task: unknown; versionId: unknown }) =>
    RunViewSchema.parse({
      ...RunRecordSchema.parse(row.run),
      task: row.task,
      versionId: row.versionId,
    });

  return {
    async getTask(workspaceId: string, name: string) {
      const [row] = await database
        .select()
        .from(tasks)
        .where(
          and(
            eq(tasks.workspaceId, UuidSchema.parse(workspaceId)),
            eq(tasks.name, name),
          ),
        );

      return row && TaskRecordSchema.parse(row);
    },

    /** Whether any workspace of this workspace's organization has the task name. */
    async organizationUsesTaskName(workspaceId: string, name: string) {
      const [row] = await database
        .select({ id: tasks.id })
        .from(tasks)
        .innerJoin(
          workspaces,
          eq(workspaces.organizationId, tasks.organizationId),
        )
        .where(
          and(
            eq(workspaces.id, UuidSchema.parse(workspaceId)),
            eq(tasks.name, name),
          ),
        )
        .limit(1);

      return row !== undefined;
    },

    async getTaskById(workspaceId: string, taskId: string) {
      const [row] = await database
        .select()
        .from(tasks)
        .where(
          and(
            eq(tasks.workspaceId, UuidSchema.parse(workspaceId)),
            eq(tasks.id, UuidSchema.parse(taskId)),
          ),
        );

      return row && TaskRecordSchema.parse(row);
    },

    async getModel(modelId: string) {
      const [row] = await database
        .select({
          id: models.id,
          status: models.status,
          properties: models.properties,
        })
        .from(models)
        .where(eq(models.id, ModelSchema.shape.id.parse(modelId)));

      return (
        row &&
        ModelRecordSchema.pick({
          id: true,
          status: true,
          properties: true,
        }).parse(row)
      );
    },

    async updateTask(taskId: string, value: z.input<typeof UpdateTaskSchema>) {
      const input = UpdateTaskSchema.parse(value);

      const [row] = await database
        .update(tasks)
        .set(
          TaskUpdateSchema.parse({
            baseModelId: input.base_model_id,
            comparisonModelId: input.comparison_model_id,
            judgeModelId: input.judge_model_id,
            trainingSchedule: input.training_schedule,
            updatedAt: new Date(),
          }),
        )
        .where(eq(tasks.id, UuidSchema.parse(taskId)))
        .returning();
      return TaskRecordSchema.parse(row);
    },

    async setProductionVersion(taskId: string, versionId: string) {
      const [row] = await database
        .update(tasks)
        .set(
          TaskUpdateSchema.parse({
            productionVersionId: versionId,
            updatedAt: new Date(),
          }),
        )
        .where(eq(tasks.id, UuidSchema.parse(taskId)))
        .returning();
      return TaskRecordSchema.parse(row);
    },

    async listTasks(workspaceId: string) {
      const id = UuidSchema.parse(workspaceId);
      const rows = TaskRecordSchema.array().parse(
        await database
          .select()
          .from(tasks)
          .where(eq(tasks.workspaceId, id))
          .orderBy(asc(tasks.name)),
      );

      const latest = await database
        .selectDistinctOn([trainingRuns.taskId], {
          run: trainingRuns,
          task: tasks.name,
          versionId: taskVersions.id,
          versionName: taskVersions.name,
        })
        .from(trainingRuns)
        .innerJoin(tasks, eq(tasks.id, trainingRuns.taskId))
        .leftJoin(taskVersions, eq(taskVersions.trainingRunId, trainingRuns.id))
        .where(eq(tasks.workspaceId, id))
        .orderBy(
          asc(trainingRuns.taskId),
          desc(trainingRuns.createdAt),
          desc(trainingRuns.id),
        );

      const byTask = new Map(
        latest.map((row) => {
          const run = LatestRunSchema.parse({
            ...flatten(row),
            versionName: row.versionName,
          });

          return [run.taskId, run] as const;
        }),
      );

      const latestVersions = VersionRecordSchema.array().parse(
        await database
          .selectDistinctOn([taskVersions.taskId])
          .from(taskVersions)
          .where(eq(taskVersions.workspaceId, id))
          .orderBy(
            asc(taskVersions.taskId),
            desc(taskVersions.createdAt),
            desc(taskVersions.id),
          ),
      );
      const versionsByTask = new Map(
        latestVersions.map((version) => [version.taskId, version]),
      );

      return rows.map((task) => ({
        ...task,
        latestRun: byTask.get(task.id) ?? null,
        latestVersion: versionsByTask.get(task.id) ?? null,
      }));
    },

    async listRuns(
      workspaceId: string,
      value: z.input<typeof TrainingRunListQuerySchema>,
    ) {
      const filters = TrainingRunListQuerySchema.parse(value);

      const rows = await selectRuns()
        .where(
          and(
            eq(tasks.workspaceId, UuidSchema.parse(workspaceId)),
            filters.task_id === undefined
              ? undefined
              : eq(trainingRuns.taskId, filters.task_id),
          ),
        )
        .orderBy(desc(trainingRuns.createdAt));

      return rows.map(flatten);
    },

    async getRun(workspaceId: string, runId: string) {
      const [row] = await selectRuns().where(
        and(
          eq(tasks.workspaceId, UuidSchema.parse(workspaceId)),
          eq(trainingRuns.id, UuidSchema.parse(runId)),
        ),
      );

      return row && flatten(row);
    },

    async listRunEvents(
      runId: string,
      value: z.input<typeof TrainingRunEventsQuerySchema>,
    ) {
      const page = TrainingRunEventsQuerySchema.parse(value);
      return EventRecordSchema.array().parse(
        await database
          .select()
          .from(trainingRunEvents)
          .where(
            and(
              eq(trainingRunEvents.runId, UuidSchema.parse(runId)),
              page.after === undefined
                ? undefined
                : gt(trainingRunEvents.id, page.after),
            ),
          )
          .orderBy(asc(trainingRunEvents.id))
          .limit(page.limit),
      );
    },

    async listVersions(taskId: string) {
      return VersionRecordSchema.array().parse(
        await database
          .select()
          .from(taskVersions)
          .where(eq(taskVersions.taskId, UuidSchema.parse(taskId)))
          .orderBy(desc(taskVersions.createdAt)),
      );
    },

    async getVersion(taskId: string, versionId: string) {
      const [row] = await database
        .select()
        .from(taskVersions)
        .where(
          and(
            eq(taskVersions.taskId, UuidSchema.parse(taskId)),
            eq(taskVersions.id, UuidSchema.parse(versionId)),
          ),
        );

      return row && VersionRecordSchema.parse(row);
    },

    async getHostingVersion(workspaceId: string, runtimeName: string) {
      const separator = runtimeName.lastIndexOf("/");
      if (separator < 0) return undefined;

      const taskName = runtimeName.slice(0, separator);
      const versionName = runtimeName.slice(separator + 1);
      const [row] = await database
        .select({ task: tasks, version: taskVersions })
        .from(taskVersions)
        .innerJoin(tasks, eq(tasks.id, taskVersions.taskId))
        .innerJoin(workspaces, eq(workspaces.id, tasks.workspaceId))
        .innerJoin(
          organizations,
          eq(organizations.id, workspaces.organizationId),
        )
        .where(
          and(
            eq(
              taskVersions.name,
              VersionRecordSchema.shape.name.parse(versionName),
            ),
            eq(tasks.name, taskName),
            eq(tasks.workspaceId, UuidSchema.parse(workspaceId)),
            isNull(workspaces.archivedAt),
            eq(organizations.status, "active"),
          ),
        );

      return (
        row && {
          task: TaskRecordSchema.parse(row.task),
          version: VersionRecordSchema.parse(row.version),
        }
      );
    },

    async listProductionVersions(baseModelId: string) {
      const rows = await database
        .select({ task: tasks, version: taskVersions })
        .from(tasks)
        .innerJoin(
          taskVersions,
          and(
            eq(taskVersions.id, tasks.productionVersionId),
            eq(taskVersions.taskId, tasks.id),
          ),
        )
        .innerJoin(workspaces, eq(workspaces.id, tasks.workspaceId))
        .innerJoin(
          organizations,
          eq(organizations.id, workspaces.organizationId),
        )
        .where(
          and(
            eq(
              taskVersions.baseModelId,
              ModelSchema.shape.id.parse(baseModelId),
            ),
            eq(taskVersions.status, "available"),
            sql`coalesce(nullif(${taskVersions.adapter}->>'validated_base_model_revision', ''), ${taskVersions.adapter}->>'base_model_revision', '') <> ''`,
            sql`(${taskVersions.adapter}->>'size_bytes')::bigint > 0`,
            isNull(workspaces.archivedAt),
            eq(organizations.status, "active"),
          ),
        )
        .orderBy(desc(tasks.updatedAt), desc(tasks.id))
        .limit(4096);

      return rows.map((row) => ({
        task: TaskRecordSchema.parse(row.task),
        version: VersionRecordSchema.parse(row.version),
      }));
    },

    async clearTrainingScheduleForBases(taskId: string, baseIds: string[]) {
      const patch = TaskRecordSchema.pick({
        trainingSchedule: true,
        updatedAt: true,
      }).parse({
        trainingSchedule: null,
        updatedAt: new Date(),
      });
      await database
        .update(tasks)
        .set(patch)
        .where(
          and(
            eq(tasks.id, UuidSchema.parse(taskId)),
            inArray(tasks.baseModelId, baseIds),
          ),
        );
    },

    async tasksForTrainingBases(baseIds: string[], after?: string) {
      const rows = await database
        .select({ id: tasks.id })
        .from(tasks)
        .where(
          and(
            inArray(tasks.baseModelId, baseIds),
            isNotNull(tasks.trainingSchedule),
            after ? gt(tasks.id, UuidSchema.parse(after)) : undefined,
          ),
        )
        .orderBy(asc(tasks.id))
        .limit(100);

      return UuidSchema.array().parse(rows.map((row) => row.id));
    },

    async admissionContext(
      target: string | { workspaceId: string; name: string },
    ) {
      const [row] = await database
        .select({
          task: tasks,
          workspace: {
            id: workspaces.id,
            archivedAt: workspaces.archivedAt,
            traceCaptureEnabled: workspaces.traceCaptureEnabled,
          },
          organization: { status: organizations.status },
        })
        .from(tasks)
        .innerJoin(workspaces, eq(tasks.workspaceId, workspaces.id))
        .innerJoin(
          organizations,
          eq(workspaces.organizationId, organizations.id),
        )
        .where(
          typeof target === "string"
            ? eq(tasks.id, UuidSchema.parse(target))
            : and(
                eq(tasks.workspaceId, UuidSchema.parse(target.workspaceId)),
                eq(tasks.name, target.name),
              ),
        );

      return row && AdmissionContextSchema.parse(row);
    },

    async activeRun(taskId: string) {
      const [row] = await database
        .select()
        .from(trainingRuns)
        .where(
          and(
            eq(trainingRuns.taskId, UuidSchema.parse(taskId)),
            isNull(trainingRuns.finishedAt),
          ),
        )
        .limit(1);

      return row && RunRecordSchema.parse(row);
    },

    async lastSuccessfulCutoff(taskId: string) {
      const [row] = await database
        .select({ inputCutoff: trainingRuns.inputCutoff })
        .from(trainingRuns)
        .where(
          and(
            eq(trainingRuns.taskId, UuidSchema.parse(taskId)),
            eq(trainingRuns.stage, "succeeded"),
          ),
        )
        .orderBy(desc(trainingRuns.inputCutoff))
        .limit(1);

      return row
        ? RunRecordSchema.pick({ inputCutoff: true }).parse(row).inputCutoff
        : null;
    },

    async isTaskLive(taskId: string) {
      const [row] = await database
        .select({ id: tasks.id })
        .from(tasks)
        .innerJoin(workspaces, eq(workspaces.id, tasks.workspaceId))
        .where(
          and(
            eq(tasks.id, UuidSchema.parse(taskId)),
            isNull(workspaces.archivedAt),
          ),
        );

      return Boolean(row);
    },

    async archivedRunToDelete(finishedBefore: Date, createdBefore: Date) {
      const [row] = await database
        .select({ id: trainingRuns.id })
        .from(trainingRuns)
        .innerJoin(tasks, eq(tasks.id, trainingRuns.taskId))
        .where(
          and(
            inArray(tasks.workspaceId, archivedWorkspaceIds()),
            or(
              lt(trainingRuns.finishedAt, finishedBefore),
              and(
                isNull(trainingRuns.finishedAt),
                lt(trainingRuns.createdAt, createdBefore),
              ),
            ),
          ),
        )
        .limit(1);

      return row ? UuidSchema.parse(row.id) : null;
    },

    async deleteRun(runId: string) {
      await database
        .delete(trainingRuns)
        .where(eq(trainingRuns.id, UuidSchema.parse(runId)));
    },

    async archivedTasksWithoutRuns(limit: number) {
      const rows = await database
        .select({ id: tasks.id })
        .from(tasks)
        .where(
          and(
            inArray(tasks.workspaceId, archivedWorkspaceIds()),
            notExists(
              database
                .select({ id: trainingRuns.id })
                .from(trainingRuns)
                .where(eq(trainingRuns.taskId, tasks.id)),
            ),
          ),
        )
        .limit(limit);

      return rows.map((row) => UuidSchema.parse(row.id));
    },

    // FOR UPDATE waits for a concurrent run insert's key-share lock, so the
    // recheck sees that run instead of the delete cascading over it.
    async deleteTaskWithoutRuns(taskId: string) {
      taskId = UuidSchema.parse(taskId);

      return database.transaction(async (tx) => {
        const [task] = await tx
          .select({ id: tasks.id })
          .from(tasks)
          .where(eq(tasks.id, taskId))
          .for("update");
        if (!task) return false;

        const [run] = await tx
          .select({ id: trainingRuns.id })
          .from(trainingRuns)
          .where(eq(trainingRuns.taskId, taskId))
          .limit(1);
        if (run) return false;

        await tx.delete(tasks).where(eq(tasks.id, taskId));
        return true;
      });
    },
  };
};
