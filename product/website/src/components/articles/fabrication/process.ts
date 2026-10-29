import type { MachineId } from "./model";
import { maskCycles, stages } from "./sequence";
import type { MaskId } from "./sequence";

export const clamp = (value: number) => Math.max(0, Math.min(1, value));
export const ease = (value: number) => {
  const t = clamp(value);

  return t * t * (3 - 2 * t);
};
export const portion = (value: number, start: number, end: number) =>
  ease((value - start) / (end - start));

export const inverterDuration = 2400;

export const inverterOperation = (input: number, progress: number) => ({
  supply: 1,
  input: portion(progress, 0, 0.08),
  gates: portion(progress, 0.08, 0.2),
  electrodes: portion(progress, 0.2, 0.3),
  transfer: portion(progress, 0.3, 0.65),
  outputRail: portion(progress, 0.65, 0.78),
  exit: portion(progress, 0.78, 0.9),
  output: progress >= 0.9 ? 1 - input : undefined,
});

export const machineIconSize = { width: 72, height: 58 };

export const machinePlaces: Record<MachineId, { x: number; y: number }> = {
  furnace: { x: 58, y: 55 },
  coat: { x: 163, y: 55 },
  litho: { x: 268, y: 55 },
  develop: { x: 372, y: 55 },
  etch: { x: 477, y: 55 },
  strip: { x: 582, y: 55 },
  anneal: { x: 58, y: 197 },
  implant: { x: 163, y: 197 },
  deposit: { x: 268, y: 197 },
  metal: { x: 372, y: 197 },
  polish: { x: 477, y: 197 },
  inspect: { x: 582, y: 197 },
};

export const machineLoadingSpots: Record<
  MachineId,
  { x: number; y: number; rx: number; ry: number }
> = {
  furnace: { x: 36, y: 27, rx: 3.5, ry: 10 },
  coat: { x: 36, y: 29, rx: 13, ry: 13 },
  litho: { x: 36, y: 34, rx: 10, ry: 3 },
  develop: { x: 36, y: 35, rx: 13, ry: 3.5 },
  etch: { x: 36, y: 35, rx: 16, ry: 3 },
  strip: { x: 36, y: 35, rx: 13, ry: 3.5 },
  anneal: { x: 36, y: 33, rx: 16, ry: 4 },
  implant: { x: 55, y: 27, rx: 3, ry: 10 },
  deposit: { x: 36, y: 35, rx: 16, ry: 3 },
  metal: { x: 36, y: 35, rx: 16, ry: 3 },
  polish: { x: 36, y: 28, rx: 13, ry: 13 },
  inspect: { x: 32, y: 30, rx: 16, ry: 16 },
};

export const machineLoadingPoint = (machine: MachineId) => {
  const centre = machinePlaces[machine];
  const spot = machineLoadingSpots[machine];

  return {
    x: centre.x + spot.x - machineIconSize.width / 2,
    y: centre.y + spot.y - machineIconSize.height / 2,
  };
};

export const waferPatternScale = 0.3;

export const waferDetailRegion = { x: 200.4, y: 104.7, size: 8.1 };

export type Visit = {
  machine?: MachineId;
  from?: MachineId;
  progress: number;
  process: number;
  loaded: number;
  working: boolean;
};

export const visitFor = (
  progress: number,
  machine: MachineId | undefined,
  from: MachineId | undefined,
): Visit => ({
  machine,
  from,
  progress,
  process: portion(progress, 0.36, 0.84),
  loaded: portion(progress, 0.25, 0.36) * (1 - portion(progress, 0.88, 0.98)),
  working: !!machine && progress >= 0.36 && progress < 0.84,
});

export const exposureLighting = (visit: Visit) => {
  const active = visit.working && visit.machine === "litho";

  return {
    beam: active ? 1 - portion(visit.process, 0.6, 0.72) : 0,
    glow: active
      ? portion(visit.process, 0, 0.12) *
        (1 - portion(visit.process, 0.45, 0.95)) *
        0.72
      : 0,
  };
};

export { stages } from "./sequence";

type ResistField = `${MaskId}${"Coat" | "Expose" | "Develop" | "Strip"}`;
type ResistValues = Record<ResistField, number>;

