import { z } from "zod";
import {
  ARTIFACT_SOURCES,
  GradArtifactIdSchema,
  UuidSchema,
} from "@gradiated/contracts";
import { ControlServiceError } from "../errors.js";

const ApiArtifactSchema = z
  .object({
    id: GradArtifactIdSchema,
    workspace_id: z.string().min(1),
    name: z.string().min(1).max(64),
    version: z.string().min(1).max(128),
    format: z.string().min(1),
    recipe_kind: z.string().min(1),
    base_model: z.string().min(1),
    sha256: z.string().regex(/^[0-9a-f]{64}$/),
    size_bytes: z.number().int().positive(),
    manifest: z.record(z.string(), z.unknown()),
    provenance: z.object({ source: z.enum(ARTIFACT_SOURCES) }).passthrough(),
  })
  .passthrough();

// The API manifest is a hint; the bundle's own manifest.json is authoritative.
export const GradArtifactSchema = ApiArtifactSchema.transform((artifact) => ({
  id: artifact.id,
  workspace_id: artifact.workspace_id,
  name: artifact.name,
  version: artifact.version,
  format: artifact.format,
  recipe_kind: artifact.recipe_kind,
  base_model: artifact.base_model,
  sha256: artifact.sha256,
  size_bytes: artifact.size_bytes,
  source: artifact.provenance.source,
}));
export type GradArtifact = z.output<typeof GradArtifactSchema>;

const ProblemSchema = z.object({ code: z.string().optional() }).passthrough();
const ResolvedSchema = z.object({ artifact: z.unknown() }).passthrough();

const notServable = () =>
  new GradArtifactError(
    "artifact_not_servable",
    "This artifact cannot be published.",
  );

// Every call the product makes is on artifacts, under one scope.
export type GradScope = "artifacts:pin";

export const versionPinHolder = (versionId: string) =>
  `inference:version:${UuidSchema.parse(versionId)}`;

export type GradArtifacts = {
  resolve(workspaceId: string, reference: string): Promise<GradArtifact | null>;
  pin(workspaceId: string, artifactId: string, holder: string): Promise<void>;
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
 * grad-server's internal artifact routes. `authorization` returns the bearer for
 * a call scoped to one workspace: a service JWT (`sub = service:inference`).
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
    scopes: readonly GradScope[];
  }) => Promise<string>;
  fetch?: typeof fetch;
  timeoutMs?: number;
}): GradArtifacts => {
  const call = async (
    method: "GET" | "POST" | "PUT" | "DELETE",
    path: string,
    workspaceId: string,
    scopes: readonly GradScope[],
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

  const workspacePath = (workspaceId: string) =>
    `/internal/v1/workspaces/${encodeURIComponent(UuidSchema.parse(workspaceId))}`;
  const pinPath = (workspaceId: string, artifactId: string, holder: string) =>
    `${workspacePath(workspaceId)}/artifacts/${encodeURIComponent(GradArtifactIdSchema.parse(artifactId))}/pins/${encodeURIComponent(holder)}`;

  const artifact = (json: unknown) => {
    const parsed = GradArtifactSchema.safeParse(json);
    if (!parsed.success) throw unavailable(parsed.error);

    return parsed.data;
  };

  return {
    async resolve(workspaceId, reference) {
      const { status, json } = await call(
        "GET",
        `${workspacePath(workspaceId)}/artifacts/${encodeURIComponent(reference)}`,
        workspaceId,
        ["artifacts:pin"],
      );
      if (status === 404) return null;
      if (status === 409) throw notServable();
      if (status !== 200) throw unavailable(new Error(`resolve ${status}`));

      const resolved = artifact(ResolvedSchema.safeParse(json).data?.artifact);
      if (resolved.workspace_id !== workspaceId) return null;

      return resolved;
    },

    async pin(workspaceId, artifactId, holder) {
      const { status, json } = await call(
        "PUT",
        pinPath(workspaceId, artifactId, holder),
        workspaceId,
        ["artifacts:pin"],
        { reason: "A Gradiated model version serves this artifact." },
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
        throw notServable();
      if (status !== 200 && status !== 201)
        throw unavailable(new Error(`pin ${status}`));
    },

    async unpin(workspaceId, artifactId, holder) {
      const { status } = await call(
        "DELETE",
        pinPath(workspaceId, artifactId, holder),
        workspaceId,
        ["artifacts:pin"],
      );
      if (status !== 204 && status !== 200 && status !== 404)
        throw unavailable(new Error(`unpin ${status}`));
    },
  };
};
