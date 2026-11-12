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
 * Refuses a new slug that is reserved, or any change once the organization has
 * a model, since its model names would stop resolving. Hosted-catalog authors
 * are reserved so `acme/...` never shadows a catalog id.
 */
export const requireChangeableSlug = async (
  transaction: Transaction,
  organizationId: string,
  slug: string,
) => {
  const [model] = await transaction
    .select({ id: tasks.id })
    .from(tasks)
    .where(eq(tasks.organizationId, organizationId))
    .limit(1);
  if (model)
    throw new ControlServiceError(
      "conflict",
      "The slug can't change once the organization has a model.",
    );

  const [author] = await transaction
    .select({ id: models.id })
    .from(models)
    .where(sql`lower(split_part(${models.id}, '/', 1)) = ${slug}`)
    .limit(1);
  if (RESERVED_ORGANIZATION_SLUGS.has(slug) || author)
    throw new ControlServiceError(
      "conflict",
      "This organization slug is reserved. Choose another.",
    );
};

export const isTakenOrganizationSlug = (error: unknown) =>
  violatesConstraint(error, "organizations_slug_unique");