export const patternState = (index: number, visit: Visit) => {
  const step = (scene: number) =>
    index === 0 || index > scene ? 1 : index < scene ? 0 : visit.process;
  const resists = Object.fromEntries(
    maskCycles.flatMap((cycle) =>
      (["coat", "expose", "develop", "strip"] as const).map((phase) => [
        `${cycle.id}${phase[0].toUpperCase()}${phase.slice(1)}`,
        step(cycle[phase]),
      ]),
    ),
  ) as ResistValues;

  return {
    ...resists,
    oxide: step(stages.growOxide),
    well: step(stages.well),
    wellAnneal: step(stages.wellAnneal),
    nitride: step(stages.isolation),
    prepareIsolation: step(stages.prepareIsolation),
    isolation: step(stages.fieldOxide),
    nitrideStrip: step(stages.nitrideStrip),
    padOxideStrip: step(stages.padOxideStrip),
    gateOxide: step(stages.gateOxide),
    poly: step(stages.poly),
    patternGate: step(stages.patternGate),
    implantN: step(stages.implant),
    implantP: step(stages.implantP),
    anneal: step(stages.anneal),
    cover: step(stages.contactInsulation),
    contactPolish: step(stages.contactPolish),
    contacts: step(stages.contacts),
    metalFill: portion(step(stages.metal), 0, 0.5),
    metal: portion(step(stages.metal), 0.5, 1),
    metalPattern: step(stages.metalPattern),
    interconnect: index === 0 ? 0 : step(stages.interconnect),
    polish: index === 0 ? 0 : step(stages.polish),
    viaOpen: index === 0 ? 0 : step(stages.via),
    viaFill: index === 0 ? 0 : portion(step(stages.upperMetal), 0, 0.5),
    upperMetal: index === 0 ? 0 : portion(step(stages.upperMetal), 0.5, 1),
    upperMetalPattern: index === 0 ? 0 : step(stages.upperMetalPattern),
  };
};
export type PatternState = ReturnType<typeof patternState>;
export const blendPattern = (
  from: PatternState,
  to: PatternState,
  progress: number,
): PatternState =>
  Object.fromEntries(
    (Object.keys(to) as (keyof PatternState)[]).map((key) => [
      key,
      (from[key] ?? 0) + (to[key] - (from[key] ?? 0)) * clamp(progress),
    ]),
  ) as PatternState;

export const transitionPattern = (
  from: PatternState,
  to: PatternState,
  progress: number,
  fromIndex: number,
  toIndex: number,
): PatternState =>
  Math.abs(toIndex - fromIndex) > 1 ? to : blendPattern(from, to, progress);

export const resistState = (state: PatternState, mask: MaskId) => ({
  coat: state[`${mask}Coat`],
  expose: state[`${mask}Expose`],
  develop: state[`${mask}Develop`],
  strip: state[`${mask}Strip`],
  amount: state[`${mask}Coat`] * (1 - state[`${mask}Strip`]),
});

export type Rectangle = readonly [number, number, number, number];
export const firstMetalTracks: Rectangle[] = [
  [24, 76, 6, 10],
  [34, 66, 20, 26],
  [48, 52, 0, 10],
  [48, 52, 20, 34],
  [14, 18, 0, 26],
  [82, 86, 0, 26],
];
export const upperMetalTracks: Rectangle[] = [
  [48, 52, 0, 25],
  [48, 92, 0, 4],
];
export const onMetalTrack = (
  x: number,
  y: number,
  tracks: readonly Rectangle[],
) => tracks.some(([x0, x1, y0, y1]) => x >= x0 && x < x1 && y >= y0 && y < y1);

export const terminals = [
  { x: 16, nType: true, gate: false },
  { x: 26, nType: true, gate: true },
  { x: 36, nType: true, gate: false },
  { x: 64, nType: false, gate: false },
  { x: 74, nType: false, gate: true },
  { x: 84, nType: false, gate: false },
];
export const contactAt = (x: number, y: number) =>
  terminals.find(
    (terminal) =>
      x >= terminal.x - 2 &&
      x < terminal.x + 2 &&
      y >= (terminal.gate ? 6 : 20) &&
      y < (terminal.gate ? 10 : 26),
  );
