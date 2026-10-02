import type { ControlDatabase } from "../db/client.js";
import { createTrainingStore } from "./store.js";
import { ControlServiceError } from "../errors.js";
import type { ContentStore } from "../traces/storage.js";
import { reconcileTrainingRun } from "./engine.js";
import { countTrainingTraces } from "./traces.js";
import {
  TrainingAdmissionError,
  type TrainingInput,
  type TrainingEngine,
} from "./types.js";

export const prepareTraining = async (
  database: ControlDatabase,
  store: ContentStore,
  target: string | { workspaceId: string; name: string },
  trigger: TrainingInput["trigger"],
  requestedBy: string | null,
  engine?: TrainingEngine,
): Promise<TrainingInput> => {
  const records = createTrainingStore(database);
  const row = await records.admissionContext(target);

  if (!row || row.workspace.archivedAt)
    throw new ControlServiceError("not_found", "The task was not found.");

  const { task, workspace } = row;
  const taskId = task.id;

  const active = await records.activeRun(taskId);

  if (active) {
    const reconciled = await reconcileTrainingRun(database, engine, active);
    if (!reconciled || (await records.activeRun(taskId)))
      throw new TrainingAdmissionError("already_training", "Already training.");
  }

  if (!task.baseModelId || !task.comparisonModelId)
    throw new TrainingAdmissionError(
      "training_not_configured",
      "Choose a base model and comparison model before training.",
    );

  if (
    trigger === "automation" &&
    (!workspace.traceCaptureEnabled ||
      !task.trainingSchedule ||
      row.organization.status !== "active")
  )
    throw new TrainingAdmissionError(
      "training_not_configured",
      "Automatic training is disabled.",
    );

  const last = await records.lastSuccessfulCutoff(taskId);

  const cutoff = new Date();
  const threshold = trigger === "manual" ? 100 : 500;
  const count = await countTrainingTraces(store, {
    workspaceId: workspace.id,
    task: task.name,
    since: last,
    cutoff,
    threshold,
  });

  if (count < threshold)
    throw new TrainingAdmissionError(
      "insufficient_traces",
      `Training needs at least ${threshold} new traces since the last successful run; found ${count}.`,
    );

  return {
    taskId,
    workspaceId: workspace.id,
    name: task.name,
    baseModelId: task.baseModelId,
    comparisonModelId: task.comparisonModelId,
    judgeModelId: task.judgeModelId,
    inputCutoff: cutoff.toISOString(),
    trigger,
    requestedBy,
  };
};
