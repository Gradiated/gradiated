import { and, eq, like, or, sql } from "drizzle-orm";
import { z } from "zod";

import { OrganizationSlugSchema } from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { models, organizationSlugs } from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";

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

export const slugFromName = (name: string) =>
  name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 30)
    .replace(/-+$/, "");

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

export const availableOrganizationSlug = async (
  database: Database,
  name: string,
) => {
  let base = slugFromName(name);
  if (base.length < 2 || (await isReserved(database, base)))
    base = `${base}-org`.replace(/^-+/, "");

  const held = new Set(
    (
      await database
        .select({ slug: organizationSlugs.slug })
        .from(organizationSlugs)
        .where(
          or(
            eq(organizationSlugs.slug, base),
            like(organizationSlugs.slug, `${base}-%`),
          ),
        )
    ).map(({ slug }) => slug),
  );
  let slug = base;
  for (let ordinal = 2; held.has(slug); ordinal++) slug = `${base}-${ordinal}`;

  return slug;
};

// The outgoing slug stays with the organization unless `releasePrevious`.
export const setCurrentOrganizationSlug = async (
  transaction: Transaction,
  organizationId: string,
  slug: string,
  options: { releasePrevious?: boolean } = {},
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

  const current = and(
    eq(organizationSlugs.organizationId, organizationId),
    eq(organizationSlugs.isCurrent, true),
  );
  if (options.releasePrevious)
    await transaction.delete(organizationSlugs).where(current);
  else
    await transaction
      .update(organizationSlugs)
      .set({ isCurrent: false })
      .where(current);

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

export const isTakenOrganizationSlug = (error: unknown): boolean => {
  if (!error || typeof error !== "object") return false;
  if (
    "code" in error &&
    error.code === "23505" &&
    "constraint" in error &&
    error.constraint === "organization_slugs_pkey"
  )
    return true;

  return (
    "cause" in error &&
    error.cause !== error &&
    isTakenOrganizationSlug(error.cause)
  );
};
