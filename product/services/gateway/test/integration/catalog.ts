import type { JsonObject } from "./json.js";
import type { RuntimeKind } from "./mock-runtimes/server.js";

export interface Release {
  readonly schema_version: 1;
  readonly runtime_revision: string;
  readonly protocol?: "system_one";
  readonly model_path: string;
  readonly model_revision: string;
  readonly runtime_model_name: string;
  readonly tokenizer_path: string;
  readonly tokenizer_revision: string;
}

export interface Deployment {
  readonly id: string;
  status: "available" | "unavailable" | "draining";
  readonly provider: string;
  readonly region: string;
  readonly fault_domain: string;
  readonly service_url: string;
  release: Release;
}

export interface DeploymentRuntimeStatus {
  readonly schema_version: 1;
  readonly deployment_id: string;
  readonly runtime_revision: string;
  readonly received_at: string;
  readonly healthy: boolean;
  readonly accepting_requests: boolean;
  readonly reason_code: string | null;
}

export interface ModelRecord {
  readonly name: string;
  status: "available" | "unavailable" | "retired";
  readonly properties: JsonObject;
}

export const release = (
  kind: RuntimeKind,
  model: string,
  runtimeModel: string,
): Release => ({
  schema_version: 1,
  runtime_revision: `${kind === "kev" ? "kev-" : "vllm-"}${model}`,
  // Field order must match the Rust struct: the release JSON is hashed.
  ...(kind === "kev" ? { protocol: "system_one" as const } : {}),
  model_path: model,
  model_revision: "synthetic-v1",
  runtime_model_name: runtimeModel,
  tokenizer_path: "unused/chat-owned",
  tokenizer_revision: "synthetic-v1",
});

export const modelRecord = (kind: RuntimeKind): ModelRecord => ({
  name: `Synthetic ${kind}`,
  status: "available",
  properties: {
    schema_version: 1,
    description: "Synthetic contract tests",
    released_at: "2026-01-01T00:00:00Z",
    hugging_face_id: null,
    quantization: "bf16",
    tokenizer: null,
    input_modalities: [
      {
        type: "text",
        supported_inputs: {
          max_context_length: { value: 8192, unit: "token" },
          max_prompt_length: { value: 4096, unit: "token" },
        },
        pricing: [
          { type: "prompt", unit: "token", cost: 10 },
          { type: "cached_prompt", unit: "token", cost: 2 },
        ],
      },
    ],
    output_modalities: [
      {
        type: "text",
        max_length: { value: 256, unit: "token" },
        default_length: { value: 16, unit: "token" },
        streaming: kind === "vllm",
        supported_parameters: {
          temperature: { type: "range", min: 0, max: 2 },
          tools: { type: "unknown" },
          tool_choice: { type: "unknown" },
        },
        pricing: [
          { type: "completion", unit: "token", cost: kind === "kev" ? 0 : 20 },
        ],
      },
    ],
    passthrough_parameters: {},
    deprecation_date: null,
  },
});
