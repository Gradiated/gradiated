import { createGunzip } from "node:zlib";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { setImmediate as nextTurn } from "node:timers/promises";
import { z } from "zod";
import {
  AdapterWeightsSchema,
  type AdapterWeightModule,
  type AdapterWeights,
} from "@gradiated/contracts";

// No ΔW = B·A is materialized: a block's ‖ΔW‖² is trace(BᵢᵀBᵢ · AⱼAⱼᵀ) over binned
// r × r Grams, and ΔW's singular values are √eig(Lᵀ(BᵀB)L) where AAᵀ = LLᵀ.

const HEATMAP_CELLS = 131_072;
const BLOCK_OPERATIONS = 2 ** 28;
const PENDING_GRAM_BYTES = 128 * 1024 * 1024;
const MAX_TENSOR_BYTES = 256 * 1024 * 1024;
const MAX_HEADER_BYTES = 8 * 1024 * 1024;
const MAX_CONFIG_BYTES = 64 * 1024;
const MAX_GRID = 64;
const MAX_SPECTRUM_RANK = 64;

const ConfigSchema = z
  .object({
    r: z.number().int().positive().max(4096),
    lora_alpha: z.number().positive(),
    use_rslora: z.boolean().nullish(),
  })
  .passthrough();

const TensorSchema = z.object({
  dtype: z.string(),
  shape: z.array(z.number().int().positive().max(1_000_000)),
  data_offsets: z.tuple([
    z.number().int().nonnegative(),
    z.number().int().nonnegative(),
  ]),
});

const WIDTH: Record<string, number> = { F16: 2, BF16: 2, F32: 4 };

class ByteReader {
  private chunk: Uint8Array = new Uint8Array(0);
  private offset = 0;

  constructor(private readonly chunks: AsyncIterator<Uint8Array>) {}

  private async fill() {
    while (this.offset >= this.chunk.length) {
      const next = await this.chunks.next();
      if (next.done) return false;

      this.chunk = next.value;
      this.offset = 0;
    }
    return true;
  }

  async read(length: number) {
    const bytes = new Uint8Array(length);
    for (let filled = 0; filled < length;) {
      if (!(await this.fill()))
        throw new Error("The adapter archive is truncated.");

      const take = Math.min(length - filled, this.chunk.length - this.offset);
      bytes.set(this.chunk.subarray(this.offset, this.offset + take), filled);
      this.offset += take;
      filled += take;
    }
    return bytes;
  }

  async skip(length: number) {
    for (let skipped = 0; skipped < length;) {
      if (!(await this.fill()))
        throw new Error("The adapter archive is truncated.");

      const take = Math.min(length - skipped, this.chunk.length - this.offset);
      this.offset += take;
      skipped += take;
    }
  }

  async drain() {
    while (await this.fill()) this.offset = this.chunk.length;
  }
}

let halfTable: Float32Array | undefined;
const halfFloats = () => {
  if (halfTable) return halfTable;

  const table = new Float32Array(65_536);
  for (let bits = 0; bits < 65_536; bits++) {
    const sign = bits & 0x8000 ? -1 : 1;
    const exponent = (bits >> 10) & 0x1f;
    const fraction = bits & 0x3ff;
    table[bits] =
      exponent === 0
        ? sign * 2 ** -14 * (fraction / 1024)
        : exponent === 31
          ? fraction
            ? Number.NaN
            : sign * Number.POSITIVE_INFINITY
          : sign * 2 ** (exponent - 15) * (1 + fraction / 1024);
  }
  return (halfTable = table);
};