export const activeSilicon = (x: number) =>
  (x >= 2 && x < 40) || (x >= 60 && x < 98);
export const gateRegion = (x: number) =>
  (x >= 23 && x < 29) || (x >= 71 && x < 77);
export const maskOpens = (mask: MaskId, x: number, y: number) => {
  switch (mask) {
    case "well":
      return x >= 55;
    case "isolation":
      return !activeSilicon(x);
    case "gate":
      return !gateRegion(x);
    case "n":
      return x >= 12 && x < 40 && y >= 12 && y < 53;
    case "p":
      return x >= 60 && x < 88 && y >= 12 && y < 53;
    case "contact":
      return !!contactAt(x, y);
    case "metal":
      return !onMetalTrack(x, y, firstMetalTracks);
    case "via":
      return x >= 48 && x < 52 && y >= 21 && y < 25;
    case "upper":
      return !onMetalTrack(x, y, upperMetalTracks);
  }
};

export const maskMeshes: Record<MaskId, { xs: number[]; ys: number[] }> = {
  well: { xs: [0, 55, 100], ys: [0, 65] },
  isolation: { xs: [0, 2, 40, 60, 98, 100], ys: [0, 65] },
  gate: { xs: [0, 2, 23, 29, 40, 60, 71, 77, 98, 100], ys: [0, 65] },
  n: {
    xs: [0, 2, 12, 23, 29, 40, 60, 71, 77, 90, 98, 100],
    ys: [0, 12, 53, 65],
  },
  p: {
    xs: [0, 2, 10, 23, 29, 40, 60, 71, 77, 88, 98, 100],
    ys: [0, 12, 53, 65],
  },
  contact: {
    xs: [0, 4, 8, 14, 18, 24, 28, 34, 38, 62, 66, 72, 76, 82, 86, 92, 96, 100],
    ys: [0, 6, 10, 20, 26, 65],
  },
  metal: {
    xs: [0, 4, 14, 18, 24, 34, 48, 52, 66, 76, 82, 86, 96, 100],
    ys: [0, 6, 10, 20, 26, 34, 65],
  },
  via: { xs: [0, 48, 52, 100], ys: [0, 21, 25, 65] },
  upper: { xs: [0, 48, 52, 92, 100], ys: [0, 4, 25, 65] },
};

export const exposureRegions = (mask: MaskId, ymax = 65): Rectangle[] => {
  const mesh = maskMeshes[mask];
  const regions: Rectangle[] = [];
  let previous = new Map<string, number>();

  for (let row = 0; row < mesh.ys.length - 1; row++) {
    const y = mesh.ys[row];
    const y1 = Math.min(mesh.ys[row + 1], ymax);
    if (y >= y1) break;

    const current = new Map<string, number>();
    let start: number | undefined;
    for (let col = 0; col < mesh.xs.length - 1; col++) {
      const open = maskOpens(mask, mesh.xs[col], y);
      if (open && start === undefined) start = mesh.xs[col];
      if (start === undefined) continue;
      if (open && col < mesh.xs.length - 2) continue;

      const end = open ? mesh.xs[col + 1] : mesh.xs[col];
      const key = `${start}-${end}`;
      const existing = previous.get(key);
      const index = existing ?? regions.length;
      regions[index] = [
        start,
        end,
        existing === undefined ? y : regions[index][2],
        y1,
      ];
      current.set(key, index);
      start = undefined;
    }
    previous = current;
  }

  return regions;
};

export const contactEtchHeight = (bottom: number, progress: number) =>
  14 + (bottom - 14) * clamp(progress);
export const upperInsulatorHeight = (
  x: number,
  y: number,
  state: PatternState,
) => {
  const raised = onMetalTrack(x, y, firstMetalTracks) ? 4 * state.metal : 0;

  return 27 + raised - (2 + raised) * state.polish;
};
export const fieldOxideProfile = (x: number, growth = 1) => {
  if (growth <= 0) return activeSilicon(x) ? 0 : 1;

  const distance = Math.min(
    Math.abs(x - 2),
    Math.abs(x - 40),
    Math.abs(x - 60),
    Math.abs(x - 98),
  );
  const signedDistance = activeSilicon(x) ? distance : -distance;
  const reach = 3 * growth;

  return ease((reach - signedDistance) / (2 * reach));
};
export const fieldOxideGrowth = (x: number, state: PatternState) =>
  8 * state.isolation * fieldOxideProfile(x, state.isolation);
