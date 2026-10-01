import { describe, expect, it } from "vitest";
import { parseTemporalWorkerEnvironment } from "../src/environment.js";

const environment = {
  DATABASE_URL: "postgresql://localhost/gradiated",
  CONTENTS_BUCKET: "test-contents",
  TRAINING_EXECUTOR: "mock",
};

describe("Temporal worker configuration", () => {
  it("starts without ingestion, ClickHouse or Valkey configuration", () => {
    expect(parseTemporalWorkerEnvironment(environment).PORT).toBe(3005);
  });
  it("accepts the real executor without ingestion configuration", () => {
    expect(
      parseTemporalWorkerEnvironment({
        ...environment,
        TRAINING_EXECUTOR: "qwen-sft",
      }).TRAINING_EXECUTOR,
    ).toBe("qwen-sft");
  });
  it("requires an explicitly enabled executor", () => {
    expect(() =>
      parseTemporalWorkerEnvironment({
        ...environment,
        TRAINING_EXECUTOR: undefined,
      }),
    ).toThrow();
  });
});
