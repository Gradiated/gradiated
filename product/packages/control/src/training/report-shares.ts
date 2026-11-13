import { createHmac, timingSafeEqual } from "node:crypto";
import { UuidSchema, VERSION_REPORT_FILE } from "@gradiated/contracts";
import { requireWorkspaceMembership } from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import type { ObjectStorage } from "../storage/object-storage.js";
import { createTrainingStore } from "./store.js";
import {
  createVersionFileStore,
  type VersionFileRecord,
} from "./version-file-store.js";
import {
  readVersionFileText,
  signVersionFileDownload,
} from "./version-files.js";

const notFound = (thing: string) =>
  new ControlServiceError("not_found", `The ${thing} was not found.`);

// Prose can end a file name with a full stop.
const referencedNames = (report: string) =>
  new Set(
    report
      .split(/[^A-Za-z0-9._-]+/)
      .flatMap((token) => [token, token.replace(/\.+$/, "")]),
  );

const publicFiles = (files: VersionFileRecord[], report: string | null) => {
  const names = report === null ? new Set<string>() : referencedNames(report);

  return files.filter(
    (file) => file.name === VERSION_REPORT_FILE || names.has(file.name),
  );
};

export const createReportShares = (
  database: ControlDatabase,
  storage?: Pick<ObjectStorage, "read" | "signDownload">,
  secret?: string,
) => {
  const records = createTrainingStore(database);
  const files = createVersionFileStore(database);
  const requireStorage = () => {
    if (!storage)
      throw new ControlServiceError(
        "unavailable",
        "Version file storage is not configured.",
      );

    return storage;
  };
  const sign = (versionId: string) => {
    if (!secret)
      throw new ControlServiceError(
        "unavailable",
        "Public report links are not configured.",
      );

    return createHmac("sha256", secret)
      .update(`report-share:v1:${versionId}`)
      .digest("base64url");
  };
  const verified = (versionId: string, signature: string) => {
    if (!UuidSchema.safeParse(versionId).success) return false;

    const expected = Buffer.from(sign(versionId));
    const actual = Buffer.from(signature);

    return (
      actual.length === expected.length && timingSafeEqual(actual, expected)
    );
  };
  const shared = async (versionId: string, signature: string) => {
    if (!verified(versionId, signature)) throw notFound("report");

    const row = await records.getSharedVersion(versionId);
    if (!row) throw notFound("report");

    const ready = await files.listReady(versionId);
    const reportFile = ready.find((file) => file.name === VERSION_REPORT_FILE);
    const report = reportFile
      ? (await readVersionFileText(requireStorage(), reportFile)).content
      : null;

    return {
      task: row.task.name,
      version: row.version.name,
      baseModelId: row.version.baseModelId,
      createdAt: row.version.createdAt,
      files: publicFiles(ready, report),
    };
  };
  const sharedFile = async (
    versionId: string,
    signature: string,
    fileId: string,
  ) => {
    const report = await shared(versionId, signature);
    const file = report.files.find((candidate) => candidate.id === fileId);
    if (!file) throw notFound("file");

    return file;
  };

  return {
    async get(
      userId: string,
      workspaceId: string,
      taskName: string,
      versionId: string,
    ) {
      const { workspace } = await requireWorkspaceMembership(database, {
        userId,
        workspaceId,
      });
      if (workspace.archivedAt) throw notFound("workspace");
      const task = await records.getTask(workspaceId, taskName);
      if (!task) throw notFound("task");
      const version = await records.findVersion(task.id, versionId);
      if (!version) throw notFound("version");

      return { versionId: version.id, signature: sign(version.id) };
    },

    shared,

    async sharedContent(versionId: string, signature: string, fileId: string) {
      return readVersionFileText(
        requireStorage(),
        await sharedFile(versionId, signature, fileId),
      );
    },

    async sharedDownload(versionId: string, signature: string, fileId: string) {
      return signVersionFileDownload(
        requireStorage(),
        await sharedFile(versionId, signature, fileId),
      );
    },
  };
};
