import { CredentialIdentitySchema } from "@gradiated/contracts";
import { z } from "zod";

import type {
  ApiClient,
  Caller,
  InferenceAuthorization,
  Principal,
} from "./api-client.js";
import type { CredentialCache } from "./cache.js";
import type { McpMetrics } from "./metrics.js";

// Revoking a credential takes effect at the API on every tool call; the cache only names the workspace.
const IDENTITY_TTL_SECONDS = 300;

// Bounds how long a cached key outlives a revoked OAuth token, and keeps it well before its own expiry.
const INFERENCE_KEY_TTL_SECONDS = 300;
const INFERENCE_KEY_MARGIN_MS = 60_000;

const InferenceKeySchema = z.object({
  secret: z.string(),
  expiresAt: z.number(),
});

export type Credentials = ReturnType<typeof createCredentials>;

export const createCredentials = (
  api: ApiClient,
  cache: CredentialCache,
  metrics?: McpMetrics,
) => {
  // Null when the credential is unknown; throws when the API cannot say.
  const authenticate = async (caller: Caller): Promise<Principal | null> => {
    const cached = CredentialIdentitySchema.safeParse(
      await cache.read("identity", caller.credential),
    );
    if (cached.success) {
      metrics?.authentication("accepted");
      return { caller, identity: cached.data };
    }

    let identity;
    try {
      identity = await api.authenticate(caller);
    } catch (error) {
      metrics?.authentication("error");
      throw error;
    }
    if (!identity) {
      metrics?.authentication("rejected");
      return null;
    }

    metrics?.authentication("accepted");
    await cache.write(
      "identity",
      caller.credential,
      identity,
      IDENTITY_TTL_SECONDS,
    );

    return { caller, identity };
  };

  // The gateway takes only API keys, so an OAuth connection calls models with a short-lived one.
  const inferenceAuthorization =
    ({ caller, identity }: Principal): InferenceAuthorization =>
    async (renew) => {
      if (identity.type === "api_key") return caller.credential;

      if (!renew) {
        const cached = InferenceKeySchema.safeParse(
          await cache.read("inference-key", caller.credential),
        );
        if (
          cached.success &&
          cached.data.expiresAt - Date.now() > INFERENCE_KEY_MARGIN_MS
        ) {
          metrics?.inferenceCredential("cached");
          return cached.data.secret;
        }
      }

      let key;
      try {
        key = await api.createInferenceKey(caller);
      } catch (error) {
        metrics?.inferenceCredential("failed");
        throw error;
      }

      metrics?.inferenceCredential("minted");
      await cache.write(
        "inference-key",
        caller.credential,
        key,
        Math.min(
          INFERENCE_KEY_TTL_SECONDS,
          (key.expiresAt - Date.now() - INFERENCE_KEY_MARGIN_MS) / 1000,
        ),
      );

      return key.secret;
    };

  return { authenticate, inferenceAuthorization };
};
