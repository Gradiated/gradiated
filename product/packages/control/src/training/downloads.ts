import type { ObjectStorage } from "../storage/object-storage.js";
import { ControlServiceError } from "../errors.js";

export type AdapterDownloads = {
  sign(
    uri: string,
    runId: string,
    sizeBytes: number,
    sha256: string,
  ): Promise<{ url: string; expires_at: string }>;
};

export const createAdapterDownloads = (
  storage:
    | Pick<ObjectStorage, "bucket" | "head" | "checksum" | "signDownload">
    | undefined,
): AdapterDownloads => {
  return {
    async sign(uri, runId, sizeBytes, sha256) {
      const bucket = storage?.bucket;
      const prefix = `s3://${bucket}/runs/${runId}/`;
      const key = uri.slice(`s3://${bucket}/`.length);
      if (
        !storage ||
        !bucket ||
        !uri.startsWith(prefix) ||
        !/^[a-zA-Z0-9_./-]+$/.test(key) ||
        key.split("/").some((part) => part === ".." || part === ".") ||
        !key.endsWith(".tar.gz")
      )
        throw new ControlServiceError(
          "unavailable",
          "The adapter archive is unavailable.",
        );

      try {
        const object = await storage.head(key, true);
        if (object.sizeBytes !== sizeBytes)
          throw new Error("Adapter size mismatch.");

        if (!object.versionId || object.versionId === "null")
          throw new Error("Adapter archive requires versioned storage.");
        if (object.sha256) {
          if (object.sha256 !== sha256)
            throw new Error("Adapter checksum mismatch.");
        } else {
          const checksum = await storage.checksum(key, {
            versionId: object.versionId,
            maxBytes: sizeBytes,
          });
          if (checksum.sizeBytes !== sizeBytes || checksum.sha256 !== sha256)
            throw new Error("Adapter checksum mismatch.");
        }

        const expiresAt = new Date(Date.now() + 300_000);
        const url = await storage.signDownload(key, {
          versionId: object.versionId,
          expiresIn: 300,
          filename: "adapter.tar.gz",
          contentType: "application/gzip",
        });
        return { url, expires_at: expiresAt.toISOString() };
      } catch {
        throw new ControlServiceError(
          "unavailable",
          "The adapter archive could not be downloaded. Please try again.",
        );
      }
    },
  };
};
