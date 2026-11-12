import { randomInt } from "node:crypto";
import { and, eq, sql } from "drizzle-orm";
import { z } from "zod";

import { OrganizationSlugSchema } from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { models, organizationSlugs } from "../db/schema/index.js";
import { ControlServiceError, violatesConstraint } from "../errors.js";

type Transaction = Parameters<Parameters<ControlDatabase["transaction"]>[0]>[0];
type Database = ControlDatabase | Transaction;

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

const SlugRowSchema = z.object({
  slug: OrganizationSlugSchema,
  organizationId: z.uuid(),
  isCurrent: z.boolean(),
});

const SLUG_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789";

/** A placeholder slug for a new organization; owners choose theirs in onboarding. */
export const randomOrganizationSlug = () =>
  Array.from({ length: 16 }, () => SLUG_ALPHABET[randomInt(36)]).join("");

// Hosted-catalog authors are reserved so `acme/...` never shadows a catalog id.
const isReserved = async (database: Database, slug: string) => {
  if (RESERVED_ORGANIZATION_SLUGS.has(slug)) return true;

  const [row] = await database
    .select({ id: models.id })
    .from(models)
    .where(sql`lower(split_part(${models.id}, '/', 1)) = ${slug}`)
    .limit(1);

  return row !== undefined;
};

// The outgoing slug stays with the organization, so names under it keep resolving.
export const setCurrentOrganizationSlug = async (
  transaction: Transaction,
  organizationId: string,
  slug: string,
) => {
  const [existing] = await transaction
    .select()
    .from(organizationSlugs)
    .where(eq(organizationSlugs.slug, slug))
    .for("update");
  const held = existing && SlugRowSchema.parse(existing);
  if (held && held.organizationId !== organizationId)
    throw new ControlServiceError(
      "conflict",
      "Another organization already uses this slug.",
    );
  if (held?.isCurrent) return;
  if (!held && (await isReserved(transaction, slug)))
    throw new ControlServiceError(
      "conflict",
      "This organization slug is reserved. Choose another.",
    );

  await transaction
    .update(organizationSlugs)
    .set({ isCurrent: false })
    .where(
      and(
        eq(organizationSlugs.organizationId, organizationId),
        eq(organizationSlugs.isCurrent, true),
      ),
    );

  if (held)
    await transaction
      .update(organizationSlugs)
      .set({ isCurrent: true })
      .where(eq(organizationSlugs.slug, slug));
  else
    await transaction
      .insert(organizationSlugs)
      .values(SlugRowSchema.parse({ slug, organizationId, isCurrent: true }));
};

export const isTakenOrganizationSlug = (error: unknown) =>
  violatesConstraint(error, "organization_slugs_pkey");
