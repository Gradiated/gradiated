import { describe, expect, it } from "vitest";

import { UsageEventSchema } from "../src/index.js";

const event = (amount: unknown) => ({
  event_id: "training:run-usage:run_1:1:1000",
  workspace_id: "0195b4f0-7e1f-7cc2-8a0d-6f1f6d0c3a11",
  product: "training",
  sku: "train:qwen/qwen3-8b",
  quantity: 1000,
  amount_nano_usd: amount,
  price_version: "pv_training_2026_11_27_placeholder",
  occurred_at: "2026-11-27T12:00:00.000Z",
  subject_id: "run_1",
});

describe("UsageEventSchema", () => {
  it.each([0, Number.MAX_SAFE_INTEGER, "0", String(Number.MAX_SAFE_INTEGER)])(
    "accepts the amount %j",
    (amount) => {
      expect(UsageEventSchema.parse(event(amount)).amount_nano_usd).toBe(
        BigInt(amount),
      );
    },
  );

  // The gateway's ledger replay refuses a balance outside the safe range.
  it.each([
    String(Number.MAX_SAFE_INTEGER + 1),
    "9223372036854775807",
    -1,
    "-1",
    1.5,
  ])("rejects the amount %j", (amount) => {
    expect(UsageEventSchema.safeParse(event(amount)).success).toBe(false);
  });
});
