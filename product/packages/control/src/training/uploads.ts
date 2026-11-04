import { mkdtemp, open, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  CreateModelUploadSchema,
  MAX_UPLOADED_ADAPTER_RANK,
  type CreateModelUpload,
} from "@gradiated/contracts";
import {
  catalogModel,
  type CatalogEntry,
} from "@gradiated/contracts/model-catalog";
import { requireWorkspaceEditor } from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import type { ObjectStorage } from "../storage/object-storage.js";
import {
  adapterArchive,
  adapterFileReader,
  validateAdapterFiles,
} from "./adapter-upload.js";
import {
  readBaseModelConfiguration,
  type BaseModelConfiguration,
} from "./base-model-configuration.js";
import { createTrainingStore } from "./store.js";
import { createModelUploadStore } from "./upload-store.js";

export const createModelUploads = (
  database: ControlDatabase,
  storage?: Pick<
    ObjectStorage,
    "signUpload" | "read" | "downloadFile" | "putFile" | "delete" | "uri"
  >,
  loadBaseConfiguration: (
    repository: string,
    revision: string,
  ) => Promise<BaseModelConfiguration> = readBaseModelConfiguration,
) => {
  let validating = false;
  const uploads = createModelUploadStore(database);
  const records = createTrainingStore(database);
  const requireStorage = () => {
    if (!storage)
      throw new ControlServiceError(
        "unavailable",
        "Model upload storage is not configured.",
      );

    return storage;
  };
  const discardInputs = async (id: string) => {
    try {
      await requireStorage().delete([
        `uploads/${id}/adapter_config.json`,
        `uploads/${id}/adapter_model.safetensors`,
      ]);
    } catch {
      // The staging lifecycle expires leftovers and late PUTs after one day.
    }
  };

  return {
    async create(
      userId: string,
      workspaceId: string,
      value: CreateModelUpload,
    ) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const objects = requireStorage();
      const input = CreateModelUploadSchema.parse(value);
      const model = await records.getModel(input.base_model_id);
      if (!model)
        throw new ControlServiceError(
          "not_found",
          "The base model was not found.",
        );

      const task = await records.getTask(workspaceId, input.task);
      if (input.create_task && task)
        throw new ControlServiceError(
          "conflict",
          "A task with this name already exists. Upload a version from that task instead.",
        );
      if (!input.create_task && !task)
        throw new ControlServiceError("not_found", "The task was not found.");

      const upload = await uploads.create(workspaceId, input);
      const prefix = `uploads/${upload.id}`;
      return {
        id: upload.id,
        config_url: await objects.signUpload(
          `${prefix}/adapter_config.json`,
          3600,
          input.config_size,
        ),
        weights_url: await objects.signUpload(
          `${prefix}/adapter_model.safetensors`,
          3600,
          input.weights_size,
        ),
        expires_at: new Date(
          upload.createdAt.getTime() + 3600_000,
        ).toISOString(),
      };
    },
    async complete(userId: string, workspaceId: string, id: string) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const objects = requireStorage();
      const upload = await uploads.get(workspaceId, id);
      if (!upload)
        throw new ControlServiceError("not_found", "The upload was not found.");
      if (upload.versionId) {
        const task = await records.getTask(workspaceId, upload.input.task);
        if (!task)
          throw new ControlServiceError("not_found", "The task was not found.");
        const version = await records.getVersion(task.id, upload.versionId);
        if (!version)
          throw new ControlServiceError(
            "not_found",
            "The version was not found.",
          );
        await discardInputs(id);
        return { task, version };
      }
      if (Date.now() - upload.createdAt.getTime() > 3600_000)
        throw new ControlServiceError(
          "conflict",
          "This upload has expired. Start a new upload.",
        );

      if (validating)
        throw new ControlServiceError(
          "unavailable",
          "Another adapter is being validated. Please try again shortly.",
        );

      validating = true;
      let directory: string | undefined;
      try {
        directory = await mkdtemp(join(tmpdir(), "gradiated-adapter-"));
        const weightsPath = join(directory, "adapter_model.safetensors");
        const archivePath = join(directory, "adapter.tar.gz");
        const { input } = upload;
        const model = await records.getModel(input.base_model_id);
        if (!model)
          throw new ControlServiceError(
            "not_found",
            "The base model was not found.",
          );

        const supported = (
          catalogModel(input.base_model_id) as CatalogEntry | undefined
        )?.training;
        if (!supported)
          throw new ControlServiceError(
            "unavailable",
            "This model does not yet have a supported LoRA upload validation profile.",
          );
        const baseRepository =
          supported.model ?? model.properties.hugging_face_id ?? model.id;
        const baseConfiguration = await loadBaseConfiguration(
          baseRepository,
          supported.revision,
        );
        if (
          !baseConfiguration.projectionShapes ||
          !Object.keys(baseConfiguration.projectionShapes).length
        )
          throw new ControlServiceError(
            "unavailable",
            "Tensor shape validation is not available for this serving architecture. No model version was published.",
          );
        const prefix = `uploads/${id}`;
        let config: Uint8Array;
        let weightsSize: number;
        try {
          const [configResult, weightsResult] = await Promise.allSettled([
            objects.read(`${prefix}/adapter_config.json`, {
              maxBytes: input.config_size,
              timeoutMs: 30_000,
            }),
            objects.downloadFile(
              `${prefix}/adapter_model.safetensors`,
              weightsPath,
              {
                maxBytes: input.weights_size,
                timeoutMs: 120_000,
              },
            ),
          ]);
          if (
            configResult.status === "rejected" ||
            weightsResult.status === "rejected"
          )
            throw new Error("Adapter download failed.");

          config = configResult.value;
          weightsSize = weightsResult.value;
        } catch {
          throw new ControlServiceError(
            "conflict",
            "The adapter files could not be read. Check that both files finished uploading.",
          );
        }
        if (
          config.length !== input.config_size ||
          weightsSize !== input.weights_size
        )
          throw new ControlServiceError(
            "conflict",
            "The uploaded files do not match their declared sizes.",
          );

        let rank: number;
        let declaredRevision: string | undefined;
        const weightsFile = await open(weightsPath, "r");
        try {
          const validated = await validateAdapterFiles(
            config,
            adapterFileReader(weightsFile, weightsSize),
            baseRepository,
            baseConfiguration,
          );
          if (
            typeof validated.revision === "string" &&
            validated.revision.length <= 300
          )
            declaredRevision = validated.revision;

          rank = validated.r;
        } catch {
          throw new ControlServiceError(
            "conflict",
            `Invalid LoRA adapter. Check the base model and checkpoint revision, config, complete layer/expert coverage, tensor pairs, rank (maximum ${MAX_UPLOADED_ADAPTER_RANK}) and safetensors format.`,
          );
        } finally {
          await weightsFile.close();
        }
        const archive = await adapterArchive(
          config,
          weightsPath,
          weightsSize,
          archivePath,
        );
        const { sha256 } = archive;
        const key = `runs/${id}/output/${sha256}/adapter.tar.gz`;
        await objects.putFile(key, archivePath, archive);
        const version = await uploads.publish(workspaceId, id, {
          format: "peft_lora",
          artifact_uri: objects.uri(key),
          sha256,
          size_bytes: archive.sizeBytes,
          rank,
          ...(declaredRevision
            ? { declared_base_model_revision: declaredRevision }
            : {}),
          ...(declaredRevision && /^[0-9a-f]{40}$/.test(declaredRevision)
            ? { base_model_revision: declaredRevision }
            : {}),
          validated_base_model_revision: supported.revision,
        });
        await discardInputs(id);
        const task = await records.getTask(workspaceId, input.task);
        if (!task)
          throw new ControlServiceError("not_found", "The task was not found.");
        return { task, version };
      } finally {
        try {
          if (directory) await rm(directory, { recursive: true, force: true });
        } finally {
          validating = false;
        }
      }
    },
  };
};
