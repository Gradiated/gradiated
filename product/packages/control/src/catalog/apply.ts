import { and, eq, inArray, sql } from "drizzle-orm";
import type { ControlDatabase } from "../db/client.js";
import {
  modelDeployments,
  models,
  organizations,
  tasks,
} from "../db/schema/index.js";
import { lockModelNamespaces } from "../organizations/slugs.js";
import {
  catalogModels,
  legacyModels,
  trainingOnlyModels,
} from "./models/index.js";
import { ModelRecordSchema } from "./records.js";
import {
  createCatalogService,
  type CatalogModelInput,
  type CatalogModelUpsert,
} from "./service.js";

export type SkippedCatalogModel = {
  id: string;
  /**
   * `owner_missing`: this environment has no organization with the owner's
   * slug. `private_model_conflict`: the owner has a private model with this name.
   * `type_changed`: the row exists with the other type; a model ID's type is
   * fixed too, as cached records carry its deployments.
   * `owner_changed`: the row exists with another owner, or public; a model
   * ID's owner is fixed when it is first written, so gateways never hold a
   * cached record under an outdated owner.
   * `namespace_conflict`: a name is another owner's (or the public
   * catalog's), or a new public name is under an organization's slug, the
   * namespace of its own models. Unlike the others, the row is not retired.
   */
  reason:
    | "owner_missing"
    | "private_model_conflict"
    | "owner_changed"
    | "type_changed"
    | "namespace_conflict";
};

/**
 * An organization's model is named like its private models, `<slug>/<name>`
 * for its ID and aliases: anything else could shadow a public ID, and a
 * further segment could be a private version name.
 */
export const requireOwnedModelNames = (definition: CatalogModelInput) => {
  const slug = definition.owner?.organizationSlug;
  if (slug === undefined) return;

  for (const name of [definition.id, ...(definition.aliases ?? [])]) {
    const rest = name.startsWith(`${slug}/`) ? name.slice(slug.length + 1) : "";
    // The gateway looks names up in lowercase, so another case never resolves.
    if (rest === "" || rest.includes("/") || name !== name.toLowerCase())
      throw new Error(
        `Organization model ${definition.id} must be named ${slug}/<model>: ${name}`,
      );
  }
};

/** Every model declares the interface its deployments serve. */
const requireModelType = (definition: CatalogModelInput) => {
  if (definition.type !== "chat" && definition.type !== "decision")
    throw new Error(
      `Model ${definition.id} must declare its type, chat or decision.`,
    );
};

