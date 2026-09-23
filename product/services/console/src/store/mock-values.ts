import { NANO_USD_PER_USD } from "@/lib/money";

export const BASE_MODEL_ID = "google/gemma-4-31b-it";
export const WORKSPACE_ID = "0198c36f-0000-7000-8000-00000000b001";
export const MOCK_MEMBER_EMAIL = "member@example.com";

export const MINUTE_MS = 60_000;
export const HOUR_MS = 60 * MINUTE_MS;
export const DAY_MS = 24 * HOUR_MS;

const LIST_PRICE_USD_PER_MILLION: Record<string, readonly [number, number]> = {
  "gpt-4o": [2.5, 10],
  "gpt-4o-mini": [0.15, 0.6],
  "claude-3-5-sonnet-20241022": [3, 15],
  "claude-3-5-haiku-20241022": [0.8, 4],
  [BASE_MODEL_ID]: [0.2, 0.6],
};

export const isoAt = (ms: number) => new Date(ms).toISOString();

export const round3 = (value: number) => Number(value.toFixed(3));

export const seededRandom = (seed: string): (() => number) => {
  let state = 0x811c9dc5;
  for (const char of seed) {
    state = Math.imul(state ^ char.charCodeAt(0), 0x01000193) >>> 0;
  }

  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let mixed = Math.imul(state ^ (state >>> 15), 1 | state);
    mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;

    return ((mixed ^ (mixed >>> 14)) >>> 0) / 0x1_0000_0000;
  };
};

export const fakeDigest = (seed: string): string => {
  const random = seededRandom(seed);

  return Array.from({ length: 8 }, () =>
    Math.floor(random() * 0x1_0000_0000)
      .toString(16)
      .padStart(8, "0"),
  ).join("");
};

export const priceForModel = (
  modelId: string,
  baseModelId: string = BASE_MODEL_ID,
): readonly [number, number] =>
  LIST_PRICE_USD_PER_MILLION[modelId] ??
  LIST_PRICE_USD_PER_MILLION[baseModelId] ?? [0, 0];

export const costNanoUsd = (
  modelId: string,
  inputTokens: number,
  outputTokens: number,
) => {
  const [input, output] = priceForModel(modelId);

  return Math.round(
    ((inputTokens * input + outputTokens * output) / 1_000_000) *
      Number(NANO_USD_PER_USD),
  );
};
