import { and, asc, eq, ne, lt, or, isNotNull } from "drizzle-orm";
import { z } from "zod";
import { v7 as uuidv7 } from "uuid";
import {
  UuidSchema,
  VersionFileNameSchema,
  type CreateTaskVersionFile,
} from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import {
  TASK_VERSION_FILE_STATUSES,
  taskVersionFiles,
  workspaces,
} from "../db/schema/index.js";

const VersionFileSchema = z.object({
  id: UuidSchema,
  workspaceId: UuidSchema,
  versionId: UuidSchema,
  name: VersionFileNameSchema,
  contentType: z.string().min(1).max(200),
  sizeBytes: z.number().int().nonnegative(),
  status: z.enum(TASK_VERSION_FILE_STATUSES),
  createdAt: z.date(),
  completedAt: z.date().nullable(),
});
export type VersionFileRecord = z.infer<typeof VersionFileSchema>;

export const versionFileKey = (
  file: Pick<VersionFileRecord, "versionId" | "id">,
) => `version-files/${file.versionId}/${file.id}`;

export const createVersionFileStore = (database: ControlDatabase) => ({
  async create(
    workspaceId: string,
    versionId: string,
    input: CreateTaskVersionFile,
  ) {
    const value = VersionFileSchema.parse({
      id: uuidv7(),
      workspaceId,
      versionId,
      name: input.name,
      contentType: input.content_type,
      sizeBytes: input.size_bytes,
      status: "pending",
      createdAt: new Date(),
      completedAt: null,
    });
    const [row] = await database
      .insert(taskVersionFiles)
      .values(value)
      .returning();

    return VersionFileSchema.parse(row);
  },
  async get(versionId: string, id: string) {
    const [row] = await database
      .select()
      .from(taskVersionFiles)
      .where(
        and(
          eq(taskVersionFiles.versionId, UuidSchema.parse(versionId)),
          eq(taskVersionFiles.id, UuidSchema.parse(id)),
        ),
      );

    return row ? VersionFileSchema.parse(row) : null;
  },
  async listReady(versionId: string) {
    const rows = await database
      .select()
      .from(taskVersionFiles)
      .where(
        and(
          eq(taskVersionFiles.versionId, UuidSchema.parse(versionId)),
          eq(taskVersionFiles.status, "ready"),
        ),
      )
      .orderBy(asc(taskVersionFiles.name));

    return rows.map((row) => VersionFileSchema.parse(row));
  },
  async complete(file: VersionFileRecord) {
    return database.transaction(async (tx) => {
      const replaced = await tx
        .update(taskVersionFiles)
        .set(
          VersionFileSchema.pick({ status: true }).parse({ status: "deleted" }),
        )
        .where(
          and(
            eq(taskVersionFiles.versionId, file.versionId),
            eq(taskVersionFiles.name, file.name),
            eq(taskVersionFiles.status, "ready"),
            ne(taskVersionFiles.id, file.id),
          ),
        )
        .returning();
      const [row] = await tx
        .update(taskVersionFiles)
        .set(
          VersionFileSchema.pick({ status: true, completedAt: true }).parse({
            status: "ready",
            completedAt: new Date(),
          }),
        )
        .where(eq(taskVersionFiles.id, file.id))
        .returning();

      return {
        file: VersionFileSchema.parse(row),
        replaced: replaced.map((value) => VersionFileSchema.parse(value)),
      };
    });
  },
  async markDeleted(id: string) {
    await database
      .update(taskVersionFiles)
      .set(
        VersionFileSchema.pick({ status: true }).parse({ status: "deleted" }),
      )
      .where(eq(taskVersionFiles.id, UuidSchema.parse(id)));
  },
  async cleanupCandidate(before: Date) {
    const [row] = await database
      .select({ file: taskVersionFiles })
      .from(taskVersionFiles)
      .innerJoin(workspaces, eq(workspaces.id, taskVersionFiles.workspaceId))
      .where(
        and(
          lt(taskVersionFiles.createdAt, before),
          or(
            isNotNull(workspaces.archivedAt),
            eq(taskVersionFiles.status, "deleted"),
            eq(taskVersionFiles.status, "pending"),
          ),
        ),
      )
      .orderBy(asc(taskVersionFiles.createdAt))
      .limit(1);

    return row ? VersionFileSchema.parse(row.file) : null;
  },
  async delete(id: string) {
    await database
      .delete(taskVersionFiles)
      .where(eq(taskVersionFiles.id, UuidSchema.parse(id)));
  },
});
