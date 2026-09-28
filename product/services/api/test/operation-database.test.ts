import { afterEach, describe, expect, it, vi } from "vitest";

import { requiredEnv } from "../src/operations/database.js";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("operation environment", () => {
  it("rejects a missing variable", () => {
    vi.stubEnv("OPERATION_TEST_VALUE", "");

    expect(() => requiredEnv("OPERATION_TEST_VALUE")).toThrow(
      "OPERATION_TEST_VALUE is required",
    );
  });
});
