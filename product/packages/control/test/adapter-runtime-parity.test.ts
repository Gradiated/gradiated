import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdtemp, open, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";
import {
  adapterFileReader,
  validateAdapterFiles,
} from "../src/training/adapter-upload.js";
import { adapterFiles } from "./support/adapter-upload.js";

const base = "test/base";
const duplicateHeader = () => {
  const fixture = adapterFiles(base);
  const size = Number(fixture.weights.readBigUInt64LE());
  const header = fixture.weights.subarray(8, 8 + size).toString();
  const [firstKey, firstValue] = Object.entries(JSON.parse(header))[0]!;
  const duplicate = JSON.stringify({ [firstKey]: firstValue }).slice(1, -1);
  const next = Buffer.from(`{${duplicate},${header.slice(1)}`);
  const prefix = Buffer.alloc(8);
  prefix.writeBigUInt64LE(BigInt(next.length));
  return {
    ...fixture,
    weights: Buffer.concat([prefix, next, fixture.weights.subarray(8 + size)]),
  };
};
const splitExpertCoverage = () => {
  const fixture = adapterFiles(base, 2, [0]);
  const weights = Buffer.from(fixture.weights);
  const size = Number(weights.readBigUInt64LE());
  const header = weights
    .subarray(8, 8 + size)
    .toString()
    .replaceAll("layers.1.mlp.experts.0.", "layers.1.mlp.experts.1.");
  weights.write(header, 8);
  return { ...fixture, weights };
};
const fusedFiles = (change?: "rank" | "bytes" | "mixed" | "dense") => {
  const fixture = adapterFiles(base, 2, change === "mixed" ? 1 : 2);
  const size = Number(fixture.weights.readBigUInt64LE());
  const tensors = JSON.parse(fixture.weights.subarray(8, 8 + size).toString());
  if (change === "rank")
    Object.values<{ shape: number[] }>(tensors)[0]!.shape[1] = 3;
  if (change === "bytes")
    Object.values<{ data_offsets: number[] }>(tensors)[0]!.data_offsets[1] = 32;
  if (change === "mixed" || change === "dense") {
    for (const [name, value] of Object.entries(tensors)) {
      if (!name.includes("layers.1.")) continue;
      const tensor = value as { shape: number[] };
      // Keep byte count and rank valid while changing the second layer's layout.
      const width = change === "mixed" ? 4 : 8;
      tensor.shape = name.includes("lora_A") ? [2, width] : [width, 2];
      delete tensors[name];
      tensors[
        name.replace(
          "mlp.experts.",
          change === "mixed" ? "mlp.experts.0." : "mlp.",
        )
      ] = tensor;
    }
  }
  const header = Buffer.from(JSON.stringify(tensors));
  const prefix = Buffer.alloc(8);
  prefix.writeBigUInt64LE(BigInt(header.length));
  return {
    ...fixture,
    weights: Buffer.concat([
      prefix,
      header,
      fixture.weights.subarray(8 + size),
    ]),
  };
};
const runtime = fileURLToPath(
  new URL("../../../inference/lora", import.meta.url),
);
const execute = promisify(execFile);
const verify = `
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from artifacts import validate_tensors
try:
    validate_tensors(Path(sys.argv[2]), {"version": {"adapter": {"rank": 2}}}, json.loads(sys.argv[3]))
except ValueError:
    print(json.dumps(False))
else:
    print(json.dumps(True))
`;