export const decodeTensor = (bytes: Uint8Array, dtype: string) => {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (dtype === "F32") {
    const values = new Float32Array(bytes.byteLength / 4);
    for (let index = 0; index < values.length; index++)
      values[index] = view.getFloat32(index * 4, true);
    return values;
  }
  const values = new Float32Array(bytes.byteLength / 2);
  if (dtype === "F16") {
    const table = halfFloats();
    for (let index = 0; index < values.length; index++)
      values[index] = table[view.getUint16(index * 2, true)]!;
  } else {
    const widened = new Uint32Array(values.buffer);
    for (let index = 0; index < values.length; index++)
      widened[index] = view.getUint16(index * 2, true) << 16;
  }
  return values;
};

const bounds = (size: number, bins: number) =>
  Array.from({ length: bins + 1 }, (_, bin) => Math.floor((bin * size) / bins));

// Gram matrices of A's rows over each column bin: Σₖ A[i,k]·A[j,k].
const columnGrams = (
  values: Float32Array,
  rank: number,
  inputs: number,
  bins: number,
) => {
  const grams = new Float64Array(bins * rank * rank);
  const edges = bounds(inputs, bins);
  for (let bin = 0; bin < bins; bin++) {
    const start = edges[bin]!;
    const end = edges[bin + 1]!;
    const offset = bin * rank * rank;
    for (let i = 0; i < rank; i++) {
      const rowI = i * inputs;
      for (let j = i; j < rank; j++) {
        const rowJ = j * inputs;
        let sum = 0;
        for (let k = start; k < end; k++)
          sum += values[rowI + k]! * values[rowJ + k]!;
        grams[offset + i * rank + j] = sum;
        grams[offset + j * rank + i] = sum;
      }
    }
  }
  return grams;
};

// Gram matrices of B's columns over each row bin: Σₖ B[k,i]·B[k,j].
const rowGrams = (
  values: Float32Array,
  outputs: number,
  rank: number,
  bins: number,
) => {
  const grams = new Float64Array(bins * rank * rank);
  const edges = bounds(outputs, bins);
  for (let bin = 0; bin < bins; bin++) {
    const offset = bin * rank * rank;
    for (let row = edges[bin]!; row < edges[bin + 1]!; row++) {
      const base = row * rank;
      for (let i = 0; i < rank; i++) {
        const value = values[base + i]!;
        if (value === 0) continue;

        for (let j = i; j < rank; j++)
          grams[offset + i * rank + j] =
            grams[offset + i * rank + j]! + value * values[base + j]!;
      }
    }
    for (let i = 0; i < rank; i++)
      for (let j = 0; j < i; j++)
        grams[offset + i * rank + j] = grams[offset + j * rank + i]!;
  }
  return grams;
};

const sumBins = (grams: Float64Array, bins: number, rank: number) => {
  const total = new Float64Array(rank * rank);
  for (let bin = 0; bin < bins; bin++)
    for (let index = 0; index < rank * rank; index++)
      total[index] = total[index]! + grams[bin * rank * rank + index]!;
  return total;
};

// Cholesky factor of a positive semi-definite matrix; dependent columns get
// zero, so L·Lᵀ still reproduces the matrix.
const cholesky = (matrix: Float64Array, size: number) => {
  const factor = new Float64Array(size * size);
  let trace = 0;
  for (let i = 0; i < size; i++) trace += Math.abs(matrix[i * size + i]!);
  const floor = (trace / size) * 1e-13;
  for (let j = 0; j < size; j++) {
    let diagonal = matrix[j * size + j]!;
    for (let k = 0; k < j; k++) diagonal -= factor[j * size + k]! ** 2;
    const pivot = diagonal > floor ? Math.sqrt(diagonal) : 0;
    factor[j * size + j] = pivot;
    for (let i = j + 1; i < size; i++) {
      if (!pivot) continue;

      let sum = matrix[i * size + j]!;
      for (let k = 0; k < j; k++)
        sum -= factor[i * size + k]! * factor[j * size + k]!;
      factor[i * size + j] = sum / pivot;
    }
  }
  return factor;
};

