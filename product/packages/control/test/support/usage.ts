import { randomUUID } from "node:crypto";

export const range = {
  from: new Date("2026-08-01T00:00:00.000Z"),
  to: new Date("2026-09-01T00:00:00.000Z"),
};

export const generation = (charge: string, completedAt: string) => ({
  id: randomUUID(),
  external_id: null,
  model_id: "vendor/model",
  status: "succeeded",
  streamed: 1,
  charge,
  input_tokens: 10,
  cached_input_tokens: 0,
  cache_write_tokens: 0,
  output_tokens: 20,
  reasoning_tokens: 0,
  finish_reason: "stop",
  error_code: null,
  usable_output_delivered: 1,
  cancellation_owner: null,
  received_at: completedAt,
  started_at: completedAt,
  first_token_at: completedAt,
  completed_at: completedAt,
});
