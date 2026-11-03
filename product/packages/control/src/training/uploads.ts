import { mkdtemp, open, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  CreateModelUploadSchema,
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
import { createTrainingStore } from "./store.js";
import { createModelUploadStore } from "./upload-store.js";

export const createModelUploads = (
  database: ControlDatabase,
  storage?: Pick<
    ObjectStorage,
    "signUpload" | "read" | "downloadFile" | "putFile" | "uri"
  >,
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
      const prefix = `runs/${upload.id}/upload`;
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
        const prefix = `runs/${id}/upload`;
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
        const weightsFile = await open(weightsPath, "r");
        try {
          rank = (
            await validateAdapterFiles(
              config,
              adapterFileReader(weightsFile, weightsSize),
              (catalogModel(input.base_model_id) as CatalogEntry | undefined)
                ?.training?.model ?? input.base_model_id,
            )
          ).r;
        } catch {
          throw new ControlServiceError(
            "conflict",
            "Invalid LoRA adapter. Check the base model, config, tensor pairs, rank and safetensors format.",
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
          base_model_revision: input.base_model_revision,
        });
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
