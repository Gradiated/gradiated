import { describe, expect, it } from "vitest";
import {
  decodeTensor,
  summarizeAdapterArchive,
  symmetricEigenvalues,
} from "../src/training/adapter-weights.js";
import {
  archive,
  matrix,
  random,
  safetensors,
  tarEntry,
  type Matrix,
} from "./support/adapter-archive.js";

const multiply = (left: Matrix, right: Matrix, scale = 1): Matrix => ({
  rows: left.rows,
  columns: right.columns,
  values: Array.from({ length: left.rows * right.columns }, (_, index) => {
    const row = Math.floor(index / right.columns);
    const column = index % right.columns;
    let sum = 0;
    for (let k = 0; k < left.columns; k++)
      sum +=
        left.values[row * left.columns + k]! *
        right.values[k * right.columns + column]!;
    return sum * scale;
  }),
});
const transpose = (input: Matrix): Matrix => ({
  rows: input.columns,
  columns: input.rows,
  values: Array.from({ length: input.values.length }, (_, index) => {
    const row = Math.floor(index / input.rows);
    const column = index % input.rows;
    return input.values[column * input.columns + row]!;
  }),
});
const frobenius = (input: Matrix) =>
  Math.sqrt(input.values.reduce((sum, value) => sum + value * value, 0));
const singularValues = (input: Matrix) => {
  const gram = multiply(transpose(input), input);
  return symmetricEigenvalues(Float64Array.from(gram.values), gram.rows)
    .map((value) => Math.sqrt(Math.max(value, 0)))
    .sort((a, b) => b - a);
};
const blockNorms = (input: Matrix, rows: number, columns: number) => {
  const edge = (size: number, bins: number, bin: number) =>
    Math.floor((bin * size) / bins);
  return Array.from({ length: rows * columns }, (_, index) => {
    const row = Math.floor(index / columns);
    const column = index % columns;
    let sum = 0;
    for (
      let i = edge(input.rows, rows, row);
      i < edge(input.rows, rows, row + 1);
      i++
    )
      for (
        let j = edge(input.columns, columns, column);
        j < edge(input.columns, columns, column + 1);
        j++
      )
        sum += input.values[i * input.columns + j]! ** 2;
    return Math.sqrt(sum);
  });
};

const config = (overrides: Record<string, unknown> = {}) =>
  Buffer.from(
    JSON.stringify({
      peft_type: "LORA",
      r: 3,
      lora_alpha: 6,
      target_modules: ["q_proj", "lm_head"],
      ...overrides,
    }),
  );

async function* chunks(bytes: Buffer, size = 97) {
  for (let offset = 0; offset < bytes.length; offset += size)
    yield bytes.subarray(offset, offset + size);
}

const decodeHeatmap = (value: string) => [...Buffer.from(value, "base64")];

