import {
  GetSecretValueCommand,
  SecretsManagerClient,
} from "@aws-sdk/client-secrets-manager";

const secretIds = {
  openai: "gradiated/prod/providers/openai",
  anthropic: "gradiated/prod/providers/anthropic",
} as const;

export type Provider = keyof typeof secretIds;

export class CredentialLoader {
  readonly #client: SecretsManagerClient;

  constructor(client = new SecretsManagerClient({ region: "us-east-1" })) {
    this.#client = client;
  }

  load = async (provider: Provider): Promise<string> => {
    try {
      const secretId = secretIds[provider];

      if (!secretId) {
        throw new Error();
      }

      const response = await this.#client.send(
        new GetSecretValueCommand({
          SecretId: secretId,
          VersionStage: "AWSCURRENT",
        }),
      );
      const value: unknown = JSON.parse(response.SecretString ?? "");

      if (typeof value !== "object" || value === null) {
        throw new Error();
      }

      const secret = value as Record<string, unknown>;
      const key =
        secret.activeSlot === "primary"
          ? secret.primaryApiKey
          : secret.activeSlot === "secondary"
            ? secret.secondaryApiKey
            : undefined;

      if (typeof key !== "string" || !key || key.trim() !== key) {
        throw new Error();
      }

      return key;
    } catch {
      throw new Error("Cannot load provider credential.");
    }
  };
}