export const symmetricEigenvalues = (input: Float64Array, size: number) => {
  const matrix = Float64Array.from(input);
  for (let sweep = 0; sweep < 64; sweep++) {
    let off = 0;
    let total = 0;
    for (let i = 0; i < size; i++)
      for (let j = 0; j < size; j++) {
        const value = matrix[i * size + j]! ** 2;
        total += value;
        if (i !== j) off += value;
      }
    if (off <= total * 1e-28 || off === 0) break;

    for (let p = 0; p < size - 1; p++)
      for (let q = p + 1; q < size; q++) {
        const apq = matrix[p * size + q]!;
        if (Math.abs(apq) < 1e-300) continue;

        const app = matrix[p * size + p]!;
        const aqq = matrix[q * size + q]!;
        const theta = (aqq - app) / (2 * apq);
        const t =
          Math.sign(theta || 1) /
          (Math.abs(theta) + Math.sqrt(theta * theta + 1));
        const c = 1 / Math.sqrt(t * t + 1);
        const s = t * c;
        for (let k = 0; k < size; k++) {
          const akp = matrix[k * size + p]!;
          const akq = matrix[k * size + q]!;
          matrix[k * size + p] = c * akp - s * akq;
          matrix[k * size + q] = s * akp + c * akq;
        }
        for (let k = 0; k < size; k++) {
          const apk = matrix[p * size + k]!;
          const aqk = matrix[q * size + k]!;
          matrix[p * size + k] = c * apk - s * aqk;
          matrix[q * size + k] = s * apk + c * aqk;
        }
      }
  }
  return Array.from({ length: size }, (_, i) => matrix[i * size + i]!);
};

const singularValues = (
  gramA: Float64Array,
  gramB: Float64Array,
  r: number,
) => {
  const factor = cholesky(gramA, r);
  const product = new Float64Array(r * r);
  for (let i = 0; i < r; i++)
    for (let j = 0; j < r; j++) {
      let sum = 0;
      for (let k = 0; k < r; k++) sum += gramB[i * r + k]! * factor[k * r + j]!;
      product[i * r + j] = sum;
    }
  const middle = new Float64Array(r * r);
  for (let i = 0; i < r; i++)
    for (let j = 0; j < r; j++) {
      let sum = 0;
      for (let k = 0; k < r; k++)
        sum += factor[k * r + i]! * product[k * r + j]!;
      middle[i * r + j] = sum;
    }
  return symmetricEigenvalues(middle, r)
    .map((value) => Math.sqrt(Math.max(value, 0)))
    .sort((a, b) => b - a);
};

type Tensor = {
  name: string;
  dtype: string;
  shape: number[];
  start: number;
  end: number;
};
type Side = {
  tensor: Tensor;
  experts: number;
  rank: number;
  features: number;
};
type Pair = {
  key: string;
  module: Folded;
  a: Side;
  b: Side;
  gramsA: (Float64Array | undefined)[];
  gramsB: (Float64Array | undefined)[];
  done: number;
};
type Folded = {
  module: string;
  layer: number | null;
  outputs: number;
  inputs: number;
  rank: number;
  experts: number;
  rows: number;
  columns: number;
  blocks: Float64Array;
  spectrum: number[] | undefined;
};

const loraTensor = (name: string) => {
  const layer =
    /^(?:[a-zA-Z0-9_]+\.)*layers\.(\d+)\.(.+)\.lora_([AB])\.weight$/.exec(name);
  if (layer)
    return {
      layer: Number(layer[1]),
      path: layer[2]!,
      side: layer[3] as "A" | "B",
    };
  const head = /^(?:base_model\.model\.)?lm_head\.lora_([AB])\.weight$/.exec(
    name,
  );
  return head
    ? { layer: null, path: "lm_head", side: head[1] as "A" | "B" }
    : undefined;
};

const side = (tensor: Tensor, kind: "A" | "B"): Side => {
  const [experts, first, second] =
    tensor.shape.length === 3
      ? (tensor.shape as [number, number, number])
      : [1, tensor.shape[0]!, tensor.shape[1]!];
  return kind === "A"
    ? { tensor, experts, rank: first, features: second }
    : { tensor, experts, rank: second, features: first };
};

