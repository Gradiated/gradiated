import { webcrypto } from "node:crypto";
import {
  METADATA_ENCODING_KEY,
  ValueError,
  type Payload,
  type PayloadCodec,
} from "@temporalio/common";
import proto from "@temporalio/proto";

const { temporal } = proto;
const encode = (text: string) => new TextEncoder().encode(text);
const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);

const ENCODING = "binary/encrypted";
const METADATA_KEY_ID = "encryption-key-id";
const IV_BYTES = 12;
const KEY_BYTES = 32;

export type PayloadKeys = {
  currentKeyId: string;
  keys: Record<string, string>;
};

export class EncryptionCodec implements PayloadCodec {
  private constructor(
    private readonly keys: ReadonlyMap<string, webcrypto.CryptoKey>,
    private readonly currentKeyId: string,
    private readonly currentKey: webcrypto.CryptoKey,
  ) {}

  static async create({
    currentKeyId,
    keys,
  }: PayloadKeys): Promise<EncryptionCodec> {
    const imported = new Map(
      await Promise.all(
        Object.entries(keys).map(
          async ([keyId, base64]) =>
            [keyId, await importKey(keyId, base64)] as const,
        ),
      ),
    );
    const currentKey = imported.get(currentKeyId);
    if (!currentKey) {
      throw new Error(`Payload key ${currentKeyId} is not in the key set`);
    }
    return new EncryptionCodec(imported, currentKeyId, currentKey);
  }

  async encode(payloads: Payload[]): Promise<Payload[]> {
    return Promise.all(
      payloads.map(async (payload) => ({
        metadata: {
          [METADATA_ENCODING_KEY]: encode(ENCODING),
          [METADATA_KEY_ID]: encode(this.currentKeyId),
        },
        data: await encrypt(
          temporal.api.common.v1.Payload.encode(payload).finish(),
          this.currentKey,
        ),
      })),
    );
  }

  async decode(payloads: Payload[]): Promise<Payload[]> {
    return Promise.all(
      payloads.map(async (payload) => {
        const encoding = payload.metadata?.[METADATA_ENCODING_KEY];
        if (!encoding || decode(encoding) !== ENCODING) {
          return payload;
        }

        const keyIdBytes = payload.metadata?.[METADATA_KEY_ID];
        if (!keyIdBytes || !payload.data) {
          throw new ValueError(
            "Encrypted payload is missing its key ID or data",
          );
        }

        const keyId = decode(keyIdBytes);
        const key = this.keys.get(keyId);
        if (!key) {
          throw new ValueError(`Payload key ${keyId} is not in the key set`);
        }

        return temporal.api.common.v1.Payload.decode(
          await decrypt(payload.data, key),
        );
      }),
    );
  }
}

const importKey = (
  keyId: string,
  base64: string,
): Promise<webcrypto.CryptoKey> => {
  const raw = Buffer.from(base64, "base64");
  if (raw.length !== KEY_BYTES) {
    throw new Error(`Payload key ${keyId} must be ${KEY_BYTES} bytes`);
  }
  return webcrypto.subtle.importKey("raw", raw, "AES-GCM", false, [
    "encrypt",
    "decrypt",
  ]);
};

const encrypt = async (
  plaintext: Uint8Array,
  key: webcrypto.CryptoKey,
): Promise<Uint8Array> => {
  const iv = webcrypto.getRandomValues(new Uint8Array(IV_BYTES));
  const ciphertext = await webcrypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    plaintext,
  );
  return Buffer.concat([iv, new Uint8Array(ciphertext)]);
};

const decrypt = async (
  data: Uint8Array,
  key: webcrypto.CryptoKey,
): Promise<Uint8Array> =>
  new Uint8Array(
    await webcrypto.subtle.decrypt(
      { name: "AES-GCM", iv: data.subarray(0, IV_BYTES) },
      key,
      data.subarray(IV_BYTES),
    ),
  );
