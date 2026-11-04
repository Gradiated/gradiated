import {
  CreateTaskVersionFileSchema,
  MAX_VERSION_FILE_CONTENT_BYTES,
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
  type VersionFileRecord,
} from "./version-file-store.js";

const UPLOAD_SECONDS = 3600;
const DOWNLOAD_SECONDS = 300;
const TEXT_FILE = /\.(md|markdown|csv|tsv|json|jsonl|txt)$/i;

const notFound = (thing: string) =>
  new ControlServiceError("not_found", `The ${thing} was not found.`);

export const createVersionFiles = (
  database: ControlDatabase,
  storage?: Pick<
    ObjectStorage,
    "signUpload" | "signDownload" | "head" | "read" | "delete"
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

    const version = await records.getVersion(task.id, versionId);
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
  const readyFile = async (versionId: string, fileId: string) => {
    const file = await files.get(versionId, fileId);
    if (!file || file.status !== "ready") throw notFound("file");

    return file;
  };
  const discard = async (stale: VersionFileRecord[]) => {
    if (!stale.length) return;

    try {
      await requireStorage().delete(stale.map(versionFileKey));
    } catch {
      // Orphaned objects are unreachable once their rows are gone.
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
          versionFileKey(file),
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
      if (!file) throw notFound("file");
      if (file.status === "ready") return file;

      let sizeBytes: number | undefined;
      try {
        sizeBytes = (await objects.head(versionFileKey(file))).sizeBytes;
      } catch {
        throw new ControlServiceError(
          "conflict",
          "The file has not been uploaded yet.",
        );
      }
      if (sizeBytes !== file.sizeBytes)
        throw new ControlServiceError(
          "conflict",
          "The uploaded file size does not match the declared size.",
        );

      const { file: ready, replaced } = await files.complete(file);
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

      const bytes = await requireStorage().read(versionFileKey(file), {
        maxBytes: MAX_VERSION_FILE_CONTENT_BYTES,
        timeoutMs: 10_000,
      });

      return {
        name: file.name,
        content_type: file.contentType,
        content: new TextDecoder("utf-8", { fatal: true }).decode(bytes),
      };
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
      if (!file) throw notFound("file");

      await files.delete(file.id);
      await discard([file]);
    },
  };
};
