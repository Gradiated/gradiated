import { and, eq, isNull } from "drizzle-orm";
import { ArtifactReferenceSchema, UuidSchema } from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { organizations, workspaces } from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";
import type { ArtifactPublisher } from "./publish.js";

/** Eval-only versions for grad's eval workers, which call the gateway's eval lane. */
export const createEvalVersions = (
  database: ControlDatabase,
  publisher: Pick<ArtifactPublisher, "publishAsService">,
) => ({
  async publish(workspaceId: string, artifact: string) {
    const [row] = await database
      .select({ slug: organizations.slug })
      .from(workspaces)
      .innerJoin(organizations, eq(organizations.id, workspaces.organizationId))
      .where(
        and(
          eq(workspaces.id, UuidSchema.parse(workspaceId)),
          isNull(workspaces.archivedAt),
          eq(organizations.status, "active"),
          eq(organizations.kind, "customer"),
        ),
      );
    if (!row)
      throw new ControlServiceError(
        "not_found",
        "The workspace was not found or is suspended.",
      );

    const published = await publisher.publishAsService(workspaceId, {
      artifact: ArtifactReferenceSchema.parse(artifact),
      evalOnly: true,
    });

    return {
      ...published,
      model: `${row.slug}/${published.task.name}/${published.version.name}`,
    };
  },
});

export type EvalVersions = ReturnType<typeof createEvalVersions>;
