import { createHash } from "node:crypto";
import type { FileHandle } from "node:fs/promises";
import { CARTRIDGE_FORMAT } from "@gradiated/contracts";

const MAX_HEADER_BYTES = 1024 * 1024;
const CHUNK_BYTES = 4 * 1024 * 1024;

export type CartridgeShape = {
  numTokens: number;
  hiddenSize: number;
  separator: string;
  hasSlotTokenIds: boolean;
  sha256: string;
};

type TensorEntry = {
  dtype: string;
  shape: number[];
  data_offsets: [number, number];
};

const fail = (message: string): never => {
  throw new Error(message);
};

const readExactly = async (
  file: FileHandle,
  length: number,
  position: number,
) => {
  const buffer = Buffer.alloc(length);
  const { bytesRead } = await file.read(buffer, 0, length, position);
  if (bytesRead !== length) fail("The cartridge file is truncated.");

  return buffer;
};

const tensor = (header: Record<string, unknown>, name: string) => {
  const entry = header[name] as TensorEntry | undefined;
  if (!entry) return undefined;
  if (
    typeof entry.dtype !== "string" ||
    !Array.isArray(entry.shape) ||
    !entry.shape.every((size) => Number.isSafeInteger(size) && size > 0) ||
    !Array.isArray(entry.data_offsets) ||
    entry.data_offsets.length !== 2 ||
    !entry.data_offsets.every(
      (offset) => Number.isSafeInteger(offset) && offset >= 0,
    )
  )
    fail(`The ${name} tensor header is malformed.`);

  return entry;
};

// A bf16 value is infinite or NaN when all eight exponent bits are set.
const finiteBf16 = (chunk: Buffer) => {
  for (let index = 0; index + 1 < chunk.length; index += 2)
    if ((chunk.readUInt16LE(index) & 0x7f80) === 0x7f80) return false;

  return true;
};

export const validateCartridgeFile = async (
  file: FileHandle,
  sizeBytes: number,
  expected: { hiddenSize: number; maxTokens: number; vocabSize?: number },
): Promise<CartridgeShape> => {
  if (sizeBytes < 8) fail("The cartridge file is too small.");

  const headerLength = Number(
    (await readExactly(file, 8, 0)).readBigUInt64LE(0),
  );
  if (
    headerLength <= 0 ||
    headerLength > MAX_HEADER_BYTES ||
    8 + headerLength > sizeBytes
  )
    fail("The safetensors header length is invalid.");

  let header: Record<string, unknown>;
  try {
    header = JSON.parse(
      (await readExactly(file, headerLength, 8)).toString("utf8"),
    );
  } catch {
    return fail("The safetensors header is not valid JSON.");
  }

  const metadata = (header.__metadata__ ?? {}) as Record<string, unknown>;
  if (
    typeof metadata !== "object" ||
    Array.isArray(metadata) ||
    Object.values(metadata).some((value) => typeof value !== "string")
  )
    fail("Safetensors metadata values must all be text.");
  if (metadata.format !== CARTRIDGE_FORMAT)
    fail(`The cartridge metadata must set format to ${CARTRIDGE_FORMAT}.`);
  if ((metadata.placement ?? "system_prompt_start") !== "system_prompt_start")
    fail("Cartridges can only be placed at the start of the system prompt.");

  const separator = metadata.separator ?? "\n\n";
  if (typeof separator !== "string" || separator.length > 64)
    return fail(
      "The cartridge separator must be text of at most 64 characters.",
    );

  const names = Object.keys(header).filter((name) => name !== "__metadata__");
  if (names.some((name) => name !== "embeddings" && name !== "slot_token_ids"))
    fail("A cartridge may only contain embeddings and slot_token_ids.");

  const embeddings =
    tensor(header, "embeddings") ?? fail("The embeddings tensor is missing.");
  if (embeddings.dtype !== "BF16")
    fail("Cartridge embeddings must be bfloat16.");
  if (embeddings.shape.length !== 2)
    fail("Cartridge embeddings must be two-dimensional.");

  const [numTokens, hiddenSize] = embeddings.shape as [number, number];
  if (hiddenSize !== expected.hiddenSize)
    fail(
      `Cartridge embeddings must be ${expected.hiddenSize} wide for this base model.`,
    );
  if (numTokens >= expected.maxTokens)
    fail(
      `The cartridge has ${numTokens} positions; this base model's context holds ${expected.maxTokens} tokens.`,
    );

  const dataStart = 8 + headerLength;
  const dataLength = sizeBytes - dataStart;
  const [embeddingsStart, embeddingsEnd] = embeddings.data_offsets;
  if (
    embeddingsEnd - embeddingsStart !== numTokens * hiddenSize * 2 ||
    embeddingsEnd > dataLength
  )
    fail("The embeddings tensor size does not match its shape.");

  const slots = tensor(header, "slot_token_ids");
  const ranges = [embeddings, ...(slots ? [slots] : [])]
    .map((entry) => entry.data_offsets)
    .sort((left, right) => left[0] - right[0]);
  if (
    ranges[0]![0] !== 0 ||
    ranges.some(
      ([start, end], index) =>
        end < start || (index > 0 && start !== ranges[index - 1]![1]),
    ) ||
    ranges.at(-1)![1] !== dataLength
  )
    fail(
      "Tensor data must be contiguous and fill the file, as safetensors requires.",
    );

  if (slots) {
    if (
      slots.dtype !== "I64" ||
      slots.shape.length !== 1 ||
      slots.shape[0] !== numTokens
    )
      fail("slot_token_ids must be int64 with one ID per cartridge position.");

    const [slotsStart, slotsEnd] = slots.data_offsets;
    if (slotsEnd - slotsStart !== numTokens * 8 || slotsEnd > dataLength)
      fail("The slot_token_ids tensor size does not match its shape.");

    const ids = await readExactly(file, numTokens * 8, dataStart + slotsStart);
    for (let index = 0; index < numTokens; index++) {
      const id = ids.readBigInt64LE(index * 8);
      if (
        id < 0n ||
        (expected.vocabSize !== undefined && id >= BigInt(expected.vocabSize))
      )
        fail(
          "slot_token_ids must be token IDs in the base model's vocabulary.",
        );
    }
  }

  const embeddingsEndInFile = dataStart + embeddingsEnd;
  for (
    let position = dataStart + embeddingsStart;
    position < embeddingsEndInFile;
    position += CHUNK_BYTES
  )
    if (
      !finiteBf16(
        await readExactly(
          file,
          Math.min(CHUNK_BYTES, embeddingsEndInFile - position),
          position,
        ),
      )
    )
      fail("Cartridge embeddings must be finite.");

  const hash = createHash("sha256");
  for (let position = 0; position < sizeBytes; position += CHUNK_BYTES)
    hash.update(
      await readExactly(
        file,
        Math.min(CHUNK_BYTES, sizeBytes - position),
        position,
      ),
    );

  return {
    numTokens,
    hiddenSize,
    separator,
    hasSlotTokenIds: Boolean(slots),
    sha256: hash.digest("hex"),
  };
};
