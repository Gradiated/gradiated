import {
  GetSecretValueCommand,
  SecretsManagerClient,
} from "@aws-sdk/client-secrets-manager";
import { describe, expect, it, vi } from "vitest";

import { CredentialLoader } from "../src/index.js";

const setup = () => {
  const client = new SecretsManagerClient({ region: "us-east-1" });
  const send =
    vi.fn<
      (
        command: GetSecretValueCommand,
      ) => Promise<{ SecretString: string | undefined }>
    >();
  vi.spyOn(client, "send").mockImplementation((command) =>
    send(command as GetSecretValueCommand),
  );

  return { loader: new CredentialLoader(client), send };
};

describe("CredentialLoader", () => {
  it.each(["openai", "anthropic"] as const)(
    "loads %s and observes a manual slot change on the next load",
    async (provider) => {
      const { loader, send } = setup();
      const keys = { primaryApiKey: "first-key", secondaryApiKey: "next-key" };
      send.mockResolvedValueOnce({
        SecretString: JSON.stringify({ ...keys, activeSlot: "primary" }),
      });
      send.mockResolvedValueOnce({
        SecretString: JSON.stringify({ ...keys, activeSlot: "secondary" }),
      });

      expect(await loader.load(provider)).toBe("first-key");
      expect(await loader.load(provider)).toBe("next-key");
      expect(send).toHaveBeenCalledTimes(2);
      expect(send.mock.calls[0]?.[0].input).toEqual({
        SecretId: `gradiated/prod/providers/${provider}`,
        VersionStage: "AWSCURRENT",
      });
    },
  );

  it.each([
    undefined,
    "private-malformed-value",
    "null",
    JSON.stringify({ primaryApiKey: "private-key" }),
    JSON.stringify({
      activeSlot: "private-invalid-slot",
      primaryApiKey: "private-key",
    }),
    JSON.stringify({ activeSlot: "primary", secondaryApiKey: "private-key" }),
    JSON.stringify({ activeSlot: "primary", primaryApiKey: "" }),
    JSON.stringify({ activeSlot: "secondary", secondaryApiKey: " " }),
    JSON.stringify({ activeSlot: "primary", primaryApiKey: 123 }),
  ])("rejects invalid secrets without exposing their values", async (value) => {
    const { loader, send } = setup();
    send.mockResolvedValue({ SecretString: value });

    await expect(loader.load("openai")).rejects.toThrow(
      /^Cannot load provider credential\.$/,
    );
  });

  it("does not require a revoked inactive key", async () => {
    const { loader, send } = setup();
    send.mockResolvedValue({
      SecretString: JSON.stringify({
        activeSlot: "secondary",
        secondaryApiKey: "next-key",
      }),
    });

    expect(await loader.load("anthropic")).toBe("next-key");
  });

  it("does not expose SDK errors or return a cached key after a failed read", async () => {
    const { loader, send } = setup();
    send.mockResolvedValueOnce({
      SecretString: JSON.stringify({
        activeSlot: "primary",
        primaryApiKey: "first-key",
      }),
    });
    send.mockRejectedValueOnce(new Error("private-provider-value"));

    expect(await loader.load("openai")).toBe("first-key");
    await expect(loader.load("openai")).rejects.toThrow(
      /^Cannot load provider credential\.$/,
    );
  });
});
