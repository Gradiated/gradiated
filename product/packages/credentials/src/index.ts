import {
  GetSecretValueCommand,
  SecretsManagerClient,
} from "@aws-sdk/client-secrets-manager";

const secretIds = {
  openai: "gradiated/prod/providers/openai",
  anthropic: "gradiated/prod/providers/anthropic",
  openrouter: "gradiated/prod/providers/openrouter",
} as const;

const CACHE_TTL_MS = 5 * 60 * 1000;

export type Provider = keyof typeof secretIds;

export class CredentialLoader {
  readonly #client: SecretsManagerClient;
  readonly #now: () => number;
  readonly #cache = new Map<Provider, { key: string; expiresAt: number }>();
  readonly #pending = new Map<Provider, Promise<string>>();

  constructor(
    client = new SecretsManagerClient({ region: "us-east-1" }),
    now = () => performance.now(),
  ) {
    this.#client = client;
    this.#now = now;
  }

  load = async (provider: Provider): Promise<string> => {
    const cached = this.#cache.get(provider);
    if (cached && this.#now() < cached.expiresAt) return cached.key;

    this.#cache.delete(provider);
    const pending = this.#pending.get(provider);
    if (pending) return pending;

    const request = this.#read(provider)
      .then((key) => {
        this.#cache.set(provider, {
          key,
          expiresAt: this.#now() + CACHE_TTL_MS,
        });
        return key;
      })
      .finally(() => this.#pending.delete(provider));
    this.#pending.set(provider, request);
    return request;
  };

  #read = async (provider: Provider): Promise<string> => {
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
