import {
  CreateTaskVersionFileSchema,
  MAX_VERSION_FILE_CONTENT_BYTES,
  WORKLOAD_BENCHMARK_FILE,
  type CreateTaskVersionFile,
} from "@gradiated/contracts";
import {
  requireWorkspaceEditor,
  requireWorkspaceMembership,
} from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import type { ObjectStorage } from "../storage/object-storage.js";
import { createTrainingStore } from "./store.js";
import {
  createVersionFileStore,
  versionFileKey,
  versionFileUploadKey,
  type VersionFileRecord,
} from "./version-file-store.js";
import {
  MAX_BENCHMARK_BYTES,
  parseWorkloadBenchmark,
} from "./workload-benchmarks.js";

const UPLOAD_SECONDS = 3600;
const DOWNLOAD_SECONDS = 300;
const TEXT_FILE = /\.(md|markdown|csv|tsv|json|jsonl|txt)$/i;

// The task list shows a benchmark in place of automatic stats, so an
// unreadable one is refused here instead of silently ignored later. It reads
// the exact object version that complete() then publishes.
const requireValidBenchmark = async (
  objects: Pick<ObjectStorage, "read">,
  file: VersionFileRecord,
  versionId: string,
) => {
  const invalid = () =>
    new ControlServiceError(
      "conflict",
      `${WORKLOAD_BENCHMARK_FILE} must be a valid workload benchmark.`,
    );
  if (file.sizeBytes > MAX_BENCHMARK_BYTES) throw invalid();
  let bytes: Uint8Array;
  try {
    bytes = await objects.read(versionFileUploadKey(file), {
      maxBytes: MAX_BENCHMARK_BYTES,
      timeoutMs: 5_000,
      versionId,
    });
  } catch (error) {
    throw new ControlServiceError(
      "unavailable",
      "The benchmark could not be checked. Try again shortly.",
      error,
    );
  }
  let parsed: ReturnType<typeof parseWorkloadBenchmark> | undefined;
  try {
    parsed = parseWorkloadBenchmark(bytes);
  } catch {
    parsed = undefined;
  }
  if (!parsed?.success) throw invalid();
};

const notFound = (thing: string) =>
  new ControlServiceError("not_found", `The ${thing} was not found.`);

