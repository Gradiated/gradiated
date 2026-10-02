import { eq } from "drizzle-orm";
import { z } from "zod";
import {
  WorkspaceSchema,
  UpdateWorkspaceSchema,
  UuidSchema,
  EvaluationJudgeSchema,
  type UpdateWorkspace,
} from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import { workspaces } from "../db/schema/index.js";

const WorkspaceRecordSchema = z.object({
  id: UuidSchema,
  organizationId: UuidSchema,
  name: WorkspaceSchema.shape.name,
  isDefault: z.boolean(),
  archivedAt: z.date().nullable(),
  createdAt: z.date(),
  updatedAt: z.date(),
  traceCaptureEnabled: z.boolean(),
  traceRetentionDays: WorkspaceSchema.shape.trace_retention_days,
  defaultJudgeModel: EvaluationJudgeSchema,
});

export const createWorkspaceStore = (database: ControlDatabase) => ({
  async update(workspaceId: string, input: UpdateWorkspace) {
    const patch = UpdateWorkspaceSchema.parse(input);
    const [workspace] = await database
      .update(workspaces)
      .set({
        name: patch.name,
        traceCaptureEnabled: patch.trace_capture_enabled,
        traceRetentionDays: patch.trace_retention_days,
        defaultJudgeModel: patch.default_judge_model,
        updatedAt: new Date(),
      })
      .where(eq(workspaces.id, workspaceId))
      .returning()
      .catch((error: unknown) => {
        if (isDuplicateName(error))
          throw new ControlServiceError(
            "conflict",
            "A workspace with this name already exists.",
            error,
          );
        throw error;
      });

    return WorkspaceRecordSchema.parse(workspace);
  },
});

const isDuplicateName = (error: unknown): boolean => {
  if (!error || typeof error !== "object") return false;
  if (
    "code" in error &&
    error.code === "23505" &&
    "constraint" in error &&
    error.constraint === "workspaces_organization_name_lower_unique"
  )
    return true;
  return (
    "cause" in error && error.cause !== error && isDuplicateName(error.cause)
  );
};
