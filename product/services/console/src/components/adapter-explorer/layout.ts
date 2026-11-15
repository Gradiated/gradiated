import type { ExplorerModel, ModuleView } from "./model";

// Plates run along +x from the embedding to the head and face -x; on a plate,
// u runs along +z (input features) and v along +y (output features).

export type PanelLayout = {
  module: ModuleView;
  plate: number;
  u: number;
  v: number;
  width: number;
  height: number;
};

export type ExpertGrid = {
  count: number;
  columns: number;
  rows: number;
  size: number;
  gap: number;
  u: number;
  v: number;
};

export type PlateKind = "embedding" | "layer" | "head";

export type PlateLayout = {
  index: number;
  kind: PlateKind;
  layer: number | null;
  x: number;
  width: number;
  height: number;
  panels: PanelLayout[];
  experts?: ExpertGrid;
  intensity: number;
};

export type DeckLayout = {
  plates: PlateLayout[];
  panels: PanelLayout[];
  spacing: number;
  width: number;
  height: number;
  start: number;
  end: number;
};

const SPACING = 1.15;
const GAP = 0.16;
const PADDING = 0.32;
const MAX_ROW = 5.4;

const span = (features: number, hidden: number, limit: number) =>
  Math.min(limit, Math.max(0.1, 0.6 * Math.sqrt(features / hidden)));

const arrange = (
  modules: ModuleView[],
  hidden: number,
  limit = 2.6,
): { panels: Omit<PanelLayout, "plate">[]; width: number; height: number } => {
  const rows: {
    items: Omit<PanelLayout, "plate">[];
    width: number;
    height: number;
  }[] = [];
  for (const module of modules) {
    const width = span(module.shape[1], hidden, limit);
    const height = span(module.shape[0], hidden, limit);
    let row = rows.at(-1);
    if (!row || (row.items.length && row.width + GAP + width > MAX_ROW)) {
      row = { items: [], width: 0, height: 0 };
      rows.push(row);
    }
    row.items.push({
      module,
      u: row.width + width / 2,
      v: -height / 2,
      width,
      height,
    });
    row.width += (row.items.length > 1 ? GAP : 0) + width;
    row.height = Math.max(row.height, height);
  }
  const width = Math.max(0, ...rows.map((row) => row.width));
  let top = 0;
  const panels: Omit<PanelLayout, "plate">[] = [];
  for (const row of rows) {
    for (const item of row.items)
      panels.push({ ...item, u: item.u - row.width / 2, v: item.v + top });
    top -= row.height + GAP;
  }
  return { panels, width, height: rows.length ? -top - GAP : 0 };
};

const expertGrid = (count: number, width: number): ExpertGrid | undefined => {
  if (!count) return undefined;

  const columns = Math.min(count, Math.ceil(Math.sqrt(count * 2.6)));
  const rows = Math.ceil(count / columns);
  const pitch = Math.min(0.16, Math.max(width, 3.2) / columns);
  return {
    count,
    columns,
    rows,
    size: pitch * 0.72,
    gap: pitch * 0.28,
    u: 0,
    v: 0,
  };
};

export const buildDeckLayout = (model: ExplorerModel): DeckLayout => {
  const contents = model.layers.map((layer) => {
    const arranged = arrange(layer.modules, model.hidden);
    const experts = expertGrid(layer.experts, arranged.width);
    const expertHeight = experts
      ? experts.rows * (experts.size + experts.gap) - experts.gap
      : 0;
    const expertWidth = experts
      ? experts.columns * (experts.size + experts.gap) - experts.gap
      : 0;
    return {
      arranged,
      experts,
      width: Math.max(arranged.width, expertWidth),
      height:
        arranged.height +
        (experts ? (arranged.height ? 0.3 : 0) + expertHeight : 0),
      expertHeight,
    };
  });
  const width =
    Math.max(2.4, ...contents.map(({ width }) => width)) + PADDING * 2;
  const height =
    Math.max(1.6, ...contents.map(({ height }) => height)) + PADDING * 2;

  const plates: PlateLayout[] = [];
  const panels: PanelLayout[] = [];
  const add = (plate: Omit<PlateLayout, "index">) => {
    const index = plates.length;
    plates.push({ ...plate, index });
    for (const panel of plate.panels) panels.push({ ...panel, plate: index });
  };

  const head = model.head;
  const headArranged = head
    ? arrange([head], model.hidden, 4.2)
    : { panels: [], width: 1.4, height: 2.2 };
  const endWidth = Math.max(width * 0.6, headArranged.width + PADDING * 2);
  const endHeight = Math.max(height, headArranged.height + PADDING * 2);
  const placeEnd = (arranged: typeof headArranged, plate: number) =>
    arranged.panels.map((panel) => ({
      ...panel,
      plate,
      v: panel.v + arranged.height / 2,
    }));

  add({
    kind: "embedding",
    layer: null,
    x: -SPACING * 2.2,
    width: endWidth,
    height: endHeight,
    panels: [],
    intensity: 0,
  });

  model.layers.forEach((layer, index) => {
    const content = contents[index]!;
    const top = content.height / 2;
    const plate = plates.length;
    add({
      kind: "layer",
      layer: layer.index,
      x: index * SPACING,
      width,
      height,
      panels: content.arranged.panels.map((panel) => ({
        ...panel,
        plate,
        v: panel.v + top,
      })),
      ...(content.experts
        ? {
            experts: {
              ...content.experts,
              v:
                top -
                content.arranged.height -
                (content.arranged.height ? 0.3 : 0) -
                content.expertHeight / 2,
            },
          }
        : {}),
      intensity: layer.intensity,
    });
  });

  const headPlate = plates.length;
  add({
    kind: "head",
    layer: null,
    x: (model.layers.length - 1) * SPACING + SPACING * 2.4,
    width: endWidth,
    height: endHeight,
    panels: placeEnd(headArranged, headPlate),
    intensity: head?.intensity ?? 0,
  });

  return {
    plates,
    panels,
    spacing: SPACING,
    width: Math.max(width, endWidth),
    height: Math.max(height, endHeight),
    start: plates[0]!.x,
    end: plates.at(-1)!.x,
  };
};