export const createVersionFiles = (
  database: ControlDatabase,
  storage?: Pick<
    ObjectStorage,
    "signUpload" | "signDownload" | "head" | "read" | "delete" | "copy"
  >,
) => {
  const files = createVersionFileStore(database);
  const records = createTrainingStore(database);
  const requireStorage = () => {
    if (!storage)
      throw new ControlServiceError(
        "unavailable",
        "Version file storage is not configured.",
      );

    return storage;
  };
  const findVersion = async (
    workspaceId: string,
    taskName: string,
    versionId: string,
  ) => {
    const task = await records.getTask(workspaceId, taskName);
    if (!task) throw notFound("task");

    const version = await records.findVersion(task.id, versionId);
    if (!version) throw notFound("version");

    return version;
  };
  const member = async (userId: string, workspaceId: string) => {
    const { workspace } = await requireWorkspaceMembership(database, {
      userId,
      workspaceId,
    });
    if (workspace.archivedAt) throw notFound("workspace");
  };
  // A ready file's name is unique within its version.
  const readyFile = async (versionId: string, reference: string) => {
    const file =
      (await files.get(versionId, reference)) ??
      (await files.getReadyByName(versionId, reference));
    if (!file || file.status !== "ready") throw notFound("file");

    return file;
  };
  const discard = async (stale: VersionFileRecord[]) => {
    if (!stale.length) return;

    try {
      await requireStorage().delete(
        stale.flatMap((file) => [
          versionFileKey(file),
          versionFileUploadKey(file),
        ]),
      );
    } catch {
      // Retained tombstones let artifact cleanup retry after storage failures.
    }
  };

  return {
    async list(
      userId: string,
      workspaceId: string,
      taskName: string,
      versionId: string,
    ) {
      await member(userId, workspaceId);
      const version = await findVersion(workspaceId, taskName, versionId);

      return files.listReady(version.id);
    },

    async create(
      userId: string,
      workspaceId: string,
      taskName: string,
      versionId: string,
      value: CreateTaskVersionFile,
    ) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const objects = requireStorage();
      const version = await findVersion(workspaceId, taskName, versionId);
      const input = CreateTaskVersionFileSchema.parse(value);
      const file = await files.create(workspaceId, version.id, input);

      return {
        id: file.id,
        upload_url: await objects.signUpload(
          versionFileUploadKey(file),
          UPLOAD_SECONDS,
          file.sizeBytes,
        ),
        expires_at: new Date(
          file.createdAt.getTime() + UPLOAD_SECONDS * 1000,
        ).toISOString(),
      };
    },

    async complete(
      userId: string,
      workspaceId: string,
      taskName: string,
      versionId: string,
      fileId: string,
    ) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const objects = requireStorage();
      const version = await findVersion(workspaceId, taskName, versionId);
      const file = await files.get(version.id, fileId);
      if (!file || file.status === "deleted") throw notFound("file");
      if (file.status === "ready") return file;

      const { file: ready, replaced } = await files.complete(file, async () => {
        if (Date.now() - file.createdAt.getTime() >= UPLOAD_SECONDS * 1000)
          throw new ControlServiceError(
            "conflict",
            "This upload has expired. Start a new upload.",
          );

        let object: Awaited<ReturnType<ObjectStorage["head"]>>;
        try {
          object = await objects.head(versionFileUploadKey(file));
        } catch (error) {
          if (
            error &&
            typeof error === "object" &&
            "name" in error &&
            error.name === "NotFound"
          )
            throw new ControlServiceError(
              "conflict",
              "The file has not been uploaded yet.",
            );

          throw new ControlServiceError(
            "unavailable",
            "Version file storage is unavailable. Try again shortly.",
            error,
          );
        }
        if (object.sizeBytes !== file.sizeBytes)
          throw new ControlServiceError(
            "conflict",
            "The uploaded file size does not match the declared size.",
          );
        if (!object.versionId || object.versionId === "null")
          throw new ControlServiceError(
            "unavailable",
            "Version file storage must have bucket versioning enabled.",
          );
        if (file.name === WORKLOAD_BENCHMARK_FILE)
          await requireValidBenchmark(objects, file, object.versionId);

        try {
          await objects.copy(
            versionFileUploadKey(file),
            versionFileKey(file),
            object.versionId,
          );
        } catch (error) {
          throw new ControlServiceError(
            "unavailable",
            "The file could not be published. Try again shortly.",
            error,
          );
        }
      });
      await discard(replaced);

      return ready;
    },

    async content(
      userId: string,
      workspaceId: string,
      taskName: string,
      versionId: string,
      fileId: string,
    ) {
      await member(userId, workspaceId);
      const version = await findVersion(workspaceId, taskName, versionId);
      const file = await readyFile(version.id, fileId);
      if (!TEXT_FILE.test(file.name))
        throw new ControlServiceError(
          "conflict",
          "Only text files can be read inline. Download this file instead.",
        );
      if (file.sizeBytes > MAX_VERSION_FILE_CONTENT_BYTES)
        throw new ControlServiceError(
          "conflict",
          "The file is too large to read inline. Download it instead.",
        );

      let bytes: Uint8Array;
      try {
        bytes = await requireStorage().read(versionFileKey(file), {
          maxBytes: MAX_VERSION_FILE_CONTENT_BYTES,
          timeoutMs: 10_000,
        });
      } catch (error) {
        throw new ControlServiceError(
          "unavailable",
          "The file could not be read. Try again shortly.",
          error,
        );
      }

      let content: string;
      try {
        content = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      } catch {
        throw new ControlServiceError(
          "conflict",
          "The file is not valid UTF-8. Download it instead.",
        );
      }

      return { name: file.name, content_type: file.contentType, content };
    },

    async download(
      userId: string,
      workspaceId: string,
      taskName: string,
      versionId: string,
      fileId: string,
    ) {
      await member(userId, workspaceId);
      const version = await findVersion(workspaceId, taskName, versionId);
      const file = await readyFile(version.id, fileId);
      const url = await requireStorage().signDownload(versionFileKey(file), {
        expiresIn: DOWNLOAD_SECONDS,
        filename: file.name,
        contentType: file.contentType,
      });

      return {
        url,
        expires_at: new Date(
          Date.now() + DOWNLOAD_SECONDS * 1000,
        ).toISOString(),
      };
    },

    async remove(
      userId: string,
      workspaceId: string,
      taskName: string,
      versionId: string,
      fileId: string,
    ) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const version = await findVersion(workspaceId, taskName, versionId);
      const file = await files.get(version.id, fileId);
      if (!file || file.status === "deleted") throw notFound("file");

      await files.markDeleted(file);
      await discard([file]);
    },
  };
};