describe("adapter weight summary", () => {
  it("matches the dense update for every projection and the head", async () => {
    const next = random(7);
    const prefix = "base_model.model.model.layers";
    const layers = [0, 1].map(() => ({
      a: matrix(3, 10, next),
      b: matrix(12, 3, next),
    }));
    const head = { a: matrix(3, 10, next), b: matrix(70, 3, next) };
    // B before A, and the head between layers, to exercise pending pairs.
    const weights = safetensors([
      {
        name: `${prefix}.1.self_attn.q_proj.lora_B.weight`,
        matrix: layers[1]!.b,
      },
      { name: "base_model.model.lm_head.lora_A.weight", matrix: head.a },
      {
        name: `${prefix}.0.self_attn.q_proj.lora_A.weight`,
        matrix: layers[0]!.a,
      },
      {
        name: `${prefix}.0.self_attn.q_proj.lora_B.weight`,
        matrix: layers[0]!.b,
      },
      { name: "base_model.model.lm_head.lora_B.weight", matrix: head.b },
      {
        name: `${prefix}.1.self_attn.q_proj.lora_A.weight`,
        matrix: layers[1]!.a,
      },
    ]);
    const summary = await summarizeAdapterArchive(
      chunks(
        archive(
          tarEntry("adapter_model.safetensors", weights),
          tarEntry("adapter_config.json", config()),
        ),
      ),
    );

    expect(summary).toMatchObject({ rank: 3, alpha: 6, scale: 2 });
    expect(summary.parameters).toBe(2 * 3 * 22 + 3 * 80);
    expect(summary.modules.map(({ layer, module }) => [layer, module])).toEqual(
      [
        [0, "self_attn.q_proj"],
        [1, "self_attn.q_proj"],
        [null, "lm_head"],
      ],
    );
    for (const [index, pair] of [...layers, head].entries()) {
      const module = summary.modules[index]!;
      const delta = multiply(pair.b, pair.a, 2);
      expect(module.shape).toEqual([delta.rows, delta.columns]);
      expect(module.experts).toBe(1);
      expect(module.norm).toBeCloseTo(frobenius(delta), 5);
      const expected = singularValues(delta).slice(0, 3);
      module.singular_values.forEach((value, rank) =>
        expect(value).toBeCloseTo(expected[rank]!, 4),
      );
      expect(Math.hypot(...module.singular_values)).toBeCloseTo(module.norm, 5);

      const [rows, columns] = module.heatmap_shape;
      expect([rows, columns]).toEqual([
        Math.min(delta.rows, 64),
        Math.min(delta.columns, 64),
      ]);
      const blocks = blockNorms(delta, rows, columns);
      const max = Math.max(...blocks);
      expect(module.heatmap_max).toBeCloseTo(max, 5);
      decodeHeatmap(module.heatmap).forEach((byte, cell) =>
        expect(
          Math.abs(byte - (blocks[cell]! / max) * 255),
        ).toBeLessThanOrEqual(0.5 + 1e-6),
      );
    }
  });

  it("folds experts, reads nested and long archive paths and skips other files", async () => {
    const next = random(11);
    const experts = [0, 1].map(() => ({
      a: matrix(2, 6, next),
      b: matrix(5, 2, next),
    }));
    const fused = [0, 1, 2].map(() => ({
      a: matrix(2, 6, next),
      b: matrix(4, 2, next),
    }));
    const prefix = "base_model.model.model.layers.0.mlp";
    const weights = safetensors([
      ...experts.flatMap((expert, index) => [
        {
          name: `${prefix}.experts.${index}.down_proj.lora_A.weight`,
          matrix: expert.a,
        },
        {
          name: `${prefix}.experts.${index}.down_proj.lora_B.weight`,
          matrix: expert.b,
        },
      ]),
      {
        name: `${prefix}.experts.gate_up_proj.lora_A.weight`,
        matrix: fused.map(({ a }) => a),
      },
      {
        name: `${prefix}.experts.gate_up_proj.lora_B.weight`,
        matrix: fused.map(({ b }) => b),
      },
      {
        name: "base_model.model.model.embed_tokens.weight",
        matrix: matrix(4, 4, next),
      },
    ]);
    const longName = `${"nested/".repeat(20)}adapter_model.safetensors`;
    const summary = await summarizeAdapterArchive(
      chunks(
        archive(
          tarEntry("README.md", Buffer.from("# adapter")),
          tarEntry(
            "adapter/adapter_config.json",
            config({ r: 2, lora_alpha: 2 }),
          ),
          tarEntry("././@LongLink", Buffer.from(`${longName}\0`), "L"),
          tarEntry(longName.slice(0, 100), weights),
        ),
        4096,
      ),
    );

    expect(summary.modules).toHaveLength(2);
    const [downProj, gateUp] = [
      summary.modules.find(({ module }) => module === "mlp.experts.down_proj")!,
      summary.modules.find(
        ({ module }) => module === "mlp.experts.gate_up_proj",
      )!,
    ];
    expect(downProj).toMatchObject({
      layer: 0,
      experts: 2,
      singular_values: [],
    });
    expect(downProj.norm).toBeCloseTo(
      Math.hypot(...experts.map(({ a, b }) => frobenius(multiply(b, a)))),
      5,
    );
    expect(gateUp).toMatchObject({ experts: 3, shape: [4, 6] });
    expect(gateUp.norm).toBeCloseTo(
      Math.hypot(...fused.map(({ a, b }) => frobenius(multiply(b, a)))),
      5,
    );
  });

  it("decodes half and bfloat16 tensors and applies rank-stabilized scaling", async () => {
    expect(
      symmetricEigenvalues(Float64Array.from([2, 1, 0, 1, 2, 0, 0, 0, 5]), 3)
        .map((value) => Math.round(value * 1e9) / 1e9)
        .sort(),
    ).toEqual([1, 3, 5]);
    expect([
      ...decodeTensor(
        Uint8Array.from([0x00, 0x3c, 0x00, 0xc0, 0x01, 0x00]),
        "F16",
      ),
    ]).toEqual([1, -2, 2 ** -24]);
    expect([
      ...decodeTensor(Uint8Array.from([0x80, 0x3f, 0x40, 0xc0]), "BF16"),
    ]).toEqual([1, -3]);

    const next = random(3);
    const a = matrix(4, 8, () => Math.round(next() * 8) / 4);
    const b = matrix(8, 4, () => Math.round(next() * 8) / 4);
    const summary = await summarizeAdapterArchive(
      chunks(
        archive(
          tarEntry(
            "adapter_config.json",
            config({ r: 4, lora_alpha: 4, use_rslora: true }),
          ),
          tarEntry(
            "adapter_model.safetensors",
            safetensors([
              {
                name: "model.layers.3.self_attn.v_proj.lora_A.weight",
                matrix: a,
                dtype: "BF16",
              },
              {
                name: "model.layers.3.self_attn.v_proj.lora_B.weight",
                matrix: b,
                dtype: "BF16",
              },
            ]),
          ),
        ),
      ),
    );
    expect(summary.scale).toBe(2);
    expect(summary.modules[0]!.norm).toBeCloseTo(
      frobenius(multiply(b, a, 2)),
      5,
    );
  });

  it("rejects truncated, unpaired and configless archives", async () => {
    const next = random(5);
    const a = {
      name: "model.layers.0.self_attn.q_proj.lora_A.weight",
      matrix: matrix(2, 4, next),
    };
    const b = {
      name: "model.layers.0.self_attn.q_proj.lora_B.weight",
      matrix: matrix(4, 2, next),
    };
    const whole = archive(
      tarEntry("adapter_config.json", config({ r: 2 })),
      tarEntry("adapter_model.safetensors", safetensors([a, b])),
    );
    await expect(
      summarizeAdapterArchive(chunks(whole.subarray(0, whole.length - 40))),
    ).rejects.toThrow();
    await expect(
      summarizeAdapterArchive(
        chunks(
          archive(
            tarEntry("adapter_config.json", config({ r: 2 })),
            tarEntry("adapter_model.safetensors", safetensors([a])),
          ),
        ),
      ),
    ).rejects.toThrow("matching A/B pairs");
    await expect(
      summarizeAdapterArchive(
        chunks(
          archive(tarEntry("adapter_model.safetensors", safetensors([a, b]))),
        ),
      ),
    ).rejects.toThrow("no adapter_config.json");
  });
});
