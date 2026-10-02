import { createHash } from "node:crypto";
import { z } from "zod";
import { EvaluationResultsSchema } from "@gradiated/contracts";
import type { ObjectStorage } from "../storage/object-storage.js";
import { ControlServiceError } from "../errors.js";

export type AdapterDownloads = {
  results?: (runId: string) => Promise<z.infer<typeof EvaluationResultsSchema>>;
  sign(
    uri: string,
    runId: string,
    sizeBytes: number,
    sha256: string,
  ): Promise<{ url: string; expires_at: string }>;
};

export const createAdapterDownloads = (
  storage:
    | Pick<
        ObjectStorage,
        "bucket" | "head" | "checksum" | "signDownload" | "read"
      >
    | undefined,
): AdapterDownloads => {
  return {
    async results(runId) {
      if (!storage)
        throw new ControlServiceError(
          "unavailable",
          "Evaluation storage is not configured.",
        );

      try {
        const prefix = `runs/${runId}/evaluation/`;
        const manifest = z
          .object({
            key: z.string(),
            size_bytes: z
              .number()
              .int()
              .positive()
              .max(8 * 1024 * 1024),
            sha256: z.string().regex(/^[0-9a-f]{64}$/),
          })
          .parse(
            JSON.parse(
              Buffer.from(
                await storage.read(`${prefix}result.json`, {
                  maxBytes: 4096,
                  timeoutMs: 10_000,
                }),
              ).toString("utf8"),
            ),
          );
        if (
          !manifest.key.startsWith(prefix) ||
          manifest.key.split("/").some((part) => part === ".." || part === ".")
        )
          throw new Error("Invalid evaluation artifact.");

        const bytes = await storage.read(manifest.key, {
          maxBytes: manifest.size_bytes,
          timeoutMs: 10_000,
        });
        if (
          bytes.length !== manifest.size_bytes ||
          createHash("sha256").update(bytes).digest("hex") !== manifest.sha256
        )
          throw new Error("Evaluation integrity check failed.");

        return EvaluationResultsSchema.parse(
          JSON.parse(Buffer.from(bytes).toString("utf8")),
        );
      } catch {
        throw new ControlServiceError(
          "unavailable",
          "Evaluation results could not be loaded. Please try again.",
        );
      }
    },
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
