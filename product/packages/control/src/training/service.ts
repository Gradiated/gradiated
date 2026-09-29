import { v7 as uuidv7 } from "uuid";
import { traceTaskKey } from "../traces/content.js";
import { discoverTraceTasks } from "../traces/tasks.js";
import type { UpdateTask, TrainingRunListQuery } from "@gradiated/contracts";
import { and, asc, desc, eq, gt } from "drizzle-orm";

import {
  requireWorkspaceEditor,
  requireWorkspaceMembership,
} from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import {
  models,
  tasks,
  taskVersions,
  trainingRunEvents,
  trainingRuns,
} from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";
import type { ContentStore } from "../traces/storage.js";

import type { AdapterDownloads } from "./downloads.js";

export type TrainingService = ReturnType<typeof createTrainingService>;
export type TaskRecord = typeof tasks.$inferSelect;
export type TaskVersionRecord = typeof taskVersions.$inferSelect;
export type TrainingRunRecord = typeof trainingRuns.$inferSelect & {
  task: string;
  versionId: string | null;
};

const notFound = (thing: string) =>
  new ControlServiceError("not_found", `The ${thing} was not found.`);

export const createTrainingService = (
  database: ControlDatabase,
  store: ContentStore,
  downloads?: AdapterDownloads,
) => {
  const member = async (userId: string, workspaceId: string) => {
    const result = await requireWorkspaceMembership(database, {
      userId,
      workspaceId,
    });
    if (result.workspace.archivedAt) throw notFound("workspace");
    return result;
  };

  const findTask = async (workspaceId: string, name: string) => {
    const [task] = await database
      .select()
      .from(tasks)
      .where(and(eq(tasks.workspaceId, workspaceId), eq(tasks.name, name)));
    if (!task) throw notFound("task");

    return task;
  };

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

  const flattenRun = ({
    run,
    task,
    versionId,
  }: {
    run: typeof trainingRuns.$inferSelect;
    task: string;
    versionId: string | null;
  }): TrainingRunRecord => ({ ...run, task, versionId });

  const findRun = async (workspaceId: string, runId: string) => {
    const [row] = await selectRuns().where(
      and(eq(trainingRuns.id, runId), eq(tasks.workspaceId, workspaceId)),
    );
    if (!row) throw notFound("training run");

    return flattenRun(row);
  };

  return {
    async listTasks(userId: string, workspaceId: string) {
      await member(userId, workspaceId);
      const known = await database
        .select({ name: tasks.name })
        .from(tasks)
        .where(eq(tasks.workspaceId, workspaceId));
      const discovered = await discoverTraceTasks(
        store,
        workspaceId,
        new Set(known.map(({ name }) => traceTaskKey(name))),
      );
      for (let offset = 0; offset < discovered.length; offset += 1000)
        await database
          .insert(tasks)
          .values(
            discovered
              .slice(offset, offset + 1000)
              .map((name) => ({ id: uuidv7(), workspaceId, name })),
          )
          .onConflictDoNothing();

      const rows = await database
        .select()
        .from(tasks)
        .where(eq(tasks.workspaceId, workspaceId))
        .orderBy(asc(tasks.name));
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
        .where(eq(tasks.workspaceId, workspaceId))
        .orderBy(
          asc(trainingRuns.taskId),
          desc(trainingRuns.createdAt),
          desc(trainingRuns.id),
        );
      const byTask = new Map(
        latest.map((row) => [
          row.run.taskId,
          { ...flattenRun(row), versionName: row.versionName },
        ]),
      );

      return rows.map((task) => ({
        ...task,
        latestRun: byTask.get(task.id) ?? null,
      }));
    },

    async getTask(userId: string, workspaceId: string, name: string) {
      await member(userId, workspaceId);

      return findTask(workspaceId, name);
    },

    async updateTask(
      userId: string,
      workspaceId: string,
      name: string,
      input: UpdateTask,
    ) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const task = await findTask(workspaceId, name);
      if (input.base_model_id !== undefined) {
        const [model] = await database
          .select({ id: models.id, status: models.status })
          .from(models)
          .where(eq(models.id, input.base_model_id));
        if (!model) throw notFound("base model");
        if (model.status !== "available")
          throw new ControlServiceError(
            "unavailable",
            "The base model is unavailable.",
          );
      }

      const [updated] = await database
        .update(tasks)
        .set({
          baseModelId: input.base_model_id,
          comparisonModelId: input.comparison_model_id,
          updatedAt: new Date(),
        })
        .where(eq(tasks.id, task.id))
        .returning();

      return updated!;
    },

    async listRuns(
      userId: string,
      workspaceId: string,
      filters: TrainingRunListQuery = {},
    ) {
      await member(userId, workspaceId);
      const rows = await selectRuns()
        .where(
          and(
            eq(tasks.workspaceId, workspaceId),
            filters.task_id === undefined
              ? undefined
              : eq(trainingRuns.taskId, filters.task_id),
          ),
        )
        .orderBy(desc(trainingRuns.createdAt));

      return rows.map(flattenRun);
    },

    async getRun(userId: string, workspaceId: string, runId: string) {
      await member(userId, workspaceId);

      return findRun(workspaceId, runId);
    },

    async listRunEvents(
      userId: string,
      workspaceId: string,
      runId: string,
      page: { after?: number | undefined; limit: number },
    ) {
      await member(userId, workspaceId);
      await findRun(workspaceId, runId);

      return database
        .select()
        .from(trainingRunEvents)
        .where(
          and(
            eq(trainingRunEvents.runId, runId),
            page.after === undefined
              ? undefined
              : gt(trainingRunEvents.id, page.after),
          ),
        )
        .orderBy(asc(trainingRunEvents.id))
        .limit(page.limit);
    },

    async listVersions(userId: string, workspaceId: string, name: string) {
      await member(userId, workspaceId);
      const task = await findTask(workspaceId, name);
      const versions = await database
        .select()
        .from(taskVersions)
        .where(eq(taskVersions.taskId, task.id))
        .orderBy(desc(taskVersions.createdAt));

      return { task, versions };
    },

    async downloadAdapter(
      userId: string,
      workspaceId: string,
      name: string,
      versionId: string,
    ) {
      await member(userId, workspaceId);
      const task = await findTask(workspaceId, name);
      const [version] = await database
        .select()
        .from(taskVersions)
        .where(
          and(eq(taskVersions.id, versionId), eq(taskVersions.taskId, task.id)),
        );
      if (!version) throw notFound("version");
      if (!downloads)
        throw new ControlServiceError(
          "unavailable",
          "Adapter storage is not configured.",
        );

      return downloads.sign(
        version.adapter.artifact_uri,
        version.trainingRunId,
        version.adapter.size_bytes,
        version.adapter.sha256,
      );
    },

    async promote(
      userId: string,
      workspaceId: string,
      name: string,
      versionId: string,
    ) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const task = await findTask(workspaceId, name);
      const [version] = await database
        .select({ id: taskVersions.id, status: taskVersions.status })
        .from(taskVersions)
        .where(
          and(eq(taskVersions.id, versionId), eq(taskVersions.taskId, task.id)),
        );
      if (!version) throw notFound("version");
      if (version.status !== "available")
        throw new ControlServiceError(
          "unavailable",
          "Serving is not enabled for this version.",
        );

      const [updated] = await database
        .update(tasks)
        .set({ productionVersionId: version.id, updatedAt: new Date() })
        .where(eq(tasks.id, task.id))
        .returning();

      return updated!;
    },
  };
};
