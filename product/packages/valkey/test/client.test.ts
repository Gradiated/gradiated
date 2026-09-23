import { SignatureV4 } from "@smithy/signature-v4";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createValkeyClient, type ValkeyEnvironment } from "../src/index.js";

const iamSettings = {
  VALKEY_IAM_CACHE_NAME: "gradiated-cache",
  VALKEY_IAM_REGION: "us-east-1",
  VALKEY_IAM_USER: "gateway",
};

const iamEnvironment = (url: string) => ({ ...iamSettings, VALKEY_URL: url });

const iamCredentials = (url = "rediss://cache.example.test") => {
  const provider = createValkeyClient(iamEnvironment(url)).options
    ?.credentialsProvider;

  if (provider?.type !== "async-credentials-provider") {
    throw new Error("Expected an async credentials provider.");
  }

  return provider.credentials;
};

const stubAwsCredentials = () => {
  vi.stubEnv("AWS_PROFILE", undefined);
  vi.stubEnv("AWS_SESSION_TOKEN", undefined);
  vi.stubEnv("AWS_ACCESS_KEY_ID", "AKIDEXAMPLE");
  vi.stubEnv(
    "AWS_SECRET_ACCESS_KEY",
    "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
  );
};

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("createValkeyClient", () => {
  it("connects by URL without IAM variables", () => {
    const client = createValkeyClient({ VALKEY_URL: "redis://localhost:6379" });

    expect(client.options?.url).toBe("redis://localhost:6379");
    expect(client.options?.credentialsProvider).toBeUndefined();
  });

  it.each([
    ["rediss://cache.example.test", 6379],
    ["rediss://cache.example.test:7000", 7000],
  ])("uses a TLS socket for IAM on %s", (url, port) => {
    const client = createValkeyClient(iamEnvironment(url));

    expect(client.options?.socket).toEqual({
      host: "cache.example.test",
      port,
      tls: true,
    });
  });

  it.each([
    [["VALKEY_IAM_CACHE_NAME"]],
    [["VALKEY_IAM_REGION"]],
    [["VALKEY_IAM_USER"]],
    [["VALKEY_IAM_CACHE_NAME", "VALKEY_IAM_REGION"]],
    [["VALKEY_IAM_CACHE_NAME", "VALKEY_IAM_USER"]],
    [["VALKEY_IAM_REGION", "VALKEY_IAM_USER"]],
  ] as const)("rejects IAM settings missing %j", (missing) => {
    const environment: ValkeyEnvironment = iamEnvironment(
      "rediss://cache.example.test",
    );

    for (const name of missing) {
      delete environment[name];
    }

    expect(() => createValkeyClient(environment)).toThrow(
      `Valkey IAM settings are incomplete; missing ${missing.join(", ")}`,
    );
  });

  it("rejects IAM over a non-TLS URL", () => {
    expect(() =>
      createValkeyClient(iamEnvironment("redis://cache.example.test")),
    ).toThrow("Valkey IAM authentication requires a rediss:// URL");
  });

  it("signs an ElastiCache IAM token from environment credentials", async () => {
    stubAwsCredentials();

    const { username, password } = await iamCredentials()();

    expect(username).toBe("gateway");
    expect(password).toMatch(/^gradiated-cache\/\?/);
    expect(password).toContain("Action=connect");
    expect(password).toContain("ResourceType=ServerlessCache");
    expect(password).toContain("User=gateway");
    expect(password).toContain("X-Amz-Expires=900");
    expect(password).not.toContain("http://");
  });

  it("presigns a token on every connect from one client", async () => {
    stubAwsCredentials();

    const presign = vi.spyOn(SignatureV4.prototype, "presign");
    const credentials = iamCredentials();

    await credentials();
    await credentials();

    expect(presign).toHaveBeenCalledTimes(2);
  });
});
