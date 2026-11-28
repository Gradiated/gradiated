import { z } from "zod";
import { mkdtemp, open, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { v7 as uuidv7 } from "uuid";
import {
  CARTRIDGE_FILE,
  DEPLOYABLE_ARTIFACT_FORMATS,
  GRAD_ARTIFACT_BUNDLE,
  MAX_UPLOADED_ADAPTER_RANK,
  ModelNameSegmentSchema,
  PLANNED_ARTIFACT_FORMATS,
  VersionNameSchema,
  type GradArtifactSource,
  type TaskVersionAdapter,
} from "@gradiated/contracts";
import {
  MODEL_CATALOG,
  type CatalogEntry,
} from "@gradiated/contracts/model-catalog";
import { requireWorkspaceEditor } from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import type { ObjectStorage } from "../storage/object-storage.js";
import { adapterFileReader, validateAdapterFiles } from "./adapter-upload.js";
import {
  readBaseModelConfiguration,
  type BaseModelConfiguration,
} from "./base-model-configuration.js";
import { validateCartridgeFile } from "./cartridge-upload.js";
import {
  GradArtifactError,
  versionPinHolder,
  type GradArtifact,
  type GradArtifacts,
} from "./grad.js";
import {
  isBundleError,
  readGradBundle,
  type GradManifest,
} from "./grad-bundle.js";
import { createPublishStore } from "./publish-store.js";
import type { AdapterQualifier, QualificationLock } from "./qualification.js";
import type { TaskRecord, TaskVersionRecord } from "./records.js";
import { createTrainingStore } from "./store.js";

// Bundles are read whole to check them; the largest LoRA (Qwen3 32B, rank 32,
// all seven projections, F32) is about 1.1 GB.
export const MAX_ARTIFACT_BUNDLE_BYTES = 4 * 1024 * 1024 * 1024;

export type PublishErrorCode =
  | "artifact_not_servable"
  | "artifact_checksum_mismatch"
  | "format_not_servable"
  | "format_not_servable_yet"
  | "base_model_not_servable"
  | "base_revision_mismatch"
  | "invalid_artifact"
  | "model_base_mismatch"
  | "version_name_taken"
  | "version_in_production";

export class PublishError extends Error {
  constructor(
    readonly code: PublishErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "PublishError";
  }
}

export type QualificationOutcome = "passed" | "rejected" | "pending";

export type PublishResult = {
  task: TaskRecord;
  version: TaskVersionRecord;
  created: boolean;
  qualification: { outcome: QualificationOutcome; detail?: string };
};

const deployable = new Set<string>(DEPLOYABLE_ARTIFACT_FORMATS);
// Version 2 only adds provenance to the manifest (ARTIFACT_FORMATS, "Opening a bundle").
const SUPPORTED_FORMAT_VERSIONS = new Set([1, 2]);
const planned = new Set<string>(PLANNED_ARTIFACT_FORMATS);

export const checkArtifactFormat = (artifact: GradArtifact) => {
  if (planned.has(artifact.format))
    throw new PublishError(
      "format_not_servable_yet",
      `Gradiated Cloud does not serve ${artifact.format} artifacts yet. Supported formats: ${DEPLOYABLE_ARTIFACT_FORMATS.join(", ")}.`,
    );
  if (!deployable.has(artifact.format))
    throw new PublishError(
      "format_not_servable",
      `${artifact.format} artifacts cannot be served. Supported formats: ${DEPLOYABLE_ARTIFACT_FORMATS.join(", ")}.`,
    );
};

/** A serving base for grad's base model ID, such as qwen/qwen3-8b. */
export const ServingBaseSchema = z.strictObject({
  model_id: z.string().min(1),
  repository: z.string().min(1),
  revision: z.string().regex(/^[0-9a-f]{40}$/),
});
export const ServingBasesSchema = z.record(z.string(), ServingBaseSchema);
export type ServingBases = z.infer<typeof ServingBasesSchema>;

export type ServingBase = {
  modelId: string;
  repository: string;
  revision: string;
};

// grad names bases by catalog ID and Hugging Face repo; serving names them by
// its own catalog ID. Configured bases win, then the catalog's training profiles.
export const servingBase = (
  manifest: GradManifest,
  configured: ServingBases = {},
): ServingBase => {
  const override = configured[manifest.base_model];
  const entry = override
    ? undefined
    : (MODEL_CATALOG as readonly CatalogEntry[]).find(
        (model) =>
          model.training &&
          (model.training.model ?? model.id) === manifest.base_model_repo,
      );
  const base: ServingBase | undefined = override
    ? {
        modelId: override.model_id,
        repository: override.repository,
        revision: override.revision,
      }
    : entry?.training && {
        modelId: entry.id,
        repository: entry.training.model ?? entry.id,
        revision: entry.training.revision,
      };
  if (!base || (override && override.repository !== manifest.base_model_repo))
    throw new PublishError(
      "base_model_not_servable",
      `No Gradiated serving pool hosts adapters for ${manifest.base_model_repo ?? manifest.base_model}.`,
    );
  if (manifest.base_model_revision !== base.revision)
    throw new PublishError(
      "base_revision_mismatch",
      `The artifact was trained on ${manifest.base_model_repo} revision ${manifest.base_model_revision ?? "(unknown)"}, but serving pins revision ${base.revision}. Retrain on the pinned revision.`,
    );

  return base;
};

const invalid = (message: string) =>
  new PublishError("invalid_artifact", message);

export const createArtifactPublisher = ({
  database,
  grad,
  bundles,
  qualifyAdapter,
  lockQualification,
  loadBaseConfiguration = readBaseModelConfiguration,
  servingBases = {},
}: {
  database: ControlDatabase;
  grad?: GradArtifacts;
  bundles?: Pick<ObjectStorage, "stream" | "uri">;
  qualifyAdapter?: AdapterQualifier;
  lockQualification?: QualificationLock;
  loadBaseConfiguration?: (
    repository: string,
    revision: string,
  ) => Promise<BaseModelConfiguration>;
  servingBases?: ServingBases;
}) => {
  const store = createPublishStore(database);
  const records = createTrainingStore(database);

  const requireGrad = () => {
    if (!grad || !bundles)
      throw new ControlServiceError(
        "unavailable",
        "Publishing from artifacts is not configured.",
      );

    return { grad, bundles };
  };

  // Reads the bundle in place and builds the version's adapter from its files.
  const verifiedAdapter = async (
    artifact: GradArtifact,
    storage: Pick<ObjectStorage, "stream" | "uri">,
  ): Promise<{
    adapter: TaskVersionAdapter;
    base: ServingBase;
  }> => {
    if (artifact.size_bytes > MAX_ARTIFACT_BUNDLE_BYTES)
      throw invalid("The artifact is larger than serving accepts.");

    const { key } = artifact;
    const source: GradArtifactSource = {
      kind: "grad",
      artifact_id: artifact.id,
      artifact_source: artifact.source,
      bundle: GRAD_ARTIFACT_BUNDLE,
    };
    const directory = await mkdtemp(join(tmpdir(), "gradiated-artifact-"));
    try {
      const keep =
        artifact.format === "cartridge"
          ? new Set([CARTRIDGE_FILE])
          : new Set(["adapter_config.json", "adapter_model.safetensors"]);
      let bundle: Awaited<ReturnType<typeof readGradBundle>>;
      try {
        bundle = await readGradBundle(
          storage.stream(key, {
            maxBytes: artifact.size_bytes,
            timeoutMs: 600_000,
          }),
          {
            directory,
            keep,
            sizeBytes: artifact.size_bytes,
            sha256: artifact.sha256,
            maxUnpackedBytes: 2 * MAX_ARTIFACT_BUNDLE_BYTES,
          },
        );
      } catch (error) {
        if (isBundleError(error))
          throw invalid(`Invalid artifact bundle: ${(error as Error).message}`);
        throw new ControlServiceError(
          "unavailable",
          "The artifact could not be read from storage. Try again shortly.",
          error,
        );
      }

      const { manifest, files } = bundle;
      if (
        manifest.format !== artifact.format ||
        !SUPPORTED_FORMAT_VERSIONS.has(manifest.format_version) ||
        !manifest.deployable
      )
        throw invalid(
          "The bundle's manifest does not match the artifact, or its format version is not supported.",
        );
      const base = servingBase(manifest, servingBases);
      const baseConfiguration = await loadBaseConfiguration(
        base.repository,
        base.revision,
      );
      const common = {
        artifact_uri: storage.uri(key),
        sha256: artifact.sha256,
        size_bytes: artifact.size_bytes,
        source,
        base_model_revision: base.revision,
        validated_base_model_revision: base.revision,
      };
      if ([...keep].some((name) => !files.has(name)))
        throw invalid(
          `A ${artifact.format} bundle must contain ${[...keep].join(" and ")}.`,
        );

      if (artifact.format === "cartridge") {
        const file = files.get(CARTRIDGE_FILE)!;
        const model = await records.getModel(base.modelId);
        const maxTokens =
          model?.properties.input_modalities[0]?.supported_inputs
            .max_context_length.value;
        if (!baseConfiguration.hiddenSize || !maxTokens)
          throw new ControlServiceError(
            "unavailable",
            "Cartridge validation is not available for this base model.",
          );

        const handle = await open(file.path, "r");
        try {
          const shape = await validateCartridgeFile(handle, file.sizeBytes, {
            hiddenSize: baseConfiguration.hiddenSize,
            maxTokens,
            ...(baseConfiguration.vocabSize
              ? { vocabSize: baseConfiguration.vocabSize }
              : {}),
          });
          return {
            base,
            adapter: {
              format: "cartridge",
              ...common,
              num_tokens: shape.numTokens,
              hidden_size: shape.hiddenSize,
              placement: "system_prompt_start",
              separator: shape.separator,
              has_slot_token_ids: shape.hasSlotTokenIds,
            },
          };
        } catch (error) {
          throw invalid(
            `Invalid cartridge: ${error instanceof Error ? error.message : "unreadable file"}`,
          );
        } finally {
          await handle.close();
        }
      }

      if (!baseConfiguration.projectionShapes)
        throw new ControlServiceError(
          "unavailable",
          "Tensor shape validation is not available for this base model.",
        );

      const config = await readFile(files.get("adapter_config.json")!.path);
      const weights = files.get("adapter_model.safetensors")!;
      const handle = await open(weights.path, "r");
      try {
        const validated = await validateAdapterFiles(
          config,
          adapterFileReader(handle, weights.sizeBytes),
          base.repository,
          baseConfiguration,
        );
        if (validated.revision !== manifest.base_model_revision)
          throw new Error("adapter_config.json names another base revision.");

        return {
          base,
          adapter: { format: "peft_lora", ...common, rank: validated.r },
        };
      } catch (error) {
        throw invalid(
          `Invalid LoRA adapter (maximum rank ${MAX_UPLOADED_ADAPTER_RANK}): ${error instanceof Error ? error.message : "unreadable files"}`,
        );
      } finally {
        await handle.close();
      }
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  };

  const qualify = async (
    version: TaskVersionRecord,
  ): Promise<
    PublishResult["qualification"] & { version: TaskVersionRecord }
  > => {
    if (version.status === "available") return { outcome: "passed", version };
    if (!qualifyAdapter) return { outcome: "pending", version };

    const release = lockQualification
      ? await lockQualification(version.id)
      : async () => undefined;
    if (!release)
      return {
        outcome: "pending",
        detail: "This version is already being tested for serving.",
        version,
      };

    try {
      await qualifyAdapter(version);
      return {
        outcome: "passed",
        version: (await store.markAvailable(version.id)) ?? version,
      };
    } catch (error) {
      if (!(error instanceof ControlServiceError)) throw error;

      return {
        outcome: error.code === "conflict" ? "rejected" : "pending",
        detail: error.message,
        version,
      };
    } finally {
      await release().catch(() => undefined);
    }
  };

  const publish = async (
    workspaceId: string,
    input: { artifact: string; task?: string; name?: string },
  ): Promise<PublishResult> => {
    const { grad, bundles } = requireGrad();
    const artifact = await grad
      .resolve(workspaceId, input.artifact)
      .catch((error: unknown) => {
        if (error instanceof GradArtifactError)
          throw new PublishError(
            error.code === "artifact_checksum_mismatch"
              ? "artifact_checksum_mismatch"
              : "artifact_not_servable",
            error.message,
          );
        throw error;
      });
    if (!artifact)
      throw new ControlServiceError("not_found", "The artifact was not found.");

    checkArtifactFormat(artifact);
    const taskName = ModelNameSegmentSchema.safeParse(
      input.task ?? artifact.name,
    );
    const versionName = VersionNameSchema.safeParse(
      input.name ?? artifact.version,
    );
    if (!taskName.success || !versionName.success)
      throw invalid(
        "The model or version name is invalid. Pass a name made of letters, digits, '.', '_' and '-'.",
      );

    const existingTask = await records.getTask(workspaceId, taskName.data);
    if (existingTask) {
      const existing = await store.findArtifactVersion(
        existingTask.id,
        artifact.id,
      );
      if (existing) {
        const { version, ...qualification } = await qualify(existing);
        return { task: existingTask, version, created: false, qualification };
      }
    } else {
      const problem = await records.modelNameProblem(
        workspaceId,
        taskName.data,
      );
      if (problem) throw new ControlServiceError("conflict", problem);
    }

    const { adapter, base } = await verifiedAdapter(artifact, bundles);
    if (existingTask && existingTask.baseModelId !== base.modelId)
      throw new PublishError(
        "model_base_mismatch",
        `The model ${existingTask.name} serves ${existingTask.baseModelId ?? "another base"}; this artifact adapts ${base.modelId}.`,
      );

    const versionId = uuidv7();
    const holder = versionPinHolder(versionId);
    const unpin = () =>
      grad.unpin(workspaceId, artifact.id, holder).catch(() => undefined);

    try {
      await grad.pin(workspaceId, artifact.id, holder);
    } catch (error) {
      if (error instanceof GradArtifactError)
        throw error.code === "artifact_not_found"
          ? new ControlServiceError("not_found", error.message)
          : new PublishError("artifact_not_servable", error.message);
      throw error;
    }

    let inserted: Awaited<ReturnType<typeof store.insertVersion>>;
    try {
      inserted = await store.insertVersion({
        id: versionId,
        workspaceId,
        task: taskName.data,
        baseModelId: base.modelId,
        name: versionName.data,
        adapter,
      });
    } catch (error) {
      await unpin();
      throw error;
    }
    if (inserted.outcome !== "created") await unpin();
    if (inserted.outcome === "base_mismatch")
      throw new PublishError(
        "model_base_mismatch",
        `The model ${inserted.task.name} serves another base model.`,
      );
    if (inserted.outcome === "name_taken")
      throw new PublishError(
        "version_name_taken",
        `The model ${inserted.task.name} already has a version named ${versionName.data}. Pass another name.`,
      );

    const { version, ...qualification } = await qualify(inserted.version);
    return {
      task: inserted.task,
      version,
      created: inserted.outcome === "created",
      qualification,
    };
  };

  const releasePin = async (release: {
    versionId: string;
    workspaceId: string;
    artifactId: string;
  }) => {
    if (!grad) return false;

    try {
      await grad.unpin(
        release.workspaceId,
        release.artifactId,
        versionPinHolder(release.versionId),
      );
    } catch {
      return false;
    }
    await store.completePinRelease(release.versionId);
    return true;
  };

  return {
    async publish(
      userId: string,
      workspaceId: string,
      input: { artifact: string; task?: string; name?: string },
    ) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      return publish(workspaceId, input);
    },

    publishAsService: publish,

    async deleteVersion(
      userId: string,
      workspaceId: string,
      taskName: string,
      reference: string,
    ) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const task = await records.getTask(workspaceId, taskName);
      if (!task)
        throw new ControlServiceError("not_found", "The task was not found.");

      const version = await records.findVersion(task.id, reference);
      if (!version)
        throw new ControlServiceError(
          "not_found",
          "The version was not found.",
        );

      const deleted = await store.deleteVersion(task.id, version.id);
      if (!deleted)
        throw new PublishError(
          "version_in_production",
          "This version serves production. Promote another version first.",
        );

      if (deleted.release) await releasePin(deleted.release);
    },

    // Retries releases that grad did not confirm when their version was deleted.
    async releasePendingPins(now = new Date()) {
      const pending = await store.pendingPinReleases(
        new Date(now.getTime() - 60_000),
      );
      let released = 0;
      for (const release of pending) if (await releasePin(release)) released++;

      return { pending: pending.length, released };
    },
  };
};

export type ArtifactPublisher = ReturnType<typeof createArtifactPublisher>;
