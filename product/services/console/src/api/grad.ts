import { Grad } from "@gradiated/grad";
import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";

import { ApiError } from "@/api/client";
import { authorizedFetch, type TokenSource } from "@/lib/grad/authorized-fetch";
import {
  usageSummarySchema,
  type UsageGroupBy,
  type UsageSummary,
} from "@/lib/grad/usage";

const PRODUCT_API_URL = import.meta.env.VITE_API_URL ?? "";

export const GRAD_API_URL =
  import.meta.env.VITE_GRAD_API_URL ?? "https://api.gradiated.com";

export const TRAINING_TOKEN_LIFETIME_MS = 5 * 60_000;
export const TRAINING_TOKEN_RENEWAL_MS = 60_000;

const trainingTokenSchema = z.object({
  token: z.string().min(1),
  expires_at: z.string(),
});

export type TrainingToken = z.infer<typeof trainingTokenSchema>;

const productUrl = (path: string) => `${PRODUCT_API_URL}${path}`;

const productJson = async (response: Response) => {
  const body: unknown = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiError(response.status, body);

  return body;
};

// POST /api/v1/workspaces/{workspace_id}/training-tokens: a five-minute JWT
// (aud=training) for the signed-in member, minted with Better Auth's jwt().
export const fetchTrainingToken = async (
  workspaceId: string,
): Promise<TrainingToken> =>
  trainingTokenSchema.parse(
    await productJson(
      await fetch(
        productUrl(
          `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/training-tokens`,
        ),
        { method: "POST", credentials: "include" },
      ),
    ),
  );

export const tokenStaleTime = (expiresAt: string, now: number) =>
  Math.max(Date.parse(expiresAt) - now - TRAINING_TOKEN_RENEWAL_MS, 0);

export const trainingTokenQuery = (
  workspaceId: string,
  fetchToken: (
    workspaceId: string,
  ) => Promise<TrainingToken> = fetchTrainingToken,
) =>
  queryOptions({
    queryKey: ["training-token", workspaceId],
    queryFn: () => fetchToken(workspaceId),
    staleTime: ({ state }) =>
      state.data ? tokenStaleTime(state.data.expires_at, Date.now()) : 0,
    gcTime: TRAINING_TOKEN_LIFETIME_MS,
    retry: false,
  });

export const gradBaseUrl = (origin: string) =>
  new URL(GRAD_API_URL, origin).toString().replace(/\/+$/, "");

export interface GradSession {
  grad: Grad;
  baseURL: string;
  fetch: typeof globalThis.fetch;
}

export const createGradSession = ({
  baseURL,
  token,
  fetch,
}: {
  baseURL: string;
  token: TokenSource;
  fetch?: typeof globalThis.fetch;
}): GradSession => {
  const authorized = authorizedFetch({
    apiOrigin: new URL(baseURL).origin,
    token,
    ...(fetch ? { fetch } : {}),
  });

  return {
    // The empty key turns off the SDK's own credentials; requests carry the JWT instead.
    grad: new Grad({ baseURL, apiKey: "", fetch: authorized }),
    baseURL,
    fetch: authorized,
  };
};

// The published SDK (0.2.0-alpha.3) predates `grad.usage.summary()`.
export const getUsageSummary = async (
  session: GradSession,
  { from, to, groupBy }: { from: string; to: string; groupBy: UsageGroupBy },
  signal?: AbortSignal,
): Promise<UsageSummary> => {
  const url = new URL(`${session.baseURL}/v1/usage/summary`);
  url.search = new URLSearchParams({ from, to, group_by: groupBy }).toString();

  const response = await session.fetch(url, {
    headers: { Accept: "application/json" },
    ...(signal ? { signal } : {}),
  });
  const body: unknown = await response.json().catch(() => undefined);

  if (!response.ok) throw new ApiError(response.status, body);

  return usageSummarySchema.parse(body);
};

const publishedVersionSchema = z.object({
  id: z.string(),
  name: z.string(),
});

export type PublishedVersion = z.infer<typeof publishedVersionSchema>;

export class DeployUnavailableError extends Error {
  constructor() {
    super("Deploying trained artifacts is not available yet.");
    this.name = "DeployUnavailableError";
  }
}

// 404/405/501 mean the inference API has no publish-from-artifact route yet.
const UNAVAILABLE_STATUSES = new Set([404, 405, 501]);

// POST /api/v1/workspaces/{ws}/tasks/{task}/versions with an artifact_id
// publishes a grad artifact as an unpromoted Version of the Model.
export const publishArtifactVersion = async ({
  workspaceId,
  model,
  artifactId,
  version,
  idempotencyKey,
}: {
  workspaceId: string;
  model: string;
  artifactId: string;
  version: string;
  idempotencyKey: string;
}): Promise<PublishedVersion> => {
  const response = await fetch(
    productUrl(
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/tasks/${encodeURIComponent(model)}/versions`,
    ),
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({ artifact_id: artifactId, name: version }),
    },
  );

  if (UNAVAILABLE_STATUSES.has(response.status))
    throw new DeployUnavailableError();

  return publishedVersionSchema.parse(await productJson(response));
};
