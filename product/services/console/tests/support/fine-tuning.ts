import type {
  TrainingRunEvent,
  TrainingRunEventPayload,
} from "@/store/fine-tuning-types";

export const runEvent = (
  id: number,
  source: TrainingRunEvent["source"],
  payload: TrainingRunEventPayload,
): TrainingRunEvent => ({
  id,
  attempt: 1,
  at: new Date(Date.UTC(2026, 8, 1, 0, 0, id)).toISOString(),
  source,
  payload,
});
