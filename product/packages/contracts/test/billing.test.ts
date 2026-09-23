import { describe, expect, it } from "vitest";

import { CreateTopUpCheckoutSchema } from "../src/index.js";

describe("CreateTopUpCheckoutSchema", () => {
  it.each(["5000000000", "10000000000000"])("accepts %s nano-USD", (amount) => {
    expect(CreateTopUpCheckoutSchema.safeParse({ amount }).success).toBe(true);
  });

  it.each([
    ["below the minimum", "4990000000"],
    ["above the maximum", "10000010000000"],
    ["a fraction of a cent", "5000000001"],
    ["a negative amount", "-5000000000"],
  ])("rejects %s", (_, amount) => {
    const result = CreateTopUpCheckoutSchema.safeParse({ amount });

    expect(result.success).toBe(false);
    expect(result.error?.issues).toContainEqual(
      expect.objectContaining({ path: ["amount"] }),
    );
  });

  it.each(["abc", "1.5", ""])(
    "returns issues without throwing for %j",
    (amount) => {
      const result = CreateTopUpCheckoutSchema.safeParse({ amount });

      expect(result.success).toBe(false);
      expect(result.error?.issues).toContainEqual(
        expect.objectContaining({ path: ["amount"] }),
      );
    },
  );
});
