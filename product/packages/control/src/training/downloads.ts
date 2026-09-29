import { createHash } from "node:crypto";
import {
  HeadObjectCommand,
  GetObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
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
  bucket: string | undefined,
): AdapterDownloads => {
  const client = new S3Client({ maxAttempts: 3 });

  return {
    async sign(uri, runId, sizeBytes, sha256) {
      const prefix = `s3://${bucket}/runs/${runId}/`;
      const key = uri.slice(`s3://${bucket}/`.length);
      if (
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
        const object = await client.send(
          new HeadObjectCommand({
            Bucket: bucket,
            Key: key,
            ChecksumMode: "ENABLED",
          }),
          { abortSignal: AbortSignal.timeout(10_000) },
        );
        if (object.ContentLength !== sizeBytes)
          throw new Error("Adapter size mismatch.");

        if (!object.VersionId || object.VersionId === "null")
          throw new Error("Adapter archive requires versioned storage.");
        const expected = Buffer.from(sha256, "hex").toString("base64");
        if (object.ChecksumSHA256 && object.ChecksumType === "FULL_OBJECT") {
          if (object.ChecksumSHA256 !== expected)
            throw new Error("Adapter checksum mismatch.");
        } else {
          const response = await client.send(
            new GetObjectCommand({
              Bucket: bucket,
              Key: key,
              VersionId: object.VersionId,
            }),
            { abortSignal: AbortSignal.timeout(120_000) },
          );
          if (!response.Body) throw new Error("Missing adapter body.");
          const reader = response.Body.transformToWebStream().getReader();
          const digest = createHash("sha256");
          let bytes = 0;
          try {
            while (true) {
              const chunk = await reader.read();
              if (chunk.done) break;
              bytes += chunk.value.length;
              if (bytes > sizeBytes) throw new Error("Adapter size mismatch.");
              digest.update(chunk.value);
            }
          } finally {
            await reader.cancel();
          }
          if (bytes !== sizeBytes || digest.digest("base64") !== expected)
            throw new Error("Adapter checksum mismatch.");
        }

        const expiresAt = new Date(Date.now() + 300_000);
        const url = await getSignedUrl(
          client,
          new GetObjectCommand({
            Bucket: bucket,
            Key: key,
            VersionId: object.VersionId,
            ResponseContentDisposition: 'attachment; filename="adapter.tar.gz"',
            ResponseContentType: "application/gzip",
          }),
          { expiresIn: 300 },
        );
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
