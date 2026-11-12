import { and, eq, isNull, ne, sql } from "drizzle-orm";

import { ModelNameSegmentSchema, UuidSchema } from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { tasks, workspaces } from "../db/schema/index.js";
import { ControlServiceError, violatesConstraint } from "../errors.js";

type Transaction = Parameters<Parameters<ControlDatabase["transaction"]>[0]>[0];

const workspaceOrganization = sql`(select ${workspaces.organizationId} from ${workspaces} where ${workspaces.id} = ${tasks.workspaceId})`;

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
        eq(tasks.modelOrganizationId, workspaces.organizationId),
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
 * model names are unique across the organization. Check `modelNameProblem` first.
 */
export const claimModelName = async (
  database: ControlDatabase | Transaction,
  taskId: string,
) => {
  await database
    .update(tasks)
    .set({ modelOrganizationId: workspaceOrganization })
    .where(
      and(
        eq(tasks.id, UuidSchema.parse(taskId)),
        isNull(tasks.modelOrganizationId),
      ),
    )
    .catch((error: unknown) => {
      if (violatesConstraint(error, "tasks_model_name_unique"))
        throw new ControlServiceError(
          "conflict",
          "Another workspace in this organization has a model with this name.",
          error,
        );
      throw error;
    });
};
