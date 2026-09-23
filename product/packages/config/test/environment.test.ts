import { describe, expect, it } from "vitest";

import { parseEnvironment } from "../src/index.js";

const validEnvironment = (
  overrides: NodeJS.ProcessEnv = {},
): NodeJS.ProcessEnv => ({
  AUTH_TEST_MODE: "true",
  BETTER_AUTH_SECRET: "s".repeat(32),
  BETTER_AUTH_URL: "http://localhost:3001",
  DATABASE_URL: "postgres://gradiated@localhost:5432/gradiated",
  VALKEY_URL: "redis://localhost:6379",
  ...overrides,
});

const productionEnvironment = (overrides: NodeJS.ProcessEnv = {}) =>
  validEnvironment({
    AUTH_EMAIL_FROM: "Gradiated <auth@gradiated.test>",
    AUTH_TEST_MODE: "false",
    GITHUB_CLIENT_ID: "github-id",
    GITHUB_CLIENT_SECRET: "github-secret",
    GOOGLE_CLIENT_ID: "google-id",
    GOOGLE_CLIENT_SECRET: "google-secret",
    NODE_ENV: "production",
    RESEND_API_KEY: "resend-key",
    STRIPE_SECRET_KEY: "sk_test",
    STRIPE_WEBHOOK_SECRET: "whsec_test",
    VALKEY_IAM_CACHE_NAME: "gradiated-cache",
    VALKEY_IAM_REGION: "us-east-1",
    VALKEY_IAM_USER: "api",
    ...overrides,
  });

const githubMessage =
  "GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET must be configured together.";
const googleMessage =
  "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured together.";
const stripeMessage =
  "STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET must be configured together.";
const valkeyIamMessage =
  "VALKEY_IAM_CACHE_NAME, VALKEY_IAM_REGION and VALKEY_IAM_USER must be configured together.";

const expectIssue = (
  environment: NodeJS.ProcessEnv,
  message: string,
  variable: string,
) => {
  expect(() => parseEnvironment(environment)).toThrow(
    expect.objectContaining({
      issues: expect.arrayContaining([
        expect.objectContaining({ message, path: [variable] }),
      ]),
    }),
  );
};

