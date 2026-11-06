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
  it("keeps Slack Connect disabled by default and validates configured engineer IDs", () => {
    expect(
      parseApiEnvironment({ ...baseEnvironment, SLACK_BOT_TOKEN: "" }),
    ).toMatchObject({
      SLACK_CONNECT_ENABLED: "false",
      SLACK_BOT_TOKEN: undefined,
      SLACK_ENGINEER_USER_IDS: [],
    });
    expect(
      parseApiEnvironment({
        ...baseEnvironment,
        SLACK_ENGINEER_USER_IDS: "U123, W456",
      }).SLACK_ENGINEER_USER_IDS,
    ).toEqual(["U123", "W456"]);
    expect(() =>
      parseApiEnvironment({
        ...baseEnvironment,
        SLACK_ENGINEER_USER_IDS: "not-a-member-id",
      }),
    ).toThrow();
  });
  it("leaves embedded NDA signing disabled when PandaDoc credentials are absent or blank", () => {
    const environment = parseApiEnvironment({
      ...baseEnvironment,
      PANDADOC_API_KEY: "",
      PANDADOC_NDA_TEMPLATE_VERSION: " ",
    });
    expect(environment.PANDADOC_NDA_ENABLED).toBe("false");
    expect(environment.PANDADOC_API_KEY).toBeUndefined();
    expect(environment.PANDADOC_NDA_TEMPLATE_VERSION).toBeUndefined();
    expect(environment.PANDADOC_NDA_TEMPLATE_ID).toBe("bTmxaYhTaU2tQ28fLhVrHn");
  });
  it("defaults the NDA countersigner and accepts an override", () => {
    expect(parseApiEnvironment(baseEnvironment)).toMatchObject({
      PANDADOC_NDA_COUNTERSIGNER_COMPANY: "PostHog Inc.",
      PANDADOC_NDA_COUNTERSIGNER_NAME: "James Hawkins",
      PANDADOC_NDA_COUNTERSIGNER_TITLE: "Co-CEO",
    });
    expect(
      parseApiEnvironment({
        ...baseEnvironment,
        PANDADOC_NDA_COUNTERSIGNER_NAME: " Grace Hopper ",
      }).PANDADOC_NDA_COUNTERSIGNER_NAME,
    ).toBe("Grace Hopper");
  });
  it("applies the API-only defaults", () => {
    expect(parseApiEnvironment(baseEnvironment)).toMatchObject({
      METRICS_PORT: 9_464,
      PROFILING_HOST: "0.0.0.0",
      PROFILING_PORT: 3_003,
    });
  });

  it("binds local private control independently of the public listener", () => {
    expect(
      parseApiEnvironment({
        ...baseEnvironment,
        HOST: "0.0.0.0",
        GPU_CONTROL_HOST: "127.0.0.1",
        GPU_CONTROL_PORT: "3005",
      }),
    ).toMatchObject({
      HOST: "0.0.0.0",
      GPU_CONTROL_HOST: "127.0.0.1",
      GPU_CONTROL_PORT: 3005,
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
