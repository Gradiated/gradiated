import { gzipSync } from "node:zlib";

export type Matrix = { rows: number; columns: number; values: number[] };
export type Entry = {
  name: string;
  matrix: Matrix | Matrix[];
  dtype?: "F32" | "BF16";
};

export const random = (seed: number) => () => {
  seed = (seed * 1_103_515_245 + 12_345) % 2 ** 31;
  return seed / 2 ** 31 - 0.5;
};
export const matrix = (
  rows: number,
  columns: number,
  next: () => number,
): Matrix => ({
  rows,
  columns,
  values: Array.from({ length: rows * columns }, next),
});

const encode = (values: number[], dtype: "F32" | "BF16") => {
  const bytes = Buffer.alloc(values.length * (dtype === "F32" ? 4 : 2));
  values.forEach((value, index) => {
    if (dtype === "F32") bytes.writeFloatLE(value, index * 4);
    else {
      // Truncation is exact for the quarter-step test values.
      const wide = Buffer.alloc(4);
      wide.writeFloatLE(value);
      bytes.writeUInt16LE(wide.readUInt32LE() >>> 16, index * 2);
    }
  });
  return bytes;
};

export const safetensors = (entries: Entry[]) => {
  let offset = 0;
  const header: Record<string, unknown> = { __metadata__: { format: "pt" } };
  const data = entries.map(({ name, matrix, dtype = "F32" }) => {
    const parts = Array.isArray(matrix) ? matrix : [matrix];
    const bytes = encode(
      parts.flatMap((part) => part.values),
      dtype,
    );
    header[name] = {
      dtype,
      shape: Array.isArray(matrix)
        ? [parts.length, parts[0]!.rows, parts[0]!.columns]
        : [matrix.rows, matrix.columns],
      data_offsets: [offset, offset + bytes.length],
    };
    offset += bytes.length;
    return bytes;
  });
  const json = Buffer.from(JSON.stringify(header));
  const size = Buffer.alloc(8);
  size.writeBigUInt64LE(BigInt(json.length));
  return Buffer.concat([size, json, ...data]);
};

export const tarEntry = (name: string, body: Buffer, type = "0") => {
  const header = Buffer.alloc(512);
  header.write(name.slice(0, 100));
  header.write("0000644\0", 100);
  header.write("0000000\0", 108);
  header.write("0000000\0", 116);
  header.write(body.length.toString(8).padStart(11, "0") + "\0", 124);
  header.write("00000000000\0", 136);
  header.fill(32, 148, 156);
  header.write(type, 156);
  header.write("ustar\0", 257);
  header.write("00", 263);
  const checksum = header.reduce((sum, byte) => sum + byte, 0);
  header.write(checksum.toString(8).padStart(6, "0") + "\0 ", 148);
  return Buffer.concat([
    header,
    body,
    Buffer.alloc((512 - (body.length % 512)) % 512),
  ]);
};

export const archive = (...entries: Buffer[]) =>
  gzipSync(Buffer.concat([...entries, Buffer.alloc(1024)]));