// Git owns the catalog: every pass rewrites each defined model, so an edit made
// directly in the database is put back. Rows it doesn't define are kept.
export const applyCatalog = async (
  database: ControlDatabase,
  definitions: readonly CatalogModelInput[] = [
    ...catalogModels,
    ...legacyModels,
    ...trainingOnlyModels(),
  ],
): Promise<{
  applied: number;
  unmanaged: string[];
  skipped: SkippedCatalogModel[];
}> =>
  database.transaction(async (tx) => {
    // First, as slug changes take it before the organization row.
    await lockModelNamespaces(tx);
    await tx.execute(sql`lock table models in share row exclusive mode`);
    definitions.forEach(requireOwnedModelNames);
    definitions.forEach(requireModelType);

    // Every name lives in one owner's namespace for good: an owned model's
    // names are under its owner's fixed slug, and a public name may not be
    // under any organization's slug. Gateways cache records under every name
    // they answer to, IDs and aliases alike, so a name that moved between
    // owners would be enforced from a stale record until it expired.
    const author = (name: string) => name.split("/", 1)[0]!;
    const slugs = [
      ...new Set(
        definitions.flatMap((definition) =>
          definition.owner
            ? [definition.owner.organizationSlug]
            : [definition.id, ...(definition.aliases ?? [])].map(author),
        ),
      ),
    ];
    // The namespace lock serializes this with slug choices; locking the owner
    // rows serializes it with private name claims, which lock them too.
    const owners = new Map(
      (slugs.length
        ? await tx
            .select({ id: organizations.id, slug: organizations.slug })
            .from(organizations)
            .where(inArray(organizations.slug, slugs))
            .for("share")
        : []
      ).map((organization) => [organization.slug, organization.id]),
    );
    // The owners' claimed private model names, as the gateway looks them up.
    // Claims lock the organization row, so none can land before this commits.
    const privateNames = new Set(
      owners.size
        ? (
            await tx
              .select({
                // Qualified by hand: both tables have a name column.
                name: sql<string>`organizations.slug || '/' || lower(tasks.name)`,
              })
              .from(tasks)
              .innerJoin(
                organizations,
                eq(organizations.id, tasks.organizationId),
              )
              .where(inArray(tasks.organizationId, [...owners.values()]))
          ).map((task) => task.name)
        : [],
    );

    const catalog = createCatalogService(tx);
    const existing = await catalog.listModels({
      includeRetired: true,
      includeOrganizationModels: true,
    });
    // Who answers to each name now, by ID or alias.
    const holders = new Map<string, string | null>();
    for (const model of existing)
      for (const name of [model.id, ...model.aliases])
        holders.set(name, model.organizationId);

    const skipped: SkippedCatalogModel[] = [];
    const writes: CatalogModelUpsert[] = [];
    for (const { owner, ...definition } of definitions) {
      const names = [definition.id, ...(definition.aliases ?? [])];

      // Never written public: a model whose owner is missing waits for it.
      const organizationId = owner ? owners.get(owner.organizationSlug) : null;
      if (organizationId === undefined) {
        skipped.push({ id: definition.id, reason: "owner_missing" });
        continue;
      }

      // Gateways cache a model record under every name it answers to, so an
      // owner that changed in place would be enforced from a stale record
      // until it expired. Moving a model to another owner, or to or from the
      // public catalog, takes a new ID; the old one is retired.
      if (
        holders.has(definition.id) &&
        holders.get(definition.id) !== organizationId
      ) {
        skipped.push({ id: definition.id, reason: "owner_changed" });
        continue;
      }

      // The same for its interface: a cached record keeps deployments of the
      // old protocol, so a model ID's type is fixed too.
      const current = existing.find((model) => model.id === definition.id);
      if (current && current.type !== definition.type) {
        skipped.push({ id: definition.id, reason: "type_changed" });
        continue;
      }

      // The same holds for aliases, and a public name may not enter an
      // organization's namespace; one a public row already answers to stays,
      // as it was never anyone else's. The row keeps its previous names.
      if (
        names.some(
          (name) =>
            (holders.has(name) && holders.get(name) !== organizationId) ||
            (organizationId === null &&
              owners.has(author(name)) &&
              holders.get(name) !== null),
        )
      ) {
        skipped.push({ id: definition.id, reason: "namespace_conflict" });
        continue;
      }

      // Both would answer the same name, so the gateway would refuse both.
      if (names.some((name) => privateNames.has(name))) {
        skipped.push({ id: definition.id, reason: "private_model_conflict" });
        continue;
      }

      writes.push({ ...definition, organizationId });
    }

    // A row already written for a definition that is now withheld, such as a
    // public model that gained an owner this environment lacks, is retired so
    // it can't stay callable or listed under its old access.
    // A public row refused a new name keeps its previous names and stays live.
    const withheld = new Set(
      skipped
        .filter((skip) => skip.reason !== "namespace_conflict")
        .map((skip) => skip.id),
    );
    const written = new Set(writes.map((definition) => definition.id));
    const kept = existing
      .filter((model) => !written.has(model.id))
      .map((model) =>
        withheld.has(model.id)
          ? { ...model, status: "retired" as const }
          : model,
      );
    const retiring = existing
      .filter((model) => withheld.has(model.id) && model.status !== "retired")
      .map((model) => model.id);
    const names = new Set(
      [...writes, ...kept]
        .filter((model) => model.status !== "retired")
        .map((model) => model.id),
    );
    for (const definition of [...writes, ...kept]) {
      for (const alias of ModelRecordSchema.shape.aliases.parse(
        definition.aliases,
      )) {
        if (alias === definition.id || names.has(alias)) {
          throw new Error(`Conflicting model alias: ${alias}`);
        }

        names.add(alias);
      }
    }

    for (const definition of writes) {
      await catalog.upsertModel(definition);
    }
    // Move existing deployments off retired IDs that became aliases of a new
    // canonical model in the same transaction so traffic and probes never drop.
    for (const definition of writes) {
      if (definition.status === "retired") continue;
      const aliases = ModelRecordSchema.shape.aliases.parse(definition.aliases);
      if (aliases.length === 0) continue;
      await tx
        .update(modelDeployments)
        .set({ modelId: definition.id, updatedAt: new Date() })
        .where(
          and(
            inArray(modelDeployments.modelId, aliases),
            sql`(coalesce(${modelDeployments.release}->>'protocol', '') = 'system_one') = ${definition.type === "decision"}`,
          ),
        );
    }
    if (retiring.length)
      await tx
        .update(models)
        .set({ status: "retired", updatedAt: new Date() })
        .where(inArray(models.id, retiring));

    const defined = new Set(definitions.map((definition) => definition.id));
    return {
      applied: writes.length,
      unmanaged: kept
        .filter((model) => !defined.has(model.id) && model.status !== "retired")
        .map((model) => model.id),
      skipped,
    };
  });
