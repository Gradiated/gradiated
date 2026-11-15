import type { getAdapterWeights } from "@/api/training";

export type AdapterWeights = Awaited<ReturnType<typeof getAdapterWeights>>;
export type BaseStructure = {
  layerCount: number;
  expertCount: number;
  expertLayers?: readonly number[] | undefined;
  projectionShapes?: Readonly<Record<string, readonly number[]>> | undefined;
};

type Shape = readonly [number, number];
const pair = (shape: readonly number[]): Shape => [
  shape[0] ?? 1,
  shape[1] ?? 1,
];

export type ModuleGroup = "attention" | "mlp" | "experts" | "head";

export type Heatmap = {
  rows: number;
  columns: number;
  values: Uint8Array;
  max: number;
};

export type ModuleView = {
  index: number;
  key: string;
  module: string;
  label: string;
  group: ModuleGroup;
  layer: number | null;
  shape: Shape;
  adapted: boolean;
  /** Frobenius norm of ΔW; 0 when the adapter does not touch the module. */
  norm: number;
  /** Fraction of the adapter's total update energy (Σ‖ΔW‖²). */
  share: number;
  /** 0–1 display intensity relative to the strongest module. */
  intensity: number;
  rank: number;
  experts: number;
  singularValues: number[];
  heatmap?: Heatmap;
};

export type LayerView = {
  index: number;
  /** Routed experts in this layer; 0 for a dense layer. */
  experts: number;
  modules: ModuleView[];
  norm: number;
  share: number;
  intensity: number;
};

export type ExplorerModel = {
  layerCount: number;
  expertCount: number;
  hidden: number;
  structureKnown: boolean;
  layers: LayerView[];
  head?: ModuleView;
  modules: ModuleView[];
  /** Adapted modules, largest update first. */
  ranked: ModuleView[];
  rank: number;
  alpha: number;
  scale: number;
  parameters: number;
  energy: number;
  adaptedLayers: number;
  groupShares: Record<ModuleGroup, number>;
};

export const moduleGroup = (module: string): ModuleGroup =>
  module === "lm_head"
    ? "head"
    : /(?:^|\.)experts\./.test(module)
      ? "experts"
      : /attn|attention/.test(module)
        ? "attention"
        : "mlp";

export const moduleLabel = (module: string) => {
  const parts = module.split(".");
  const last = parts.at(-1) ?? module;
  const parent = parts.at(-2);
  return parent && /expert/.test(parent) ? `${parent}.${last}` : last;
};

export const decodeHeatmap = (value: string) => {
  const binary = atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
};

const moduleKey = (layer: number | null, module: string) =>
  layer === null ? module : `${layer}/${module}`;

const mostCommon = (values: number[]) => {
  const counts = new Map<number, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  let best = values[0] ?? 1;
  for (const [value, count] of counts)
    if (count > (counts.get(best) ?? 0)) best = value;
  return best;
};