const plan = (header: Record<string, unknown>, dataBytes: number) => {
  const tensors: Tensor[] = [];
  const sides = new Map<string, { A?: Side; B?: Side }>();
  for (const [name, value] of Object.entries(header)) {
    if (name === "__metadata__") continue;

    const parsed = TensorSchema.parse(value);
    const [start, end] = parsed.data_offsets;
    if (end < start || end > dataBytes)
      throw new Error("Tensor exceeds the safetensors data.");

    const tensor = { name, ...parsed, start, end };
    tensors.push(tensor);
    const lora = loraTensor(name);
    const width = WIDTH[parsed.dtype];
    if (
      !lora ||
      !width ||
      (parsed.shape.length !== 2 && parsed.shape.length !== 3)
    )
      continue;
    if (
      parsed.shape.reduce((size, dimension) => size * dimension, width) !==
      end - start
    )
      throw new Error("Tensor size does not match its shape.");
    if (end - start > MAX_TENSOR_BYTES)
      throw new Error("Adapter tensor is too large to summarize.");

    const key = `${lora.layer ?? "head"}/${lora.path}`;
    const entry = sides.get(key) ?? {};
    entry[lora.side] = side(tensor, lora.side);
    sides.set(key, entry);
  }
  tensors.sort((left, right) => left.start - right.start);

  const pairs: Pair[] = [];
  const folded = new Map<string, Folded>();
  for (const [key, { A, B }] of sides) {
    if (!A || !B || A.rank !== B.rank || A.experts !== B.experts)
      throw new Error("Adapter tensors are not in matching A/B pairs.");

    const [layer, ...rest] = key.split("/");
    const path = rest.join("/");
    const module = path.replace(/\.experts\.\d+\./, ".experts.");
    const foldedKey = `${layer}/${module}`;
    const existing = folded.get(foldedKey);
    if (
      existing &&
      (existing.outputs !== B.features ||
        existing.inputs !== A.features ||
        existing.rank !== A.rank)
    )
      throw new Error("Adapter experts disagree on shape.");

    const target = existing ?? {
      module,
      layer: layer === "head" ? null : Number(layer),
      outputs: B.features,
      inputs: A.features,
      rank: A.rank,
      experts: 0,
      rows: 0,
      columns: 0,
      blocks: new Float64Array(0),
      spectrum: undefined,
    };
    target.experts += A.experts;
    folded.set(foldedKey, target);
    pairs.push({
      key,
      module: target,
      a: A,
      b: B,
      gramsA: [],
      gramsB: [],
      done: 0,
    });
  }
  if (!pairs.length) throw new Error("The adapter contains no LoRA tensors.");

  // One grid for every module, bounded by response size, arithmetic and the
  // Grams that unpaired tensors may hold while the stream reaches their pair.
  const weight = pairs.reduce(
    (sum, pair) => sum + pair.a.experts * pair.a.rank ** 2,
    0,
  );
  const grid = Math.max(
    1,
    Math.min(
      MAX_GRID,
      Math.floor(Math.sqrt(HEATMAP_CELLS / folded.size)),
      Math.floor(Math.sqrt(BLOCK_OPERATIONS / weight)),
      Math.floor(PENDING_GRAM_BYTES / (weight * 2 * 8)),
    ),
  );
  for (const module of folded.values()) {
    module.rows = Math.min(grid, module.outputs);
    module.columns = Math.min(grid, module.inputs);
    module.blocks = new Float64Array(module.rows * module.columns);
  }
  const owners = new Map<string, { pair: Pair; kind: "A" | "B" }>();
  for (const pair of pairs) {
    owners.set(pair.a.tensor.name, { pair, kind: "A" });
    owners.set(pair.b.tensor.name, { pair, kind: "B" });
  }
  return { tensors, owners, folded };
};

