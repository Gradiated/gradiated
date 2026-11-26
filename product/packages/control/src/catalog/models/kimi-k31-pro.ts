import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import type { CatalogModelInput } from "../service.js";

export const kimiK31ProModelId = "moonshotai/kimi-k3.1-pro";
export const kimiK31ProArtifactModelPath = "moonshotai/Kimi-K3.1-Pro";
export const kimiK31ProTokenizerRevision =
  "d9e99b0792a5e93b78ea9bea62a68167e36ddd9e";
export const yetalabsKimiK31ProAbliteratedModelId =
  "yetalabs/kimi-k3.1-pro-abliterated";
export const yetalabsKimiK31ProAbliteratedArtifactModelPath =
  "yetalabs/Kimi-K3.1-Pro-abliterated";
export const yetalabsKimiK31ProAbliteratedTokenizerRevision =
  "0911ef0765f49d26dfa25bb0d071f29463f8000b";

export const createKimiK31ProModelConfiguration = () =>
  ({
    id: kimiK31ProModelId,
    name: modelDisplayName(kimiK31ProModelId),
    status: "available",
    type: "chat",
    openrouterModelId: kimiK31ProModelId,
    // Counts tokens in-gateway even when no local deployment supplies one.
    tokenizer: {
      path: kimiK31ProArtifactModelPath,
      revision: kimiK31ProTokenizerRevision,
    },
    properties: {
      description:
        "Moonshot AI's Kimi K3.1 Pro with MXFP4 routed experts, reasoning and tool use.",
      released_at: "2026-10-23T00:00:00.000Z",
      hugging_face_id: kimiK31ProArtifactModelPath,
      quantization: "mxfp4",
      tokenizer: "Kimi K3.1",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 1_048_576, unit: "token" },
          },
          pricing: [
            { type: "prompt", unit: "token", cost: 1_600 },
            { type: "cached_prompt", unit: "token", cost: 160 },
          ],
        },
      ],
      output_modalities: [
        {
          type: "text",
          max_length: { value: 131_072, unit: "token" },
          // A request without a limit may use the model maximum. The gateway
          // sends no limit, so the runtime also stops at the remaining context.
          default_length: { value: 131_072, unit: "token" },
          streaming: true,
          supported_parameters: {
            temperature: { type: "range", min: 0, max: 2 },
            top_p: { type: "range", min: 0, max: 1 },
            seed: { type: "integer", min: 0, max: Number.MAX_SAFE_INTEGER },
            frequency_penalty: { type: "range", min: -2, max: 2 },
            presence_penalty: { type: "range", min: -2, max: 2 },
            stop: { type: "unknown" },
            tools: { type: "unknown" },
            tool_choice: { type: "unknown" },
            parallel_tool_calls: { type: "boolean" },
            // Rendered into the Kimi prompt and, for json_schema, enforced by
            // the runtime grammar unless `strict` is false.
            response_format: { type: "unknown" },
            // Moonshot Partial Mode: `partial: true` on the final assistant
            // message. The gateway continues that message without reasoning.
            partial: { type: "boolean" },
            reasoning: { type: "unknown" },
            reasoning_effort: { type: "enum", values: ["low", "high", "max"] },
          },
          pricing: [
            { type: "completion", unit: "token", cost: 8_000 },
            { type: "internal_reasoning", unit: "token", cost: 8_000 },
          ],
        },
      ],
      default_parameters: {
        temperature: 1,
        top_p: 0.95,
        frequency_penalty: 0,
        presence_penalty: 0,
      },
      reasoning: {
        supported_efforts: ["low", "high", "max"],
        default_effort: "max",
      },
    },
  }) satisfies CatalogModelInput;

export const createYetalabsKimiK31ProAbliteratedModelConfiguration = () => {
  const base = createKimiK31ProModelConfiguration();

  return {
    ...base,
    id: yetalabsKimiK31ProAbliteratedModelId,
    name: modelDisplayName(yetalabsKimiK31ProAbliteratedModelId),
    status: "available",
    type: "chat",
    // OpenRouter does not serve YetaLabs' weights; stock Kimi K3.1 Pro is a different model.
    openrouterModelId: null,
    tokenizer: {
      path: yetalabsKimiK31ProAbliteratedArtifactModelPath,
      revision: yetalabsKimiK31ProAbliteratedTokenizerRevision,
    },
    properties: {
      ...base.properties,
      description:
        "YetaLabs' Kimi K3.1 Pro Cyber (MXFP4) with retained reasoning and tool use.",
      released_at: "2026-11-17T00:00:00.000Z",
      hugging_face_id: yetalabsKimiK31ProAbliteratedArtifactModelPath,
    },
  } satisfies CatalogModelInput;
};
