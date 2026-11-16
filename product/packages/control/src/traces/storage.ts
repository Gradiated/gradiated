import {
  DeleteObjectsCommand,
  GetObjectCommand,
  ListObjectsV2Command,
  S3Client,
} from "@aws-sdk/client-s3";
import { ControlServiceError } from "../errors.js";

export interface ContentStore {
  list(
    prefix: string,
    options?: {
      cursor?: string | undefined;
      delimiter?: string | undefined;
      limit?: number;
    },
  ): Promise<{
    keys: string[];
    prefixes: string[];
    modifiedAt?: Record<string, string>;
    cursor?: string | undefined;
  }>;
  read(
    key: string,
    range?: { offset: number; length: number },
  ): Promise<Uint8Array>;
  delete(keys: string[]): Promise<void>;
}
/**
 * The largest stored object the API reads: one generation record, which the
 * collector caps at 96 MiB, or one manifest.
 */
export const MAX_RECORD_BYTES = 96 * 1024 * 1024;

export const createContentStore = (bucket: string): ContentStore => {
  const client = new S3Client({ maxAttempts: 3 });
  const send = <T>(operation: Promise<T>): Promise<T> =>
    operation.catch(() => {
      throw new ControlServiceError(
        "unavailable",
        "Generation content storage is unavailable.",
      );
    });
  return {
    async list(prefix, options = {}) {
      const page = await send(
        client.send(
          new ListObjectsV2Command({
            Bucket: bucket,
            Prefix: prefix,
            Delimiter: options.delimiter,
            ContinuationToken: options.cursor,
            MaxKeys: options.limit ?? 100,
          }),
          { abortSignal: AbortSignal.timeout(10_000) },
        ),
      );
      return {
        keys: (page.Contents ?? []).flatMap((row) =>
          row.Key ? [row.Key] : [],
        ),
        prefixes: (page.CommonPrefixes ?? []).flatMap((row) =>
          row.Prefix ? [row.Prefix] : [],
        ),
        modifiedAt: Object.fromEntries(
          (page.Contents ?? []).flatMap((row) =>
            row.Key && row.LastModified
              ? [[row.Key, row.LastModified.toISOString()]]
              : [],
          ),
        ),
        cursor: page.NextContinuationToken,
      };
    },
    async read(key, range) {
      const response = await send(
        client.send(
          new GetObjectCommand({
            Bucket: bucket,
            Key: key,
            ...(range
              ? {
                  Range: `bytes=${range.offset}-${range.offset + range.length - 1}`,
                }
              : {}),
          }),
          { abortSignal: AbortSignal.timeout(10_000) },
        ),
      );
      const limit = MAX_RECORD_BYTES;
      if (!response.Body || (response.ContentLength ?? 0) > limit)
        throw new ControlServiceError(
          "unavailable",
          "Generation content exceeds the read limit.",
        );
      const reader = response.Body.transformToWebStream().getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      try {
        while (true) {
          const chunk = await send(reader.read());
          if (chunk.done) break;
          size += chunk.value.length;
          if (size > limit)
            throw new ControlServiceError(
              "unavailable",
              "Generation content exceeds the read limit.",
            );
          chunks.push(chunk.value);
        }
      } finally {
        await reader.cancel();
      }
      return Buffer.concat(chunks, size);
    },
    async delete(keys) {
      if (!keys.length) return;
      const result = await send(
        client.send(
          new DeleteObjectsCommand({
            Bucket: bucket,
            Delete: { Objects: keys.map((Key) => ({ Key })), Quiet: true },
          }),
          { abortSignal: AbortSignal.timeout(10_000) },
        ),
      );
      if (result.Errors?.length)
        throw new ControlServiceError(
          "unavailable",
          "Generation content deletion will be retried.",
        );
    },
  };
};
