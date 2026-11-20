import { randomUUID } from "node:crypto";
import type { PeftLoraAdapter } from "@gradiated/contracts";
import type { ControlDatabase } from "../../src/db/client.js";
import { eq } from "drizzle-orm";
import { tasks, workspaces } from "../../src/db/schema/index.js";
import { createCatalogService } from "../../src/catalog/service.js";
import type { TrainingInput } from "../../src/training/types.js";
import { modelInput, seedMember } from "./fixtures.js";

export const trainingAdapter: PeftLoraAdapter = {
  format: "peft_lora",
  artifact_uri: "s3://test/adapter",
  sha256: "a".repeat(64),
  size_bytes: 100,
  rank: 16,
};

export const seedTrainingTask = async (
  database: ControlDatabase,
  baseModelId?: string,
) => {
  const member = await seedMember(database, { role: "admin" });
  await database
    .update(workspaces)
    .set({ traceCaptureEnabled: true })
    .where(eq(workspaces.id, member.workspaceId));

  const model = await createCatalogService(database).upsertModel(
    modelInput(baseModelId ? { id: baseModelId } : {}),
  );
  const [task] = await database
    .insert(tasks)
    .values({
      id: randomUUID(),
      workspaceId: member.workspaceId,
      name: "triage",
      baseModelId: model.id,
      comparisonModelId: "openai/gpt-5",
      judgeModelId: "openai/gpt-5",
      trainingSchedule: "0 3 * * 1",
    })
    .returning();
  const input: TrainingInput = {
    taskId: task!.id,
    workspaceId: member.workspaceId,
    name: task!.name,
    baseModelId: model.id,
    comparisonModelId: "openai/gpt-5",
    judgeModelId: "openai/gpt-5",
    inputCutoff: "2026-09-30T12:00:00.000Z",
    trigger: "manual",
    requestedBy: member.userId,
  };

  return { ...member, task: task!, input };
};
