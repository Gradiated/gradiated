import { describe, expect, it } from "vitest";

import { parseApiEnvironment } from "../src/environment.js";

const token = "deployment-status-token-with-32-characters";

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
      DEPLOYMENT_STATUS_INGEST_TOKENS: new Map(),
    });
  });

  it("accepts an optional isolated adapter control credential", () => {
    const controlToken = "a".repeat(43);
    expect(
      parseApiEnvironment({
        ...baseEnvironment,
        LORA_CONTROL_TOKEN: controlToken,
      }).LORA_CONTROL_TOKEN,
    ).toBe(controlToken);
    for (const value of ["", "short", "a".repeat(257), "a".repeat(32) + "!"]) {
      expect(() =>
        parseApiEnvironment({ ...baseEnvironment, LORA_CONTROL_TOKEN: value }),
      ).toThrow();
    }
  });

  it("requires the Nomad issuer configuration as a pair", () => {
    expect(() =>
      parseApiEnvironment({
        ...baseEnvironment,
        NOMAD_CA_KMS_KEY: "alias/test",
      }),
    ).toThrow("must be configured together");
    expect(() =>
      parseApiEnvironment({ ...baseEnvironment, NOMAD_CA_PEM: "public-ca" }),
    ).toThrow("must be configured together");
    expect(
      parseApiEnvironment({
        ...baseEnvironment,
        NOMAD_CA_KMS_KEY: "alias/test",
        NOMAD_CA_PEM: "public-ca",
      }),
    ).toMatchObject({
      NOMAD_CA_KMS_KEY: "alias/test",
      NOMAD_CA_PEM: "public-ca",
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

  it("maps each deployment status token to one provider", () => {
    const environment = parseApiEnvironment({
      ...baseEnvironment,
      DEPLOYMENT_STATUS_INGEST_TOKENS: JSON.stringify({
        runpod: token,
        nomad: `${token}!`,
      }),
    });

    expect([...environment.DEPLOYMENT_STATUS_INGEST_TOKENS]).toEqual([
      ["runpod", token],
      ["nomad", `${token}!`],
    ]);
  });

  it("rejects non-JSON deployment status tokens without quoting them", () => {
    const parse = () =>
      parseApiEnvironment({
        ...baseEnvironment,
        DEPLOYMENT_STATUS_INGEST_TOKENS: `{"runpod": ${token}`,
      });

    expect(parse).toThrow(
      "DEPLOYMENT_STATUS_INGEST_TOKENS must be a JSON object",
    );
    expect(parse).not.toThrow(token);
  });

  it.each([
    {
      name: "an array",
      value: JSON.stringify([token]),
      message: "DEPLOYMENT_STATUS_INGEST_TOKENS must be a JSON object",
    },
    {
      name: "an invalid provider name",
      value: JSON.stringify({ RunPod: token }),
      message: "Deployment status provider names are invalid",
    },
    {
      name: "a short token",
      value: JSON.stringify({ runpod: "short" }),
      message: "Deployment status tokens must contain at least 32 characters",
    },
  ])("rejects deployment status tokens with $name", ({ value, message }) => {
    expect(() =>
      parseApiEnvironment({
        ...baseEnvironment,
        DEPLOYMENT_STATUS_INGEST_TOKENS: value,
      }),
    ).toThrow(message);
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
