import { eq, sql } from "drizzle-orm";

import type { ControlDatabase } from "../db/client.js";
import { models, tasks } from "../db/schema/index.js";
import { ControlServiceError, violatesConstraint } from "../errors.js";

type Transaction = Parameters<Parameters<ControlDatabase["transaction"]>[0]>[0];

// Migration 0030 copies this list for its backfill.
export const RESERVED_ORGANIZATION_SLUGS: ReadonlySet<string> = new Set([
  "admin",
  "anthropic",
  "api",
  "billing",
  "console",
  "docs",
  "gradiated",
  "help",
  "internal",
  "models",
  "openai",
  "settings",
  "staff",
  "support",
  "system",
  "v1",
  "www",
]);

/**
 * Serializes choosing an organization slug with applying the model catalog,
 * the two writers of model namespaces, for the rest of the transaction.
 */
export const lockModelNamespaces = async (
  transaction: Pick<Transaction, "execute">,
) => {
  await transaction.execute(
    sql`select pg_advisory_xact_lock(hashtext('gradiated-model-namespaces-v1'))`,
  );
};

/**
 * Refuses a new slug that is reserved, or any change once the organization has
 * a model, private or its own hosted one, since its model names would stop
 * resolving. Hosted-catalog authors are reserved so `acme/...` never shadows a
 * catalog id.
 */
export const requireChangeableSlug = async (
  transaction: Transaction,
  organizationId: string,
  slug: string,
) => {
  // Held until the slug is written and committed, so a catalog pass that adds
  // a public author can't see the namespace free at the same time.
  await lockModelNamespaces(transaction);
  const [privateModel] = await transaction
    .select({ id: tasks.id })
    .from(tasks)
    .where(eq(tasks.organizationId, organizationId))
    .limit(1);
  const [ownedModel] = await transaction
    .select({ id: models.id })
    .from(models)
    .where(eq(models.organizationId, organizationId))
    .limit(1);
  if (privateModel || ownedModel)
    throw new ControlServiceError(
      "conflict",
      "The slug can't change once the organization has a model.",
    );

  const [author] = await transaction
    .select({ id: models.id })
    .from(models)
    // Aliases too: a name's namespace never changes owner, as gateways cache
    // model records under every name they answer to.
    .where(
      sql`lower(split_part(${models.id}, '/', 1)) = ${slug} or exists (select 1 from unnest(${models.aliases}) alias where lower(split_part(alias, '/', 1)) = ${slug})`,
    )
    .limit(1);
  if (RESERVED_ORGANIZATION_SLUGS.has(slug) || author)
    throw new ControlServiceError(
      "conflict",
      "This organization slug is reserved. Choose another.",
    );
};

export const isTakenOrganizationSlug = (error: unknown) =>
  violatesConstraint(error, "organizations_slug_unique");
