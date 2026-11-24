export const ONE_BF16 = 0x3f80;
export const NAN_BF16 = 0x7fc0;

export const cartridgeFile = ({
  tokens = 4,
  hidden = 8,
  metadata = { format: "gradiated.cartridge/1" } as Record<string, string>,
  slots = true as boolean | number[],
  value = ONE_BF16,
  extra = false,
} = {}) => {
  const embeddings = Buffer.alloc(tokens * hidden * 2);
  for (let index = 0; index < tokens * hidden; index++)
    embeddings.writeUInt16LE(value, index * 2);

  const ids = Array.isArray(slots)
    ? slots
    : Array.from({ length: tokens }, (_, index) => 100 + index);
  const slotBytes = Buffer.alloc(ids.length * 8);
  ids.forEach((id, index) => slotBytes.writeBigInt64LE(BigInt(id), index * 8));

  const header: Record<string, unknown> = {
    __metadata__: metadata,
    embeddings: {
      dtype: "BF16",
      shape: [tokens, hidden],
      data_offsets: [0, embeddings.length],
    },
  };
  const parts = [embeddings];
  if (slots) {
    header.slot_token_ids = {
      dtype: "I64",
      shape: [ids.length],
      data_offsets: [embeddings.length, embeddings.length + slotBytes.length],
    };
    parts.push(slotBytes);
  }
  if (extra)
    header.bias = {
      dtype: "BF16",
      shape: [1],
      data_offsets: [
        embeddings.length + slotBytes.length,
        embeddings.length + slotBytes.length + 2,
      ],
    };

  // An odd header length checks that bf16 pairs stay aligned to the tensor.
  let json = JSON.stringify(header);
  if (json.length % 2 === 0) json += " ";
  const length = Buffer.alloc(8);
  length.writeBigUInt64LE(BigInt(json.length));

  return Buffer.concat([
    length,
    Buffer.from(json),
    ...parts,
    ...(extra ? [Buffer.alloc(2)] : []),
  ]);
};
