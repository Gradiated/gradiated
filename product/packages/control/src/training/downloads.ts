import { createHash } from "node:crypto";
import { z } from "zod";
import {
  AdapterWeightsSchema,
  CARTRIDGE_FILE,
  EvaluationResultsSchema,
  type AdapterWeights,
} from "@gradiated/contracts";
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
  weights?(
    uri: string,
    runId: string,
    sizeBytes: number,
    sha256: string,
  ): Promise<AdapterWeights>;
};

// Bump when the summary changes so cached summaries are recomputed.
const WEIGHTS_VERSION = "v1";
// Bounds the one-time CPU cost of a summary; uploads are capped at 512 MiB.
const MAX_SUMMARY_BYTES = 1024 * 1024 * 1024;

export const createAdapterDownloads = (
  storage:
    | Pick<
        ObjectStorage,
        | "bucket"
        | "head"
        | "checksum"
        | "signDownload"
        | "read"
        | "stream"
        | "put"
      >
    | undefined,
): AdapterDownloads => {
  const archiveKey = (uri: string, runId: string) => {
    const bucket = storage?.bucket;
    const key = uri.slice(`s3://${bucket}/`.length);
    if (
      !storage ||
      !bucket ||
      !uri.startsWith(`s3://${bucket}/`) ||
      !/^[a-zA-Z0-9_./-]+$/.test(key) ||
      key.split("/").some((part) => part === ".." || part === ".")
    )
      return undefined;
    if (key.startsWith(`runs/${runId}/`) && key.endsWith(".tar.gz"))
      return {
        storage,
        key,
        filename: "adapter.tar.gz",
        contentType: "application/gzip",
      };
    if (
      key.startsWith(`cartridges/${runId}/`) &&
      key.endsWith(`/${CARTRIDGE_FILE}`)
    )
      return {
        storage,
        key,
        filename: CARTRIDGE_FILE,
        contentType: "application/octet-stream",
      };

    return undefined;
  };
  const inFlight = new Map<string, Promise<AdapterWeights>>();
  // One summary at a time per process: each one streams and decodes a whole
  // adapter, and requests for the same archive share the first computation.
  let queue: Promise<unknown> = Promise.resolve();

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
      const archive = archiveKey(uri, runId);
      if (!archive)
        throw new ControlServiceError(
          "unavailable",
          "The adapter archive is unavailable.",
        );
      const { storage, key } = archive;

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
          filename: archive.filename,
          contentType: archive.contentType,
        });
        return { url, expires_at: expiresAt.toISOString() };
      } catch {
        throw new ControlServiceError(
          "unavailable",
          "The adapter archive could not be downloaded. Please try again.",
        );
      }
    },
    weights(uri, runId, sizeBytes, sha256) {
      const archive = archiveKey(uri, runId);
      if (
        !archive ||
        archive.filename !== "adapter.tar.gz" ||
        !/^[0-9a-f]{64}$/.test(sha256)
      )
        return Promise.reject(
          new ControlServiceError(
            "unavailable",
            "The adapter archive is unavailable.",
          ),
        );
      const { storage, key } = archive;
      const cacheKey = `runs/${runId}/output/adapter-weights/${sha256}.${WEIGHTS_VERSION}.json`;
      const pending = inFlight.get(cacheKey);
      if (pending) return pending;

      const compute = async () => {
        try {
          return AdapterWeightsSchema.parse(
            JSON.parse(
              Buffer.from(
                await storage.read(cacheKey, {
                  maxBytes: 16 * 1024 * 1024,
                  timeoutMs: 10_000,
                }),
              ).toString("utf8"),
            ),
          );
        } catch {
          // Not cached yet, or cached by an incompatible build: recompute.
        }
        const summary = await (queue = queue
          .catch(() => undefined)
          .then(async () => {
            const object = await storage.head(key);
            if (object.sizeBytes !== sizeBytes || sizeBytes > MAX_SUMMARY_BYTES)
              throw new Error("Adapter size mismatch.");
            if (!object.versionId || object.versionId === "null")
              throw new Error("Adapter archive requires versioned storage.");

            const hash = createHash("sha256");
            let received = 0;
            const verified = async function* (
              chunks: AsyncIterable<Uint8Array>,
            ) {
              for await (const chunk of chunks) {
                hash.update(chunk);
                received += chunk.length;
                yield chunk;
              }
            };
            // Loaded on first use so API startup does not pay for it.
            const { summarizeAdapterArchive } =
              await import("./adapter-weights.js");
            const result = await summarizeAdapterArchive(
              verified(
                storage.stream(key, {
                  versionId: object.versionId,
                  maxBytes: sizeBytes,
                  timeoutMs: 300_000,
                }),
              ),
            );
            if (received !== sizeBytes || hash.digest("hex") !== sha256)
              throw new Error("Adapter checksum mismatch.");

            return result;
          }) as Promise<AdapterWeights>);
        try {
          await storage.put(
            cacheKey,
            Buffer.from(JSON.stringify(summary), "utf8"),
          );
        } catch {
          // The summary is still correct; the next request recomputes it.
        }
        return summary;
      };
      const promise = compute()
        .catch(() => {
          throw new ControlServiceError(
            "unavailable",
            "The adapter weights could not be summarized. Please try again.",
          );
        })
        .finally(() => inFlight.delete(cacheKey));
      inFlight.set(cacheKey, promise);
      return promise;
    },
  };
};
