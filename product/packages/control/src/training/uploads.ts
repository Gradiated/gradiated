import { mkdtemp, open, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  CreateModelUploadSchema,
  TRAINING_BASE_MODELS,
  MAX_UPLOADED_ADAPTER_RANK,
  CARTRIDGE_FILE,
  type CreateModelUploadInput,
} from "@gradiated/contracts";
import {
  catalogModel,
  type CatalogEntry,
} from "@gradiated/contracts/model-catalog";
import {
  requireWorkspaceEditor,
  requireWorkspaceMembership,
} from "../access.js";
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
import { validateCartridgeFile } from "./cartridge-upload.js";
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
        `uploads/${id}/${CARTRIDGE_FILE}`,
      ]);
    } catch {
      // The staging lifecycle expires leftovers and late PUTs after one day.
    }
  };

  // Public catalog data: the pinned base checkpoint's layer layout.
  const structure = async (modelId: string) => {
    const model = await records.getModel(modelId);
    const entry = catalogModel(modelId) as CatalogEntry | undefined;
    // Serving-only models can still describe their layers for the explorer.
    const supported = entry?.training ?? entry?.architecture;
    if (!model || !supported)
      throw new ControlServiceError(
        "not_found",
        "No adapter validation profile exists for this model.",
      );

    return loadBaseConfiguration(
      supported.model ?? model.properties.hugging_face_id ?? model.id,
      supported.revision,
    );
  };

  return {
    async configuration(userId: string, workspaceId: string, modelId: string) {
      const membership = await requireWorkspaceMembership(database, {
        userId,
        workspaceId,
      });
      if (membership.workspace.archivedAt)
        throw new ControlServiceError(
          "not_found",
          "The workspace was not found.",
        );

      return structure(modelId);
    },
    structure,
    async create(
      userId: string,
      workspaceId: string,
      value: CreateModelUploadInput,
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

      if (
        model.status !== "available" &&
        !TRAINING_BASE_MODELS.some((base) => base.id === model.id)
      )
        throw new ControlServiceError(
          "conflict",
          "The base model is unavailable for training.",
        );

      const task = await records.getTask(workspaceId, input.task);
      if (input.create_task && task)
        throw new ControlServiceError(
          "conflict",
          "A task with this name already exists. Upload a version from that task instead.",
        );
      const problem = await records.modelNameProblem(workspaceId, input.task);
      if (problem) throw new ControlServiceError("conflict", problem);
      if (!input.create_task && !task)
        throw new ControlServiceError("not_found", "The task was not found.");

      if (
        !input.create_task &&
        task &&
        task.baseModelId !== input.base_model_id
      )
        throw new ControlServiceError(
          "conflict",
          "The adapter base model must match the task base model.",
        );

      const upload = await uploads.create(workspaceId, input);
      const prefix = `uploads/${upload.id}`;
      const grants =
        input.format === "cartridge"
          ? {
              cartridge_url: await objects.signUpload(
                `${prefix}/${CARTRIDGE_FILE}`,
                3600,
                input.cartridge_size,
              ),
            }
          : {
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
            };
      return {
        id: upload.id,
        ...grants,
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

        const entry = catalogModel(input.base_model_id) as
          CatalogEntry | undefined;
        const supported =
          input.format === "cartridge"
            ? (entry?.training ?? entry?.architecture)
            : entry?.training;
        if (!supported)
          throw new ControlServiceError(
            "unavailable",
            `This model does not yet have a supported ${input.format === "cartridge" ? "cartridge" : "LoRA"} upload validation profile.`,
          );
        const baseRepository =
          supported.model ?? model.properties.hugging_face_id ?? model.id;
        const baseConfiguration = await loadBaseConfiguration(
          baseRepository,
          supported.revision,
        );
        if (input.format === "cartridge") {
          const cartridgePath = join(directory, CARTRIDGE_FILE);
          const maxTokens =
            model.properties.input_modalities[0]?.supported_inputs
              .max_context_length.value;
          if (!baseConfiguration.hiddenSize || !maxTokens)
            throw new ControlServiceError(
              "unavailable",
              "Cartridge validation is not available for this base model. No model version was published.",
            );

          let cartridgeSize: number;
          try {
            cartridgeSize = await objects.downloadFile(
              `uploads/${id}/${CARTRIDGE_FILE}`,
              cartridgePath,
              { maxBytes: input.cartridge_size, timeoutMs: 600_000 },
            );
          } catch {
            throw new ControlServiceError(
              "conflict",
              "The cartridge file could not be read. Check that it finished uploading.",
            );
          }
          if (cartridgeSize !== input.cartridge_size)
            throw new ControlServiceError(
              "conflict",
              "The uploaded file does not match its declared size.",
            );

          const cartridgeFile = await open(cartridgePath, "r");
          let shape: Awaited<ReturnType<typeof validateCartridgeFile>>;
          try {
            shape = await validateCartridgeFile(cartridgeFile, cartridgeSize, {
              hiddenSize: baseConfiguration.hiddenSize,
              maxTokens,
              ...(baseConfiguration.vocabSize
                ? { vocabSize: baseConfiguration.vocabSize }
                : {}),
            });
          } catch (error) {
            throw new ControlServiceError(
              "conflict",
              `Invalid cartridge: ${error instanceof Error ? error.message : "unreadable file"}`,
            );
          } finally {
            await cartridgeFile.close();
          }

          const key = `cartridges/${id}/${shape.sha256}/${CARTRIDGE_FILE}`;
          await objects.putFile(key, cartridgePath, {
            sha256: shape.sha256,
            sizeBytes: cartridgeSize,
          });
          const version = await uploads.publish(workspaceId, id, {
            format: "cartridge",
            artifact_uri: objects.uri(key),
            sha256: shape.sha256,
            size_bytes: cartridgeSize,
            num_tokens: shape.numTokens,
            hidden_size: shape.hiddenSize,
            placement: "system_prompt_start",
            separator: shape.separator,
            has_slot_token_ids: shape.hasSlotTokenIds,
            validated_base_model_revision: supported.revision,
          });
          await discardInputs(id);
          const task = await records.getTask(workspaceId, input.task);
          if (!task)
            throw new ControlServiceError(
              "not_found",
              "The task was not found.",
            );

          return { task, version };
        }

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
            `Invalid LoRA adapter. Check the base model and checkpoint revision, config, expert coverage, tensor pairs, rank (maximum ${MAX_UPLOADED_ADAPTER_RANK}) and safetensors format.`,
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
