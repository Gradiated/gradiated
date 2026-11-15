import { adapterProjectionShapes } from "@gradiated/contracts/adapter-shapes";

import type {
  AdapterWeights,
  BaseStructure,
} from "@/components/adapter-explorer/model";
import {
  deepseek_v4_1_flash,
  glm_5_3_flash,
  qwen3_0_6b,
  qwen3_32b,
} from "@/stories/base-model-configs";

// Layer counts, expert layouts and shapes follow each model's pinned config.json;
// norms, heatmaps and singular values are seeded noise, not measurements.

type Shapes = Record<string, readonly [number, number]>;

const generator = (seed: number) => () => {
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4_294_967_296;
};

const range = (start: number, end: number) =>
  Array.from({ length: end - start }, (_, index) => start + index);

const toBase64 = (bytes: Uint8Array) =>
  btoa(String.fromCharCode(...Array.from(bytes)));

export const syntheticWeights = ({
  shapes,
  layerCount,
  rank,
  alpha = rank * 2,
  seed = 1,
  peak = 0.68,
}: {
  shapes: Shapes;
  layerCount: number;
  rank: number;
  alpha?: number;
  seed?: number;
  peak?: number;
}): AdapterWeights => {
  const random = generator(seed);
  const gaussian = () =>
    Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(2 * Math.PI * random());
  const entries = Object.entries(shapes);
  const grid = Math.max(
    1,
    Math.min(64, Math.floor(Math.sqrt(131_072 / Math.max(entries.length, 1)))),
  );
  const moduleScale = new Map<string, number>();
  const modules = entries.map(([key, [outputs, inputs]]) => {
    const [first, ...rest] = key.split("/");
    const layer = rest.length ? Number(first) : null;
    const module = rest.length ? rest.join("/") : key;
    const position = layer === null ? 1 : layer / Math.max(layerCount - 1, 1);
    const profile =
      0.3 +
      Math.exp(-(((position - peak) / 0.16) ** 2)) +
      0.45 * Math.exp(-(((position - 0.12) / 0.08) ** 2));
    if (!moduleScale.has(module)) moduleScale.set(module, 0.4 + random() * 1.2);
    const norm =
      profile *
      moduleScale.get(module)! *
      Math.exp(gaussian() * 0.22) *
      Math.sqrt((outputs + inputs) / 4096) *
      0.35;

    const rows = Math.min(grid, outputs);
    const columns = Math.min(grid, inputs);
    const hot = new Set(range(0, 3).map(() => Math.floor(random() * rows)));
    const rowWeights = range(0, rows).map(
      (row) => Math.exp(gaussian() * 0.45) * (hot.has(row) ? 2.6 : 1),
    );
    const columnWeights = range(0, columns).map(() =>
      Math.exp(gaussian() * 0.35),
    );
    const blocks = rowWeights.flatMap((row) =>
      columnWeights.map((column) => row * column * Math.exp(gaussian() * 0.15)),
    );
    const energy = Math.sqrt(
      blocks.reduce((sum, value) => sum + value ** 2, 0),
    );
    const max = Math.max(...blocks);
    const decay = 0.25 + random() * 0.6;
    const spectrum = range(0, rank).map(
      (index) => Math.exp(-index * decay) * (1 + random() * 0.15),
    );
    const spectrumNorm = Math.hypot(...spectrum);
    return {
      module,
      layer,
      shape: [outputs, inputs],
      experts: 1,
      rank,
      norm,
      singular_values: spectrum
        .map((value) => (value / spectrumNorm) * norm)
        .sort((left, right) => right - left),
      heatmap_shape: [rows, columns],
      heatmap: toBase64(
        Uint8Array.from(blocks, (value) => Math.round((value / max) * 255)),
      ),
      heatmap_max: (max / energy) * norm,
    };
  });
  return {
    rank,
    alpha,
    scale: alpha / rank,
    parameters: entries.reduce(
      (sum, [, [outputs, inputs]]) => sum + rank * (outputs + inputs),
      0,
    ),
    modules,
  };
};

const pick = (shapes: Shapes, keep: (key: string) => boolean): Shapes =>
  Object.fromEntries(Object.entries(shapes).filter(([key]) => keep(key)));

// DeepSeek V4.1 Flash 1017: 40 layers, 384 routed experts in every layer.
const deepseekShapes = adapterProjectionShapes({
  ...deepseek_v4_1_flash,
  vocab_size: 129_280,
})!;
export const deepseekStructure: BaseStructure = {
  layerCount: 40,
  expertCount: 384,
  expertLayers: range(0, 40),
  projectionShapes: deepseekShapes,
};
export const deepseekHeadWeights = syntheticWeights({
  shapes: pick(deepseekShapes, (key) => key === "lm_head"),
  layerCount: 40,
  rank: 4,
  alpha: 8,
  seed: 4,
});
export const deepseekAttentionWeights = syntheticWeights({
  shapes: pick(deepseekShapes, (key) => key !== "lm_head"),
  layerCount: 40,
  rank: 8,
  seed: 8,
});

// GLM-5.3 Flash: 45 layers, 288 routed experts after the first 3 dense layers.
const glmShapes = adapterProjectionShapes(glm_5_3_flash)!;
export const glmStructure: BaseStructure = {
  layerCount: 45,
  expertCount: 288,
  expertLayers: range(3, 45),
  projectionShapes: glmShapes,
};
export const glmAttentionWeights = syntheticWeights({
  shapes: glmShapes,
  layerCount: 45,
  rank: 16,
  seed: 53,
  peak: 0.45,
});

const qwen32bShapes = adapterProjectionShapes(qwen3_32b)!;
export const qwen32bStructure: BaseStructure = {
  layerCount: 64,
  expertCount: 0,
  projectionShapes: qwen32bShapes,
};
export const qwen32bWeights = syntheticWeights({
  shapes: qwen32bShapes,
  layerCount: 64,
  rank: 8,
  seed: 32,
});

const qwen06bShapes = adapterProjectionShapes(qwen3_0_6b)!;
export const qwen06bStructure: BaseStructure = {
  layerCount: 28,
  expertCount: 0,
  projectionShapes: qwen06bShapes,
};
export const qwen06bWeights = syntheticWeights({
  shapes: pick(qwen06bShapes, (key) => key.includes("self_attn")),
  layerCount: 28,
  rank: 16,
  seed: 6,
});

// Kimi K3.1 Pro: 93 layers, 896 routed experts after one dense layer. Its adapter
// shapes are not in the catalog, so only the adapter's own modules are drawn.
export const kimiStructure: BaseStructure = {
  layerCount: 93,
  expertCount: 896,
  expertLayers: range(1, 93),
};
const kimiAttention = (() => {
  const hidden = 7168;
  const heads = 96;
  const shapes: Shapes = {};
  for (const layer of range(0, 93)) {
    shapes[`${layer}/self_attn.q_a_proj`] = [1536, hidden];
    shapes[`${layer}/self_attn.q_b_proj`] = [heads * (128 + 64), 1536];
    shapes[`${layer}/self_attn.kv_a_proj_with_mqa`] = [512 + 64, hidden];
    shapes[`${layer}/self_attn.kv_b_proj`] = [heads * (128 + 128), 512];
    shapes[`${layer}/self_attn.o_proj`] = [hidden, heads * 128];
  }
  return shapes;
})();
export const kimiWeights = syntheticWeights({
  shapes: kimiAttention,
  layerCount: 93,
  rank: 8,
  seed: 93,
  peak: 0.8,
});