export const buildExplorerModel = (
  weights: AdapterWeights,
  structure?: BaseStructure,
): ExplorerModel => {
  const adapted = new Map(
    weights.modules.map((entry) => [
      moduleKey(entry.layer, entry.module),
      entry,
    ]),
  );
  const shapes = new Map<
    string,
    { layer: number | null; module: string; shape: Shape }
  >();
  for (const [key, shape] of Object.entries(
    structure?.projectionShapes ?? {},
  )) {
    const [first, ...rest] = key.split("/");
    const layer = rest.length ? Number(first) : null;
    const module = rest.length ? rest.join("/") : key;
    if (layer !== null && !Number.isInteger(layer)) continue;
    shapes.set(moduleKey(layer, module), { layer, module, shape: pair(shape) });
  }
  for (const entry of weights.modules) {
    const key = moduleKey(entry.layer, entry.module);
    if (!shapes.has(key))
      shapes.set(key, {
        layer: entry.layer,
        module: entry.module,
        shape: pair(entry.shape),
      });
  }

  const maxLayer = Math.max(
    -1,
    ...[...shapes.values()].map(({ layer }) => layer ?? -1),
  );
  const layerCount = Math.max(structure?.layerCount ?? 0, maxLayer + 1, 1);
  const expertCount =
    structure?.expertCount ??
    Math.max(
      0,
      ...weights.modules
        .filter(({ module }) => moduleGroup(module) === "experts")
        .map(({ experts }) => experts),
    );
  const energy = weights.modules.reduce(
    (sum, entry) => sum + entry.norm * entry.norm,
    0,
  );
  const maxNorm = Math.max(0, ...weights.modules.map(({ norm }) => norm));

  const groupOrder: Record<ModuleGroup, number> = {
    attention: 0,
    mlp: 1,
    experts: 2,
    head: 3,
  };
  const ordered = [...shapes.entries()].sort(
    ([, left], [, right]) =>
      (left.layer ?? Number.MAX_SAFE_INTEGER) -
        (right.layer ?? Number.MAX_SAFE_INTEGER) ||
      groupOrder[moduleGroup(left.module)] -
        groupOrder[moduleGroup(right.module)],
  );
  const modules: ModuleView[] = ordered.map(([key, base], index) => {
    const entry = adapted.get(key);
    const norm = entry?.norm ?? 0;
    return {
      index,
      key,
      module: base.module,
      label: moduleLabel(base.module),
      group: moduleGroup(base.module),
      layer: base.layer,
      shape: base.shape,
      adapted: Boolean(entry),
      norm,
      share: energy > 0 ? (norm * norm) / energy : 0,
      intensity: maxNorm > 0 ? (norm / maxNorm) ** 0.75 : 0,
      rank: entry?.rank ?? 0,
      experts: entry?.experts ?? 1,
      singularValues: entry?.singular_values ?? [],
      ...(entry
        ? {
            heatmap: {
              rows: entry.heatmap_shape[0] ?? 1,
              columns: entry.heatmap_shape[1] ?? 1,
              values: decodeHeatmap(entry.heatmap),
              max: entry.heatmap_max,
            },
          }
        : {}),
    };
  });

  const expertLayers = new Set(structure?.expertLayers ?? []);
  const layers: LayerView[] = Array.from({ length: layerCount }, (_, index) => {
    const members = modules.filter((module) => module.layer === index);
    const layerEnergy = members.reduce(
      (sum, module) => sum + module.norm * module.norm,
      0,
    );
    return {
      index,
      experts:
        !structure?.expertLayers || expertLayers.has(index) ? expertCount : 0,
      modules: members,
      norm: Math.sqrt(layerEnergy),
      share: energy > 0 ? layerEnergy / energy : 0,
      intensity: 0,
    };
  });
  const maxLayerNorm = Math.max(0, ...layers.map(({ norm }) => norm));
  for (const layer of layers)
    layer.intensity =
      maxLayerNorm > 0 ? (layer.norm / maxLayerNorm) ** 0.75 : 0;

  const groupShares: Record<ModuleGroup, number> = {
    attention: 0,
    mlp: 0,
    experts: 0,
    head: 0,
  };
  for (const module of modules) groupShares[module.group] += module.share;

  const head = modules.find((module) => module.layer === null);
  return {
    layerCount,
    expertCount,
    hidden: mostCommon([...shapes.values()].map(({ shape }) => shape[1])),
    structureKnown: Boolean(structure?.projectionShapes),
    layers,
    ...(head ? { head } : {}),
    modules,
    ranked: modules
      .filter((module) => module.adapted)
      .sort((left, right) => right.norm - left.norm),
    rank: weights.rank,
    alpha: weights.alpha,
    scale: weights.scale,
    parameters: weights.parameters,
    energy,
    adaptedLayers: layers.filter((layer) =>
      layer.modules.some((module) => module.adapted),
    ).length,
    groupShares,
  };
};

export const formatCount = (value: number) =>
  new Intl.NumberFormat("en-US", {
    notation: value >= 10_000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
export const formatShape = ([outputs, inputs]: readonly [number, number]) =>
  `${outputs.toLocaleString("en-US")} × ${inputs.toLocaleString("en-US")}`;

// sRGB approximations of the scene's heat ramp for HTML overlays.
const HEAT_STOPS: [number, number, number][] = [
  [10, 42, 44],
  [16, 128, 116],
  [146, 218, 64],
  [255, 206, 102],
  [255, 249, 232],
];
export const heatRgb = (t: number): [number, number, number] => {
  const value = Math.min(Math.max(t, 0), 1) * (HEAT_STOPS.length - 1);
  const index = Math.min(Math.floor(value), HEAT_STOPS.length - 2);
  const f = value - index;
  const [a, b] = [HEAT_STOPS[index]!, HEAT_STOPS[index + 1]!];
  return [0, 1, 2].map((channel) =>
    Math.round(a[channel]! + (b[channel]! - a[channel]!) * f),
  ) as [number, number, number];
};
export const heatColor = (t: number) => `rgb(${heatRgb(t).join(" ")})`;
