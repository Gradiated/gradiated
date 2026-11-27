import { z } from "zod";
import {
  ARTIFACT_SOURCES,
  GradArtifactIdSchema,
  UuidSchema,
} from "@gradiated/contracts";
import { ControlServiceError } from "../errors.js";

export const GradArtifactSchema = z
  .object({
    id: GradArtifactIdSchema,
    workspace_id: UuidSchema,
    name: z.string().min(1).max(64),
    version: z.string().min(1).max(128),
    kind: z.enum(["release", "checkpoint"]),
    source: z.enum(ARTIFACT_SOURCES),
    format: z.string().min(1),
    recipe_kind: z.string().min(1),
    base_model: z.string().min(1),
    base_model_repo: z.string().min(1).nullable(),
    base_model_revision: z.string().nullable(),
    sha256: z.string().regex(/^[0-9a-f]{64}$/),
    size_bytes: z.number().int().positive(),
  })
  .passthrough();
export type GradArtifact = z.infer<typeof GradArtifactSchema>;

const ProblemSchema = z.object({ code: z.string().optional() }).passthrough();

export const versionPinHolder = (versionId: string) =>
  `inference:version:${UuidSchema.parse(versionId)}`;

export type GradArtifacts = {
  resolve(workspaceId: string, reference: string): Promise<GradArtifact | null>;
  pin(
    workspaceId: string,
    artifactId: string,
    holder: string,
  ): Promise<GradArtifact>;
  unpin(workspaceId: string, artifactId: string, holder: string): Promise<void>;
};

export class GradArtifactError extends Error {
  constructor(
    readonly code: "artifact_not_servable" | "artifact_not_found",
    message: string,
  ) {
    super(message);
    this.name = "GradArtifactError";
  }
}

const unavailable = (cause?: unknown) =>
  new ControlServiceError(
    "unavailable",
    "The training service is unavailable. Try again shortly.",
    cause,
  );

/**
 * grad-server's artifact calls. `authorization` returns the bearer token for a
 * call scoped to one workspace: a service JWT (`sub = service:inference`).
 */
export const createGradArtifacts = ({
  baseUrl,
  authorization,
  fetch: request = fetch,
  timeoutMs = 10_000,
}: {
  baseUrl: string;
  authorization: (call: {
    workspaceId: string;
    scopes: readonly string[];
  }) => Promise<string>;
  fetch?: typeof fetch;
  timeoutMs?: number;
}): GradArtifacts => {
  const call = async (
    method: "GET" | "POST" | "PUT" | "DELETE",
    path: string,
    workspaceId: string,
    scopes: readonly string[],
    body?: unknown,
  ) => {
    let response: Response;
    try {
      const token = await authorization({ workspaceId, scopes });
      response = await request(new URL(path, baseUrl), {
        method,
        headers: {
          authorization: `Bearer ${token}`,
          accept: "application/json",
          ...(body === undefined ? {} : { "content-type": "application/json" }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        redirect: "error",
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (error) {
      throw unavailable(error);
    }

    const text = await response.text().catch(() => "");
    let json: unknown = undefined;
    try {
      json = text ? JSON.parse(text) : undefined;
    } catch {
      json = undefined;
    }
    return { status: response.status, json };
  };

  const artifact = (json: unknown) => {
    const parsed = GradArtifactSchema.safeParse(json);
    if (!parsed.success) throw unavailable(parsed.error);

    return parsed.data;
  };

  return {
    async resolve(workspaceId, reference) {
      const { status, json } = await call(
        "POST",
        "/internal/v1/artifacts/resolve",
        workspaceId,
        ["artifacts:read"],
        { workspace_id: workspaceId, ref: reference },
      );
      if (status === 404) return null;
      if (status !== 200) throw unavailable(new Error(`resolve ${status}`));

      const resolved = artifact(json);
      if (resolved.workspace_id !== workspaceId) return null;

      return resolved;
    },

    async pin(workspaceId, artifactId, holder) {
      const { status, json } = await call(
        "PUT",
        `/v1/artifacts/${encodeURIComponent(GradArtifactIdSchema.parse(artifactId))}/pins/${encodeURIComponent(holder)}`,
        workspaceId,
        ["artifacts:pin"],
      );
      if (status === 404)
        throw new GradArtifactError(
          "artifact_not_found",
          "The artifact was not found in this workspace.",
        );
      if (
        status === 409 &&
        ProblemSchema.safeParse(json).data?.code === "artifact_not_servable"
      )
        throw new GradArtifactError(
          "artifact_not_servable",
          "Checkpoints and test-only bundles cannot be published. Promote the checkpoint to an artifact first.",
        );
      if (status !== 200 && status !== 201)
        throw unavailable(new Error(`pin ${status}`));

      return artifact(json);
    },

    async unpin(workspaceId, artifactId, holder) {
      const { status } = await call(
        "DELETE",
        `/v1/artifacts/${encodeURIComponent(GradArtifactIdSchema.parse(artifactId))}/pins/${encodeURIComponent(holder)}`,
        workspaceId,
        ["artifacts:pin"],
      );
      if (status !== 204 && status !== 200 && status !== 404)
        throw unavailable(new Error(`unpin ${status}`));
    },
  };
};