export const insulationThickness = (
  x: number,
  _y: number,
  state: PatternState,
) =>
  5 * state.oxide * (1 - state.padOxideStrip) +
  fieldOxideGrowth(x, state) +
  1.8 * state.gateOxide * (1 - fieldOxideProfile(x, state.isolation));
export const siliconSurfaceHeight = (
  x: number,
  _y: number,
  state: PatternState,
) =>
  -2 * state.oxide -
  0.44 * fieldOxideGrowth(x, state) -
  0.8 * state.gateOxide * (1 - fieldOxideProfile(x, state.isolation));
export const nitrideThickness = (x: number, state: PatternState) =>
  6 *
  state.nitride *
  (1 - state.nitrideStrip) *
  (activeSilicon(x) ? 1 : 1 - state.prepareIsolation);
export const isolationProfileXs = [
  ...new Set([
    0,
    52,
    55,
    80,
    100,
    ...[2, 40, 60, 98].flatMap((edge) =>
      Array.from({ length: 25 }, (_, i) => edge - 3 + i * 0.25).filter(
        (x) => x >= 0 && x <= 100,
      ),
    ),
  ]),
].sort((a, b) => a - b);
export const deviceSurfaceHeight = (
  x: number,
  y: number,
  state: PatternState,
) =>
  siliconSurfaceHeight(x, y, state) +
  insulationThickness(x, y, state) +
  8 * state.poly * (gateRegion(x) ? 1 : 1 - state.patternGate);

export const contactInsulatorHeight = (
  x: number,
  y: number,
  state: PatternState,
) => {
  const deposited = deviceSurfaceHeight(x, y, state) + 20;

  return deposited + (14 - deposited) * state.contactPolish;
};

export const materialSurfaceHeight = (state: PatternState, x = 0, y = 0) => {
  const deviceTop =
    deviceSurfaceHeight(x, y, state) + nitrideThickness(x, state);
  const coveredTop =
    deviceTop + (contactInsulatorHeight(x, y, state) - deviceTop) * state.cover;
  const metalTop =
    coveredTop +
    3 *
      state.metal *
      (onMetalTrack(x, y, firstMetalTracks) ? 1 : 1 - state.metalPattern);
  const insulatedTop =
    metalTop +
    (upperInsulatorHeight(x, y, state) - metalTop) * state.interconnect;

  return (
    insulatedTop +
    3 *
      state.upperMetal *
      (onMetalTrack(x, y, upperMetalTracks) ? 1 : 1 - state.upperMetalPattern)
  );
};
export const resistTopHeight = (state: PatternState, mask: MaskId) => {
  const coated = mask === "gate" ? { ...state, patternGate: 0 } : state;

  return (
    Math.max(
      ...[
        [0, 0],
        [26, 8],
        [50, 23],
        [74, 8],
        [94, 23],
      ].map(([x, y]) => materialSurfaceHeight(coated, x, y)),
    ) + 9
  );
};

export const resistThickness = (
  state: PatternState,
  mask: MaskId,
  x: number,
  y: number,
  topHeight?: number,
) => {
  const amount = state[`${mask}Coat`] * (1 - state[`${mask}Strip`]);
  if (amount === 0) return 0;

  const retained = maskOpens(mask, x, y) ? 1 - state[`${mask}Develop`] : 1;
  if (retained === 0) return 0;

  return (
    Math.max(
      0,
      (topHeight ?? resistTopHeight(state, mask)) -
        materialSurfaceHeight(state, x, y),
    ) *
    amount *
    retained
  );
};

export const patternSurfaceHeight = (state: PatternState, x = 0, y = 0) =>
  materialSurfaceHeight(state, x, y) +
  maskCycles.reduce(
    (height, cycle) => height + resistThickness(state, cycle.id, x, y),
    0,
  );

export const filmVisibility = (thickness: number) => ease(thickness / 0.8);
export const sceneDuration = 6500;
