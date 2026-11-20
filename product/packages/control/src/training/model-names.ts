import { and, eq, ne, or, sql } from "drizzle-orm";

import { ModelNameSegmentSchema, UuidSchema } from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { violatesConstraint } from "../errors.js";
import {
  models,
  organizations,
  tasks,
  workspaces,
} from "../db/schema/index.js";

type Transaction = Parameters<Parameters<ControlDatabase["transaction"]>[0]>[0];

export const TAKEN_MODEL_NAME =
  "Another workspace in this organization has a model with this name.";
export const OWNED_MODEL_NAME =
  "This organization already has a hosted model with this name.";

/** Why a task's name can't become `<organization slug>/<task>`, if it can't. */
export const modelNameProblem = async (
  database: ControlDatabase | Transaction,
  workspaceId: string,
  name: string,
) => {
  if (!ModelNameSegmentSchema.safeParse(name).success)
    return "Model names can't contain '/' or be longer than 128 characters.";

  const workspace = UuidSchema.parse(workspaceId);
  const [taken] = await database
    .select({ id: tasks.id })
    .from(tasks)
    .innerJoin(workspaces, eq(workspaces.id, workspace))
    .where(
      and(
        eq(tasks.organizationId, workspaces.organizationId),
        eq(tasks.name, name),
        ne(tasks.workspaceId, workspaces.id),
      ),
    )
    .limit(1);
  if (taken) return TAKEN_MODEL_NAME;

  // The gateway looks hosted model IDs and aliases up in lowercase, so the
  // organization's own `<slug>/<name>` model would make the private name
  // ambiguous. The claim trigger leaves such a name unclaimed as well.
  const publicName = sql`${organizations.slug} || '/' || lower(${name})`;
  const [owned] = await database
    .select({ id: models.id })
    .from(models)
    .innerJoin(organizations, eq(organizations.id, models.organizationId))
    .innerJoin(workspaces, eq(workspaces.organizationId, organizations.id))
    .where(
      and(
        eq(workspaces.id, workspace),
        // A retired hosted model yields its name to a private one.
        ne(models.status, "retired"),
        or(
          eq(models.id, publicName),
          sql`${publicName} = any(${models.aliases})`,
        ),
      ),
    )
    .limit(1);

  return owned && OWNED_MODEL_NAME;
};

// The database claims a task's name when its first version is written.
export const isTakenModelName = (error: unknown) =>
  violatesConstraint(error, "tasks_organization_name_unique");
