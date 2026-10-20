import type { ObjectStorage } from "../storage/object-storage.js";
import { sha256 } from "./dataset.js";

export type TrainingArtifact = {
  key: string;
  sha256: string;
  size_bytes: number;
};
// Matched by the bucket lifecycle rule ExpireTrainingInputsAfter90Days
// (infra/modules/registry-secrets/model-artifacts.tf).
export const EXPIRING_TRAINING_INPUT_TAGS = { retention: "90d" } as const;
export type TrainingArtifactWriteOptions = { expiring?: boolean };

export interface TrainingArtifacts {
  put(
    key: string,
    bytes: Uint8Array,
    options?: TrainingArtifactWriteOptions,
  ): Promise<TrainingArtifact>;
  markExpiring(key: string): Promise<void>;
  read(key: string): Promise<Uint8Array>;
  verify(artifact: TrainingArtifact): Promise<void>;
  download(
    artifact: TrainingArtifact,
  ): Promise<TrainingArtifact & { url: string }>;
  upload(key: string): Promise<{ key: string; url: string }>;
  exists(key: string): Promise<boolean>;
  uri(key: string): string;
}

export const createTrainingArtifacts = (
  storage: Pick<
    ObjectStorage,
    "put" | "tag" | "read" | "exists" | "signDownload" | "signUpload" | "uri"
  >,
): TrainingArtifacts => {
  const checkKey = (key: string) => {
    if (
      !/^runs\/[0-9a-f-]{36}\/[a-zA-Z0-9_./-]+$/.test(key) ||
      key.includes("..")
    )
      throw new Error("Invalid training artifact key.");
    return key;
  };
  const read = (key: string) =>
    storage.read(checkKey(key), { maxBytes: 256 * 1024 * 1024 });
  return {
    async put(key, bytes, options = {}) {
      await storage.put(
        checkKey(key),
        bytes,
        options.expiring ? { tags: EXPIRING_TRAINING_INPUT_TAGS } : {},
      );
      return { key, sha256: sha256(bytes), size_bytes: bytes.length };
    },
    async markExpiring(key) {
      await storage.tag(checkKey(key), EXPIRING_TRAINING_INPUT_TAGS);
    },
    read,
    async verify(artifact) {
      const bytes = await read(artifact.key);
      if (
        bytes.length !== artifact.size_bytes ||
        sha256(bytes) !== artifact.sha256
      )
        throw new Error("Training artifact integrity check failed.");
    },
    exists: (key) => storage.exists(checkKey(key)),
    async download(artifact) {
      return {
        ...artifact,
        url: await storage.signDownload(checkKey(artifact.key), {
          expiresIn: 7200,
        }),
      };
    },
    async upload(key) {
      return {
        key,
        url: await storage.signUpload(checkKey(key), 7200),
      };
    },
    uri: (key) => storage.uri(checkKey(key)),
  };
};
