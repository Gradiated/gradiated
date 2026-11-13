import {
  createCipheriv,
  createDecipheriv,
  createHash,
  randomBytes,
} from "node:crypto";

export interface CacheStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string, ttlSeconds: number): Promise<void>;
  delete(key: string): Promise<void>;
}

export type CacheKind = "identity" | "inference-key";

export type CredentialCache = ReturnType<typeof createCredentialCache>;

// A slow cache must not hold up a request that the API can answer directly.
const CACHE_TIMEOUT_MS = 250;

const withTimeout = <Value>(operation: Promise<Value>): Promise<Value> =>
  Promise.race([
    operation,
    new Promise<never>((_, reject) =>
      setTimeout(
        () => reject(new Error("The cache timed out.")),
        CACHE_TIMEOUT_MS,
      ).unref(),
    ),
  ]);

const derive = (purpose: string, kind: CacheKind, credential: string) =>
  createHash("sha256")
    .update(`gradiated-mcp/${purpose}/${kind}\0`)
    .update(credential)
    .digest();

// Entries are named and encrypted with keys derived from the credential, so the cache alone reveals nothing.
export const createCredentialCache = (
  store: CacheStore | undefined,
  onResult: (result: "hit" | "miss" | "error") => void = () => undefined,
) => {
  const entryKey = (kind: CacheKind, credential: string) =>
    `mcp:v1:${kind}:${derive("name", kind, credential).toString("base64url")}`;

  const read = async (
    kind: CacheKind,
    credential: string,
  ): Promise<unknown> => {
    if (!store) return undefined;

    try {
      const stored = await withTimeout(store.get(entryKey(kind, credential)));
      if (!stored) {
        onResult("miss");
        return undefined;
      }

      const bytes = Buffer.from(stored, "base64url");
      const decipher = createDecipheriv(
        "aes-256-gcm",
        derive("key", kind, credential),
        bytes.subarray(0, 12),
      );
      decipher.setAuthTag(bytes.subarray(12, 28));
      const value: unknown = JSON.parse(
        Buffer.concat([
          decipher.update(bytes.subarray(28)),
          decipher.final(),
        ]).toString("utf8"),
      );
      onResult("hit");

      return value;
    } catch {
      onResult("error");
      return undefined;
    }
  };

  const write = async (
    kind: CacheKind,
    credential: string,
    value: unknown,
    ttlSeconds: number,
  ) => {
    if (!store || ttlSeconds < 1) return;

    const iv = randomBytes(12);
    const cipher = createCipheriv(
      "aes-256-gcm",
      derive("key", kind, credential),
      iv,
    );
    const encrypted = Buffer.concat([
      cipher.update(JSON.stringify(value), "utf8"),
      cipher.final(),
    ]);
    const stored = Buffer.concat([iv, cipher.getAuthTag(), encrypted]);

    await withTimeout(
      store.set(
        entryKey(kind, credential),
        stored.toString("base64url"),
        Math.floor(ttlSeconds),
      ),
    ).catch(() => onResult("error"));
  };

  const remove = async (kind: CacheKind, credential: string) => {
    if (!store) return;

    await withTimeout(store.delete(entryKey(kind, credential))).catch(() =>
      onResult("error"),
    );
  };

  return { read, write, remove };
};