describe("parseEnvironment", () => {
  it("applies defaults to the minimal development environment", () => {
    expect(parseEnvironment(validEnvironment())).toMatchObject({
      AUTH_TEST_MODE: true,
      CONSOLE_URL: "http://localhost:3000",
      HOST: "0.0.0.0",
      NODE_ENV: "development",
      PORT: 3001,
      TRUSTED_ORIGINS: ["http://localhost:3000", "http://127.0.0.1:3000"],
    });
  });

  it("trims and splits trusted origins", () => {
    const environment = parseEnvironment(
      validEnvironment({ TRUSTED_ORIGINS: " http://a.test , http://b.test " }),
    );

    expect(environment.TRUSTED_ORIGINS).toEqual([
      "http://a.test",
      "http://b.test",
    ]);
  });

  it("rejects an empty trusted origin", () => {
    expect(() =>
      parseEnvironment(validEnvironment({ TRUSTED_ORIGINS: "http://a.test," })),
    ).toThrow();
  });

  it("coerces the port", () => {
    expect(parseEnvironment(validEnvironment({ PORT: "8080" })).PORT).toBe(
      8080,
    );
  });

  it.each(["0", "65536"])("rejects port %s", (port) => {
    expect(() => parseEnvironment(validEnvironment({ PORT: port }))).toThrow();
  });

  it("rejects a short auth secret", () => {
    expect(() =>
      parseEnvironment(
        validEnvironment({ BETTER_AUTH_SECRET: "s".repeat(31) }),
      ),
    ).toThrow();
  });

  it.each<[NodeJS.ProcessEnv, string, string]>([
    [{ GITHUB_CLIENT_ID: "github-id" }, githubMessage, "GITHUB_CLIENT_SECRET"],
    [
      { GITHUB_CLIENT_SECRET: "github-secret" },
      githubMessage,
      "GITHUB_CLIENT_ID",
    ],
    [{ GOOGLE_CLIENT_ID: "google-id" }, googleMessage, "GOOGLE_CLIENT_SECRET"],
    [
      { GOOGLE_CLIENT_SECRET: "google-secret" },
      googleMessage,
      "GOOGLE_CLIENT_ID",
    ],
    [{ STRIPE_SECRET_KEY: "sk_test" }, stripeMessage, "STRIPE_WEBHOOK_SECRET"],
    [
      { STRIPE_WEBHOOK_SECRET: "whsec_test" },
      stripeMessage,
      "STRIPE_SECRET_KEY",
    ],
    [{ VALKEY_IAM_CACHE_NAME: "cache" }, valkeyIamMessage, "VALKEY_IAM_REGION"],
    [
      { VALKEY_IAM_REGION: "us-east-1" },
      valkeyIamMessage,
      "VALKEY_IAM_CACHE_NAME",
    ],
    [{ VALKEY_IAM_USER: "api" }, valkeyIamMessage, "VALKEY_IAM_CACHE_NAME"],
    [
      { VALKEY_IAM_CACHE_NAME: "cache", VALKEY_IAM_REGION: "us-east-1" },
      valkeyIamMessage,
      "VALKEY_IAM_USER",
    ],
    [
      { VALKEY_IAM_CACHE_NAME: "cache", VALKEY_IAM_USER: "api" },
      valkeyIamMessage,
      "VALKEY_IAM_REGION",
    ],
    [
      { VALKEY_IAM_REGION: "us-east-1", VALKEY_IAM_USER: "api" },
      valkeyIamMessage,
      "VALKEY_IAM_CACHE_NAME",
    ],
  ])("rejects the partial group %o", (overrides, message, variable) => {
    expectIssue(validEnvironment(overrides), message, variable);
  });

  it("rejects a whitespace-only Valkey IAM variable", () => {
    expect(() =>
      parseEnvironment(productionEnvironment({ VALKEY_IAM_REGION: " " })),
    ).toThrow(
      expect.objectContaining({
        issues: expect.arrayContaining([
          expect.objectContaining({
            code: "too_small",
            path: ["VALKEY_IAM_REGION"],
          }),
        ]),
      }),
    );
  });

  it("rejects test mode in production", () => {
    expectIssue(
      productionEnvironment({ AUTH_TEST_MODE: "true" }),
      "AUTH_TEST_MODE cannot be enabled in production.",
      "AUTH_TEST_MODE",
    );
  });

  it.each<[NodeJS.ProcessEnv, string, string]>([
    [
      { GITHUB_CLIENT_ID: undefined, GITHUB_CLIENT_SECRET: undefined },
      "GitHub authentication credentials are required in production.",
      "GITHUB_CLIENT_ID",
    ],
    [
      { GOOGLE_CLIENT_ID: undefined, GOOGLE_CLIENT_SECRET: undefined },
      "Google authentication credentials are required in production.",
      "GOOGLE_CLIENT_ID",
    ],
  ])("rejects production without %o", (overrides, message, variable) => {
    expectIssue(productionEnvironment(overrides), message, variable);
  });

  it.each<[NodeJS.ProcessEnv, string]>([
    [{ AUTH_EMAIL_FROM: undefined }, "AUTH_EMAIL_FROM"],
    [{ RESEND_API_KEY: undefined }, "RESEND_API_KEY"],
    [
      { AUTH_EMAIL_FROM: undefined, RESEND_API_KEY: undefined },
      "AUTH_EMAIL_FROM",
    ],
  ])(
    "requires email delivery outside test mode without %o",
    (overrides, variable) => {
      expectIssue(
        validEnvironment({
          AUTH_EMAIL_FROM: "auth@gradiated.test",
          AUTH_TEST_MODE: "false",
          RESEND_API_KEY: "resend-key",
          ...overrides,
        }),
        "AUTH_EMAIL_FROM and RESEND_API_KEY are required when AUTH_TEST_MODE is disabled.",
        variable,
      );
    },
  );

  it("parses a complete production environment", () => {
    expect(parseEnvironment(productionEnvironment())).toMatchObject({
      AUTH_TEST_MODE: false,
      NODE_ENV: "production",
      VALKEY_IAM_USER: "api",
    });
  });

  it("returns a frozen environment", () => {
    expect(Object.isFrozen(parseEnvironment(validEnvironment()))).toBe(true);
  });
});
