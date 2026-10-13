import { describe, expect, it } from "vitest";

import { parseApiEnvironment } from "../src/environment.js";

const baseEnvironment = {
  BETTER_AUTH_SECRET: "local-only-not-secret-change-in-production-0001",
  BETTER_AUTH_URL: "http://localhost:3001",
  DATABASE_URL: "postgres://localhost:5432/gradiated",
  VALKEY_URL: "redis://localhost:6379",
  AUTH_EMAIL_FROM: "Gradiated <auth@example.com>",
  RESEND_API_KEY: "re_test",
};

describe("API environment", () => {
  it("applies the API-only defaults", () => {
    expect(parseApiEnvironment(baseEnvironment)).toMatchObject({
      METRICS_PORT: 9_464,
      PROFILING_HOST: "0.0.0.0",
      PROFILING_PORT: 3_003,
    });
  });

  it("rejects a profiling token shorter than 32 characters", () => {
    expect(() =>
      parseApiEnvironment({
        ...baseEnvironment,
        PROFILING_INGEST_TOKEN: "short",
      }),
    ).toThrow();
  });

  it("sends email through Resend outside test mode", () => {
    expect(parseApiEnvironment(baseEnvironment).authEmail).toEqual({
      kind: "resend",
      from: "Gradiated <auth@example.com>",
      apiKey: "re_test",
    });
  });

  it.each(["AUTH_EMAIL_FROM", "RESEND_API_KEY"] as const)(
    "requires %s outside test mode",
    (name) => {
      const { [name]: _omitted, ...environment } = baseEnvironment;

      expect(() => parseApiEnvironment(environment)).toThrow(
        "AUTH_EMAIL_FROM and RESEND_API_KEY are required when AUTH_TEST_MODE is disabled.",
      );
    },
  );

  it("captures email in test mode", () => {
    const environment = parseApiEnvironment({
      BETTER_AUTH_SECRET: baseEnvironment.BETTER_AUTH_SECRET,
      BETTER_AUTH_URL: baseEnvironment.BETTER_AUTH_URL,
      DATABASE_URL: baseEnvironment.DATABASE_URL,
      VALKEY_URL: baseEnvironment.VALKEY_URL,
      AUTH_TEST_MODE: "true",
    });

    expect(environment.authEmail).toEqual({ kind: "test" });
  });
});