const finishExpert = (pair: Pair, expert: number) => {
  const gramsA = pair.gramsA[expert]!;
  const gramsB = pair.gramsB[expert]!;
  const { rows, columns, rank } = pair.module;
  const square = rank * rank;
  for (let row = 0; row < rows; row++)
    for (let column = 0; column < columns; column++) {
      let sum = 0;
      const offsetB = row * square;
      const offsetA = column * square;
      for (let index = 0; index < square; index++)
        sum += gramsB[offsetB + index]! * gramsA[offsetA + index]!;
      pair.module.blocks[row * columns + column] =
        pair.module.blocks[row * columns + column]! + Math.max(sum, 0);
    }
  if (pair.module.experts === 1 && rank <= MAX_SPECTRUM_RANK)
    pair.module.spectrum = singularValues(
      sumBins(gramsA, columns, rank),
      sumBins(gramsB, rows, rank),
      rank,
    );
  pair.gramsA[expert] = undefined;
  pair.gramsB[expert] = undefined;
};

const accumulate = (pair: Pair, kind: "A" | "B", bytes: Uint8Array) => {
  const sideInfo = kind === "A" ? pair.a : pair.b;
  const values = decodeTensor(bytes, sideInfo.tensor.dtype);
  const { rank, features, experts } = sideInfo;
  const stride = rank * features;
  for (let expert = 0; expert < experts; expert++) {
    const slice = values.subarray(expert * stride, (expert + 1) * stride);
    if (kind === "A")
      pair.gramsA[expert] = columnGrams(
        slice,
        rank,
        features,
        pair.module.columns,
      );
    else
      pair.gramsB[expert] = rowGrams(slice, features, rank, pair.module.rows);
    if (pair.gramsA[expert] && pair.gramsB[expert]) finishExpert(pair, expert);
  }
};

const readSafetensors = async (
  reader: ByteReader,
  size: number,
  folded: { value?: Map<string, Folded> },
) => {
  const prefix = new DataView((await reader.read(8)).buffer);
  const headerBytes = Number(prefix.getBigUint64(0, true));
  if (
    headerBytes < 2 ||
    headerBytes > MAX_HEADER_BYTES ||
    headerBytes + 8 > size
  )
    throw new Error("Invalid safetensors header.");

  const header = z
    .record(z.string(), z.unknown())
    .parse(
      JSON.parse(new TextDecoder().decode(await reader.read(headerBytes))),
    );
  const dataBytes = size - 8 - headerBytes;
  const layout = plan(header, dataBytes);
  folded.value = layout.folded;
  let position = 0;
  for (const tensor of layout.tensors) {
    if (tensor.start < position) throw new Error("Overlapping tensor data.");

    await reader.skip(tensor.start - position);
    const owner = layout.owners.get(tensor.name);
    if (owner) {
      accumulate(
        owner.pair,
        owner.kind,
        await reader.read(tensor.end - tensor.start),
      );
      await nextTurn();
    } else await reader.skip(tensor.end - tensor.start);
    position = tensor.end;
  }
  await reader.skip(dataBytes - position);
};

const text = (bytes: Uint8Array) => {
  const end = bytes.indexOf(0);
  return new TextDecoder().decode(end < 0 ? bytes : bytes.subarray(0, end));
};