it.each([
  {
    name: "complete dense layers",
    layerCount: 2,
    expertCount: 0,
    files: () => adapterFiles(base, 2),
    accepted: true,
  },
  {
    name: "a subset of dense layers",
    layerCount: 2,
    expertCount: 0,
    files: () => adapterFiles(base, 1),
    accepted: true,
  },
  {
    name: "complete expert layers",
    layerCount: 2,
    expertCount: 2,
    files: () => adapterFiles(base, 2, [0, 1]),
    accepted: true,
  },
  {
    name: "indexed MoE header above 1 MiB",
    layerCount: 2,
    expertCount: 4096,
    files: () => {
      const fixture = adapterFiles(
        base,
        2,
        Array.from({ length: 4096 }, (_, index) => index),
      );
      expect(Number(fixture.weights.readBigUInt64LE())).toBeGreaterThan(
        1024 * 1024,
      );
      return fixture;
    },
    accepted: true,
  },
  {
    name: "missing expert coverage",
    layerCount: 2,
    expertCount: 2,
    files: () => adapterFiles(base, 2, [0]),
    accepted: false,
  },
  {
    name: "out-of-range experts",
    layerCount: 1,
    expertCount: 2,
    files: () => adapterFiles(base, 1, [2]),
    accepted: false,
  },
  {
    name: "experts on a dense base",
    layerCount: 1,
    expertCount: 0,
    files: () => adapterFiles(base, 1, [0]),
    accepted: false,
  },
  ...[
    {
      name: "complete fused experts",
      expertCount: 2,
      files: () => fusedFiles(),
      accepted: true,
    },
    {
      name: "fused expert count mismatch",
      expertCount: 3,
      files: () => fusedFiles(),
      accepted: false,
    },
    {
      name: "fused experts on a dense base",
      expertCount: 0,
      files: () => fusedFiles(),
      accepted: false,
    },
    {
      name: "fused rank mismatch",
      expertCount: 2,
      files: () => fusedFiles("rank"),
      accepted: false,
    },
    {
      name: "fused byte count mismatch",
      expertCount: 2,
      files: () => fusedFiles("bytes"),
      accepted: false,
    },
    {
      name: "mixed indexed and fused expert layouts",
      expertCount: 1,
      files: () => fusedFiles("mixed"),
      accepted: false,
    },
    {
      name: "dense modules alongside fused experts",
      expertCount: 2,
      files: () => fusedFiles("dense"),
      accepted: true,
    },
  ].map((scenario) => ({ ...scenario, layerCount: 2 })),
  {
    name: "duplicate config keys",
    layerCount: 1,
    expertCount: 0,
    files: () => {
      const fixture = adapterFiles(base);
      return {
        ...fixture,
        config: Buffer.from(
          fixture.config.toString().replace('"r":2', '"r":1,"r":2'),
        ),
      };
    },
    accepted: false,
  },
  {
    name: "duplicate tensor keys",
    layerCount: 1,
    expertCount: 0,
    files: duplicateHeader,
    accepted: false,
  },
  {
    name: "non-finite JSON numbers",
    layerCount: 1,
    expertCount: 0,
    files: () => {
      const fixture = adapterFiles(base);
      return {
        ...fixture,
        config: Buffer.from(
          fixture.config.toString().replace('"r":2', '"unused":1e999,"r":2'),
        ),
      };
    },
    accepted: false,
  },
  {
    name: "JSON-like text metadata",
    layerCount: 1,
    expertCount: 0,
    files: () => {
      const fixture = adapterFiles(base);
      return {
        ...fixture,
        config: Buffer.from(
          JSON.stringify({
            ...JSON.parse(fixture.config.toString()),
            notes: '{"r":1,"r":2}',
          }),
        ),
      };
    },
    accepted: true,
  },
  {
    name: "expert coverage is per layer",
    layerCount: 2,
    expertCount: 2,
    files: splitExpertCoverage,
    accepted: false,
  },
  {
    name: "invalid UTF-8 configuration",
    layerCount: 1,
    expertCount: 0,
    files: () => {
      const fixture = adapterFiles(base);
      return {
        ...fixture,
        config: Buffer.concat([
          Buffer.from('{"unused":"'),
          Buffer.from([255]),
          Buffer.from('",'),
          fixture.config.subarray(1),
        ]),
      };
    },
    accepted: false,
  },
])(
  "matches the serving validator for $name",
  async ({ layerCount, expertCount, files, accepted }) => {
    const directory = await mkdtemp(join(tmpdir(), "adapter-runtime-parity-"));
    try {
      const fixture = files();
      const weights = join(directory, "adapter_model.safetensors");
      await writeFile(join(directory, "adapter_config.json"), fixture.config);
      await writeFile(weights, fixture.weights);
      const file = await open(weights, "r");
      try {
        const uploaded = await validateAdapterFiles(
          fixture.config,
          adapterFileReader(file, fixture.weights.length),
          base,
          { layerCount, expertCount },
        ).then(
          () => true,
          () => false,
        );
        expect(uploaded).toBe(accepted);
      } finally {
        await file.close();
      }
      const { stdout } = await execute(
        "python3",
        [
          "-c",
          verify,
          runtime,
          directory,
          JSON.stringify({
            num_hidden_layers: layerCount,
            n_routed_experts: expertCount,
          }),
        ],
        { timeout: 10000 },
      );
      expect(JSON.parse(stdout)).toBe(accepted);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  },
  30_000,
);
