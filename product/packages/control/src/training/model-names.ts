import { and, eq, ne } from "drizzle-orm";

import { ModelNameSegmentSchema, UuidSchema } from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { violatesConstraint } from "../errors.js";
import { tasks, workspaces } from "../db/schema/index.js";

type Transaction = Parameters<Parameters<ControlDatabase["transaction"]>[0]>[0];

export const TAKEN_MODEL_NAME =
  "Another workspace in this organization has a model with this name.";

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

  return taken && TAKEN_MODEL_NAME;
};

// The database claims a task's name when its first version is written.
export const isTakenModelName = (error: unknown) =>
  violatesConstraint(error, "tasks_organization_name_unique");
