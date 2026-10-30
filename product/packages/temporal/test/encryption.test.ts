import { randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";
import {
  defaultPayloadConverter,
  ApplicationFailure,
  type Payload,
} from "@temporalio/common";
import {
  loadDataConverter,
  decodeFailure,
  encodeErrorToFailure,
  encodeToPayload,
  decodeOptionalSinglePayload,
} from "@temporalio/common/internal/internal-non-workflow";
import { temporal } from "@temporalio/proto";
import { describe, expect, it } from "vitest";
import { createDataConverter, EncryptionCodec } from "../src/index.js";

const sourceFailureConverter = fileURLToPath(
  new URL("../src/failure-converter.ts", import.meta.url),
);

const newKey = () => randomBytes(32).toString("base64");
const secret = "customer prompt: the launch code is 0000";

const jsonPayload = (value: unknown): Payload =>
  defaultPayloadConverter.toPayload(value);

const valuesOf = (payloads: Payload[]): unknown[] =>
  payloads.map((payload) => defaultPayloadConverter.fromPayload(payload));

const bytesOf = (payloads: Payload[]): string =>
  Buffer.concat(
    payloads.map((payload) =>
      temporal.api.common.v1.Payload.encode(payload).finish(),
    ),
  ).toString("latin1");

describe("EncryptionCodec", () => {
  it("round-trips payloads without the plaintext reaching the wire", async () => {
    const codec = await EncryptionCodec.create({
      currentKeyId: "a",
      keys: { a: newKey() },
    });
    const encoded = await codec.encode([
      jsonPayload({ secret }),
      jsonPayload(null),
    ]);

    expect(bytesOf(encoded)).not.toContain(secret);
    expect(bytesOf(encoded)).not.toContain("json/plain");
    expect(valuesOf(await codec.decode(encoded))).toEqual([{ secret }, null]);
  });

  it("encrypts the same payload differently each time", async () => {
    const codec = await EncryptionCodec.create({
      currentKeyId: "a",
      keys: { a: newKey() },
    });
    const [first] = await codec.encode([jsonPayload(secret)]);
    const [second] = await codec.encode([jsonPayload(secret)]);

    expect(first!.data).not.toEqual(second!.data);
  });

  it("decodes history written with a retired key after rotation", async () => {
    const keys = { old: newKey(), new: newKey() };
    const before = await EncryptionCodec.create({
      currentKeyId: "old",
      keys: { old: keys.old },
    });
    const after = await EncryptionCodec.create({ currentKeyId: "new", keys });
    const history = await before.encode([jsonPayload(secret)]);

    expect(valuesOf(await after.decode(history))).toEqual([secret]);
    const [fresh] = await after.encode([jsonPayload(secret)]);
    expect(Buffer.from(fresh!.metadata!["encryption-key-id"]!).toString()).toBe(
      "new",
    );
  });

  it("passes through payloads it did not encrypt", async () => {
    const codec = await EncryptionCodec.create({
      currentKeyId: "a",
      keys: { a: newKey() },
    });
    const plain = [jsonPayload(secret)];

    expect(await codec.decode(plain)).toEqual(plain);
  });

  it.each([
    [
      "an unknown key ID",
      (payload: Payload): Payload => ({
        ...payload,
        metadata: {
          ...payload.metadata,
          "encryption-key-id": Buffer.from("missing"),
        },
      }),
      /Payload key missing is not in the key set/,
    ],
    [
      "tampered ciphertext",
      (payload: Payload): Payload => {
        const data = Buffer.from(payload.data!);
        data[data.length - 1]! ^= 1;
        return { ...payload, data };
      },
      /operation failed/,
    ],
    [
      "a missing key ID",
      (payload: Payload): Payload => ({
        ...payload,
        metadata: { encoding: payload.metadata!.encoding! },
      }),
      /missing its key ID or data/,
    ],
  ])("rejects %s", async (_, corrupt, error) => {
    const codec = await EncryptionCodec.create({
      currentKeyId: "a",
      keys: { a: newKey() },
    });
    const [encoded] = await codec.encode([jsonPayload(secret)]);

    await expect(codec.decode([corrupt(encoded!)])).rejects.toThrow(error);
  });

  it("rejects a payload encrypted under a different key with the same ID", async () => {
    const writer = await EncryptionCodec.create({
      currentKeyId: "a",
      keys: { a: newKey() },
    });
    const reader = await EncryptionCodec.create({
      currentKeyId: "a",
      keys: { a: newKey() },
    });

    await expect(
      reader.decode(await writer.encode([jsonPayload(secret)])),
    ).rejects.toThrow(/operation failed/);
  });

  it.each([
    [{ currentKeyId: "b", keys: { a: newKey() } }, /Payload key b is not in/],
    [
      { currentKeyId: "a", keys: { a: randomBytes(16).toString("base64") } },
      /Payload key a must be 32 bytes/,
    ],
  ])("rejects an invalid key set", async (keys, error) => {
    await expect(EncryptionCodec.create(keys)).rejects.toThrow(error);
  });
});

describe("createDataConverter", () => {
  const load = async () =>
    loadDataConverter({
      ...(await createDataConverter({
        currentKeyId: "a",
        keys: { a: newKey() },
      })),
      failureConverterPath: sourceFailureConverter,
    });

  it("encrypts values", async () => {
    const converter = await load();
    const payload = await encodeToPayload(converter, { secret });

    expect(bytesOf([payload])).not.toContain(secret);
    expect(await decodeOptionalSinglePayload(converter, payload)).toEqual({
      secret,
    });
  });

  it("encrypts failure messages and stack traces", async () => {
    const converter = await load();
    const failure = await encodeErrorToFailure(
      converter,
      ApplicationFailure.create({ message: secret }),
    );
    const wire = temporal.api.failure.v1.Failure.encode(failure).finish();

    expect(Buffer.from(wire).toString("latin1")).not.toContain(secret);
    expect(failure.message).toBe("Encoded failure");
    const decoded = await decodeFailure(converter.payloadCodecs, failure);
    expect(
      converter.failureConverter.failureToError(
        decoded,
        converter.payloadConverter,
      ).message,
    ).toBe(secret);
  });
});