const readArchive = async (chunks: AsyncIterable<Uint8Array>) => {
  const reader = new ByteReader(chunks[Symbol.asyncIterator]());
  let config: z.infer<typeof ConfigSchema> | undefined;
  const folded: { value?: Map<string, Folded> } = {};
  let longName: string | undefined;
  for (;;) {
    const block = await reader.read(512);
    if (block.every((byte) => byte === 0)) break;

    const size = Number.parseInt(
      text(block.subarray(124, 136)).trim() || "0",
      8,
    );
    if (!Number.isSafeInteger(size) || size < 0)
      throw new Error("Invalid archive entry size.");

    const type = String.fromCharCode(block[156]!);
    const prefix = text(block.subarray(345, 500));
    const name =
      longName ??
      (prefix
        ? `${prefix}/${text(block.subarray(0, 100))}`
        : text(block.subarray(0, 100)));
    longName = undefined;
    const file = name.split("/").at(-1);
    const padding = (512 - (size % 512)) % 512;
    if (type === "L" || type === "x") {
      const body = text(await reader.read(Math.min(size, 65_536)));
      await reader.skip(size - Math.min(size, 65_536) + padding);
      longName =
        type === "L"
          ? body
          : (/(?:^|\n)\d+ path=([^\n]*)\n/.exec(body)?.[1] ?? undefined);
      continue;
    }
    if ((type === "0" || type === "\0") && file === "adapter_config.json") {
      if (size > MAX_CONFIG_BYTES)
        throw new Error("Adapter config is too large.");

      config = ConfigSchema.parse(
        JSON.parse(new TextDecoder().decode(await reader.read(size))),
      );
      await reader.skip(padding);
    } else if (
      (type === "0" || type === "\0") &&
      file === "adapter_model.safetensors"
    ) {
      if (folded.value) throw new Error("The archive has two adapters.");

      await readSafetensors(reader, size, folded);
      await reader.skip(padding);
    } else await reader.skip(size + padding);
  }
  await reader.drain();
  if (!config) throw new Error("The archive has no adapter_config.json.");
  if (!folded.value) throw new Error("The archive has no adapter weights.");

  return { config, folded: folded.value };
};

const toBase64 = (bytes: Uint8Array) => Buffer.from(bytes).toString("base64");
const round = (value: number) => {
  if (!Number.isFinite(value))
    throw new Error("The adapter contains non-finite values.");
  return Number(value.toPrecision(6));
};

export const summarizeAdapterArchive = async (
  gzipped: AsyncIterable<Uint8Array>,
): Promise<AdapterWeights> => {
  let result: Awaited<ReturnType<typeof readArchive>> | undefined;
  await pipeline(Readable.from(gzipped), createGunzip(), async (source) => {
    result = await readArchive(source as AsyncIterable<Uint8Array>);
  });
  const { config, folded } = result!;
  const factor = (rank: number) =>
    config.lora_alpha / (config.use_rslora ? Math.sqrt(rank) : rank);
  let parameters = 0;
  const modules: AdapterWeightModule[] = [...folded.values()]
    .sort(
      (left, right) =>
        (left.layer ?? Number.MAX_SAFE_INTEGER) -
          (right.layer ?? Number.MAX_SAFE_INTEGER) ||
        left.module.localeCompare(right.module),
    )
    .map((module) => {
      const scale = factor(module.rank);
      parameters +=
        module.experts * module.rank * (module.inputs + module.outputs);
      const blocks = Array.from(
        module.blocks,
        (value) => Math.sqrt(value) * scale,
      );
      const max = Math.max(0, ...blocks);
      const norm =
        Math.sqrt(module.blocks.reduce((sum, value) => sum + value, 0)) * scale;
      const quantized = Uint8Array.from(blocks, (value) =>
        max > 0 ? Math.round((value / max) * 255) : 0,
      );
      return {
        module: module.module,
        layer: module.layer,
        shape: [module.outputs, module.inputs] as [number, number],
        experts: module.experts,
        rank: module.rank,
        norm: round(norm),
        singular_values: (module.spectrum ?? []).map((value) =>
          round(value * scale),
        ),
        heatmap_shape: [module.rows, module.columns] as [number, number],
        heatmap: toBase64(quantized),
        heatmap_max: round(max),
      };
    });

  return AdapterWeightsSchema.parse({
    rank: config.r,
    alpha: config.lora_alpha,
    scale: factor(config.r),
    parameters,
    modules,
  });
};
