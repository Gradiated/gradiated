import { and, eq, ne } from "drizzle-orm";

import { ModelNameSegmentSchema, UuidSchema } from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { organizations, tasks, workspaces } from "../db/schema/index.js";

type Transaction = Parameters<Parameters<ControlDatabase["transaction"]>[0]>[0];

/** Why a task's name can't become `<organization slug>/<task>`, if it can't. */
export const modelNameProblem = async (
  database: ControlDatabase | Transaction,
  workspaceId: string,
  name: string,
) => {
  if (!ModelNameSegmentSchema.safeParse(name).success)
    return "Model names can't contain '/' or be longer than 128 characters.";

  const [taken] = await database
    .select({ id: tasks.id })
    .from(tasks)
    .innerJoin(workspaces, eq(workspaces.id, UuidSchema.parse(workspaceId)))
    .where(
      and(
        eq(tasks.organizationId, workspaces.organizationId),
        eq(tasks.name, name),
        ne(tasks.workspaceId, workspaces.id),
      ),
    )
    .limit(1);

  return (
    taken &&
    "Another workspace in this organization has a model with this name."
  );
};

/**
 * A task's name becomes a model name once it trains or takes an upload, and
 * model names are unique across the organization. Returns false when another
 * workspace's task already holds the name.
 */
export const claimModelName = async (
  transaction: Transaction,
  taskId: string,
) => {
  const [task] = await transaction
    .select({
      name: tasks.name,
      claimed: tasks.organizationId,
      organizationId: workspaces.organizationId,
    })
    .from(tasks)
    .innerJoin(workspaces, eq(workspaces.id, tasks.workspaceId))
    .where(eq(tasks.id, UuidSchema.parse(taskId)));
  if (!task) return false;
  if (task.claimed) return true;

  // Slug changes take the same lock, so the slug can't change under a first model.
  await transaction
    .select({ id: organizations.id })
    .from(organizations)
    .where(eq(organizations.id, task.organizationId))
    .for("update");
  const [taken] = await transaction
    .select({ id: tasks.id })
    .from(tasks)
    .where(
      and(
        eq(tasks.organizationId, task.organizationId),
        eq(tasks.name, task.name),
      ),
    )
    .limit(1);
  if (taken) return false;

  await transaction
    .update(tasks)
    .set({ organizationId: task.organizationId })
    .where(eq(tasks.id, taskId));

  return true;
};
