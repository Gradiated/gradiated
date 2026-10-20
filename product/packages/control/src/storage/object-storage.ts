import { createHash } from "node:crypto";
import {
  GetObjectCommand,
  HeadObjectCommand,
  PutObjectCommand,
  PutObjectTaggingCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

export type ObjectReadOptions = {
  maxBytes: number;
  timeoutMs?: number;
  versionId?: string;
};
export type ObjectTags = Readonly<Record<string, string>>;
export type ObjectWriteOptions = { tags?: ObjectTags };
export type ObjectDownloadOptions = {
  expiresIn: number;
  versionId?: string;
  filename?: string;
  contentType?: string;
};

export class ObjectStorage {
  private readonly client: S3Client;

  constructor(readonly bucket: string) {
    this.client = new S3Client({
      maxAttempts: 3,
      requestChecksumCalculation: "WHEN_REQUIRED",
    });
  }

  private consume = async (
    key: string,
    { maxBytes, timeoutMs = 120_000, versionId }: ObjectReadOptions,
    receive: (chunk: Uint8Array) => void,
  ) => {
    const response = await this.client.send(
      new GetObjectCommand({
        Bucket: this.bucket,
        Key: key,
        ...(versionId ? { VersionId: versionId } : {}),
      }),
      { abortSignal: AbortSignal.timeout(timeoutMs) },
    );
    if (!response.Body) throw new Error("Missing object body.");

    const reader = response.Body.transformToWebStream().getReader();
    let sizeBytes = 0;
    try {
      if ((response.ContentLength ?? 0) > maxBytes)
        throw new Error("Object exceeds read limit.");

      for (;;) {
        const chunk = await reader.read();
        if (chunk.done) break;

        sizeBytes += chunk.value.length;
        if (sizeBytes > maxBytes) throw new Error("Object exceeds read limit.");

        receive(chunk.value);
      }
    } finally {
      await reader.cancel();
    }
    return sizeBytes;
  };

  read = async (
    key: string,
    options: ObjectReadOptions,
  ): Promise<Uint8Array> => {
    const chunks: Uint8Array[] = [];
    const sizeBytes = await this.consume(key, options, (chunk) => {
      chunks.push(chunk);
    });
    return Buffer.concat(chunks, sizeBytes);
  };

  checksum = async (key: string, options: ObjectReadOptions) => {
    const hash = createHash("sha256");
    const sizeBytes = await this.consume(key, options, (chunk) => {
      hash.update(chunk);
    });
    return { sha256: hash.digest("hex"), sizeBytes };
  };

  put = async (
    key: string,
    bytes: Uint8Array,
    { tags }: ObjectWriteOptions = {},
  ) => {
    await this.client.send(
      new PutObjectCommand({
        Bucket: this.bucket,
        Key: key,
        Body: bytes,
        ChecksumSHA256: createHash("sha256").update(bytes).digest("base64"),
        ...(tags ? { Tagging: new URLSearchParams(tags).toString() } : {}),
      }),
      { abortSignal: AbortSignal.timeout(120_000) },
    );
  };

  // Replaces the object's whole tag set; S3 lifecycle rules match these tags.
  tag = async (key: string, tags: ObjectTags) => {
    await this.client.send(
      new PutObjectTaggingCommand({
        Bucket: this.bucket,
        Key: key,
        Tagging: {
          TagSet: Object.entries(tags).map(([Key, Value]) => ({ Key, Value })),
        },
      }),
      { abortSignal: AbortSignal.timeout(10_000) },
    );
  };

  head = async (key: string, checksums = false) => {
    const object = await this.client.send(
      new HeadObjectCommand({
        Bucket: this.bucket,
        Key: key,
        ...(checksums ? { ChecksumMode: "ENABLED" } : {}),
      }),
      { abortSignal: AbortSignal.timeout(10_000) },
    );
    return {
      sizeBytes: object.ContentLength,
      versionId: object.VersionId,
      sha256:
        object.ChecksumSHA256 && object.ChecksumType === "FULL_OBJECT"
          ? Buffer.from(object.ChecksumSHA256, "base64").toString("hex")
          : undefined,
    };
  };

  exists = async (key: string) => {
    try {
      await this.head(key);
      return true;
    } catch (error) {
      if ((error as { name?: string }).name === "NotFound") return false;
      throw error;
    }
  };

  signDownload = (key: string, options: ObjectDownloadOptions) =>
    getSignedUrl(
      this.client,
      new GetObjectCommand({
        Bucket: this.bucket,
        Key: key,
        ...(options.versionId ? { VersionId: options.versionId } : {}),
        ...(options.filename
          ? {
              ResponseContentDisposition: `attachment; filename="${options.filename}"`,
            }
          : {}),
        ...(options.contentType
          ? { ResponseContentType: options.contentType }
          : {}),
      }),
      { expiresIn: options.expiresIn },
    );

  signUpload = (key: string, expiresIn: number) =>
    getSignedUrl(
      this.client,
      new PutObjectCommand({ Bucket: this.bucket, Key: key }),
      { expiresIn },
    );

  uri = (key: string) => `s3://${this.bucket}/${key}`;
}
