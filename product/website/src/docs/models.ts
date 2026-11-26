import { MODEL_CATALOG } from "../../../packages/contracts/src/model-catalog";

const ids: readonly string[] = MODEL_CATALOG.map((entry) => entry.id);

const pickModel = (pattern: RegExp, fallback: string): string =>
  (ids.find((id) => pattern.test(id)) ?? fallback).trim().toLowerCase();

export const OPUS_MODEL = pickModel(
  /^anthropic\/claude-opus-/,
  "anthropic/claude-opus-5-5",
);

export const SONNET_MODEL = pickModel(
  /^anthropic\/claude-sonnet-/,
  "anthropic/claude-sonnet-5-5",
);

export const GPT_MODEL = pickModel(/^openai\/gpt-/, "openai/gpt-6.1-sol");
