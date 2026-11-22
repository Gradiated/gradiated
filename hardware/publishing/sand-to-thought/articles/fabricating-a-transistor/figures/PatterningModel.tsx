import { useEffect, useId, useRef, useState } from "react";
import type { PointerEvent } from "react";
import {
  exposedResistColour,
  logicColours,
  materialColours,
  siliconColours,
} from "./materials";
import {
  activeSilicon,
  exposureLighting,
  exposureRegions,
  fieldOxideGrowth,
  filmVisibility,
  inverterOperation,
  firstMetalTracks,
  portion,
  upperInsulatorHeight,
  upperMetalTracks,
  onMetalTrack,
  contactEtchHeight,
  contactInsulatorHeight,
  stages,
  deviceSurfaceHeight,
  gateRegion,
  materialSurfaceHeight,
  maskOpens,
  maskMeshes,
  resistState,
  resistThickness,
  resistTopHeight,
  terminals,
  contactAt,
  insulationThickness,
  isolationProfileXs,
  nitrideThickness,
  siliconSurfaceHeight,
} from "./process";
import type { PatternState, Visit } from "./process";
import { maskCycles, steps } from "./sequence";
import { CloseupProcessEffects } from "./ProcessEffects";
import { ExposureBeams } from "./ExposureBeams";

import { surfaceContours } from "./surfaces";
import type { SurfacePoint as Point } from "./surfaces";
type RegionLabel = string | ((x: number, y: number) => string);
type Face = {
  points: Point[];
  contours?: Point[][];
  surface?: string;
  fill: string;
  depth: number;
  opacity: number;
  region: string;
};

const mix = (from: number, to: number, progress: number) =>
  from + (to - from) * progress;

export type CameraState = {
  elevation: number;
  section: number;
  scale?: number;
  centreY?: number;
  cutY?: number;
};

export const patterningCamera = (
  index: number,
  progress: number,
  from: CameraState,
) => {
  const viewChange = portion(progress, 0, 0.28);
  const step = steps[index];
  const angle =
    index === stages.layout || step.phase === "expose"
      ? 1.05
      : index >= stages.contactInsulation
        ? 0.65
        : 0.55;
  const elevation = mix(from.elevation, angle ?? 0.62, viewChange);
  const section = mix(
    from.section,
    index === 0 || index < stages.layout || index >= stages.develop ? 1 : 0,
    viewChange,
  );
  const cutY = mix(
    from.cutY ?? 34,
    index >= stages.via && index < stages.upperMetal ? 25 : 34,
    viewChange,
  );
  const ymax = mix(65, cutY, section);
  const yaw = mix(0.42, 0.08, section);
  const exposing = step.phase === "expose";
  const scale = mix(from.scale ?? 2.6, exposing ? 2.1 : 2.6, viewChange);
  const centreY = mix(from.centreY ?? 132, exposing ? 170 : 132, viewChange);
  const project = ([x, y, z]: Point) => {
    const u = (x - 50) * Math.cos(yaw) - (y - 32.5) * Math.sin(yaw);
    const v = (x - 50) * Math.sin(yaw) + (y - 32.5) * Math.cos(yaw);

    return [
      190 + u * scale,
      centreY + (v * Math.sin(elevation) - z * Math.cos(elevation)) * scale,
    ] as [number, number];
  };

  return { elevation, section, scale, centreY, cutY, ymax, yaw, project };
};

export const PatterningModel = ({
  index,
  progress,
  fromIndex,
  view,
  visit,
  state,
  input,
  embedded = false,
}: {
  index: number;
  progress: number;
  fromIndex: number;
  view: ReturnType<typeof patterningCamera>;
  visit: Visit;
  state: PatternState;
  input: number;
  embedded?: boolean;
}) => {
  const id = useId();
  const profileCache = useRef(
    new Map<number, { inputs: number[]; faces: Face[] }>(),
  );
  const hoveredRegion = useRef("");
  const [regionTip, setRegionTip] = useState<{
    label: string;
    x: number;
    y: number;
    scene: number;
  } | null>(null);
  useEffect(() => {
    hoveredRegion.current = "";
    setRegionTip(null);
  }, [index]);
  useEffect(() => {
    const dismiss = () => {
      hoveredRegion.current = "";
      setRegionTip(null);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismiss();
    };
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.removeEventListener("scroll", dismiss, true);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);
  const hideRegionTip = () => {
    hoveredRegion.current = "";
    setRegionTip(null);
  };
  const showRegionTip = (event: PointerEvent<HTMLDivElement>) => {
    const target = event.target as Element;
    const label =
      target.closest("[data-region]")?.getAttribute("data-region") ?? "";
    const key = `${index}:${label}`;
    if (hoveredRegion.current === key) return;

    hoveredRegion.current = key;
    if (!label) {
      setRegionTip(null);
      return;
    }

    const bounds = event.currentTarget.getBoundingClientRect();
    setRegionTip({
      label,
      x: Math.max(
        8,
        Math.min(bounds.width - 208, event.clientX - bounds.left + 12),
      ),
      y: Math.max(4, event.clientY - bounds.top - 40),
      scene: index,
    });
  };
  const { elevation, section, ymax, yaw, project } = view;
  const lighting = exposureLighting(visit);
  const implanted = Math.max(state.implantN, state.implantP);
  const crystalDamage = Math.max(
    state.well * (1 - state.wellAnneal),
    implanted * (1 - state.anneal),
  );
  const crystalRepair = Math.max(
    state.wellAnneal * (1 - implanted),
    state.anneal,
  );
  const path = (points: Point[], close = true) =>
    points
      .map(
        (point, i) =>
          `${i ? "L" : "M"}${project(point)
            .map((n) => n.toFixed(2))
            .join(" ")}`,
      )
      .join(" ") + (close ? "Z" : "");
  const faces: Face[] = [];
  let layerOrder = 0;
  let profileOrder = 0;
  let faceOpacity = 1;
  let faceRegion = "";
  let faceSurface: string | undefined;
  const addFace = (points: Point[], fill: string, opacity = 1) => {
    const depth =
      points.reduce(
        (sum, [x, y, z]) =>
          sum +
          (x * Math.sin(yaw) + y * Math.cos(yaw)) * Math.cos(elevation) +
          z * Math.sin(elevation),
        0,
      ) / points.length;
    faces.push({
      points,
      fill,
      depth: depth + layerOrder * 1000,
      opacity: opacity * faceOpacity,
      region: faceRegion,
      surface: faceSurface,
    });
  };
  const layer = (
    xs: number[],
    ys: number[],
    base: number | ((col: number, row: number) => number),
    height: (x: number, y: number) => number,
    colours: [string, string, string],
    expose: boolean | ((col: number, row: number) => number) = false,
    opacity = 1,
    region: RegionLabel = "Silicon",
  ) => {
    layerOrder += 1;
    if (opacity <= 0) return;

    for (let row = 0; row < ys.length - 1; row++) {
      for (let col = 0; col < xs.length - 1; col++) {
        const x0 = xs[col],
          x1 = xs[col + 1],
          y0 = ys[row],
          y1 = ys[row + 1];
        const h = height(col, row);
        if (h < 0.001 || y1 <= y0) continue;

        const bottom = typeof base === "number" ? base : base(col, row);
        faceOpacity = opacity * (layerOrder === 1 ? 1 : filmVisibility(h));
        faceRegion =
          typeof region === "function"
            ? region((x0 + x1) / 2, (y0 + y1) / 2)
            : region;
        const top = bottom + h;
        const exposure = typeof expose === "function" ? expose(col, row) : 0;
        addFace(
          [
            [x0, y0, top],
            [x1, y0, top],
            [x1, y1, top],
            [x0, y1, top],
          ],
          exposure > 0
            ? exposedResistColour(exposure, lighting.glow)
            : colours[0],
        );
        const neighbour = (col: number, row: number) => {
          if (
            col < 0 ||
            row < 0 ||
            col >= xs.length - 1 ||
            row >= ys.length - 1
          )
            return 0;

          const neighbourBase =
            typeof base === "number" ? base : base(col, row);

          return Math.max(0, neighbourBase + height(col, row) - bottom);
        };
        const left = neighbour(col - 1, row);
        const right = neighbour(col + 1, row);
        const back = neighbour(col, row - 1);
        const front = neighbour(col, row + 1);
        if (h > left)
          addFace(
            [
              [x0, y0, bottom + left],
              [x0, y1, bottom + left],
              [x0, y1, top],
              [x0, y0, top],
            ],
            colours[1],
          );
        if (h > right)
          addFace(
            [
              [x1, y0, bottom + right],
              [x1, y1, bottom + right],
              [x1, y1, top],
              [x1, y0, top],
            ],
            colours[1],
          );
        if (h > back)
          addFace(
            [
              [x0, y0, bottom + back],
              [x1, y0, bottom + back],
              [x1, y0, top],
              [x0, y0, top],
            ],
            colours[2],
          );
        if (h > front)
          addFace(
            [
              [x0, y1, bottom + front],
              [x1, y1, bottom + front],
              [x1, y1, top],
              [x0, y1, top],
            ],
            colours[2],
          );
      }
    }
  };
  const profileLayer = (
    xs: number[],
    ys: number[],
    baseAt: (x: number, y: number) => number,
    heightAt: (x: number, y: number) => number,
    colours: [string, string, string],
    opacity: number,
    region: RegionLabel,
    exposureAt?: (x: number, y: number) => number,
    fadeGroupAt?: (x: number, y: number) => string | number | boolean,
    drawTopLast = false,
    dependencies?: number[],
  ) => {
    layerOrder += 1;
    if (opacity <= 0) return;

    const profile = profileOrder++;
    const inputs = dependencies && [
      layerOrder,
      ymax,
      yaw,
      elevation,
      opacity,
      ...dependencies,
    ];
    const cached = profileCache.current.get(profile);
    if (
      inputs &&
      cached &&
      inputs.length === cached.inputs.length &&
      inputs.every((value, i) => value === cached.inputs[i])
    ) {
      faces.push(...cached.faces);
      return;
    }

    const firstFace = faces.length;
    const regionAt = (x: number, y: number) =>
      typeof region === "function" ? region(x, y) : region;
    const fadeGroup = (x: number, y: number) =>
      JSON.stringify([regionAt(x, y), fadeGroupAt?.(x, y)]);
    const thicknessByGroup = new Map<string, number>();
    for (let row = 0; row < ys.length - 1; row++) {
      for (let col = 0; col < xs.length - 1; col++) {
        const x = (xs[col] + xs[col + 1]) / 2;
        const y = (ys[row] + ys[row + 1]) / 2;
        const group = fadeGroup(x, y);
        thicknessByGroup.set(
          group,
          Math.max(thicknessByGroup.get(group) ?? 0, heightAt(x, y)),
        );
      }
    }
    for (let row = 0; row < ys.length - 1; row++) {
      for (let col = 0; col < xs.length - 1; col++) {
        const x0 = xs[col],
          x1 = xs[col + 1];
        const y0 = ys[row],
          y1 = ys[row + 1];
        const epsilon = 0.00001;
        const samples = [
          [x0 + epsilon, y0 + epsilon],
          [x1 - epsilon, y0 + epsilon],
          [x1 - epsilon, y1 - epsilon],
          [x0 + epsilon, y1 - epsilon],
        ];
        const corners = [
          [x0, y0],
          [x1, y0],
          [x1, y1],
          [x0, y1],
        ];
        const atCorner = (
          sample: (x: number, y: number) => number,
          i: number,
        ) => {
          const exact = sample(corners[i][0], corners[i][1]);
          const inside = sample(samples[i][0], samples[i][1]);

          return Math.abs(exact - inside) < 0.001 ? exact : inside;
        };
        const heights = samples.map((_, i) => atCorner(heightAt, i));
        if (Math.max(...heights) < 0.001) continue;

        const bases = samples.map((_, i) => atCorner(baseAt, i));
        const tops = bases.map((base, i) => base + heights[i]);
        const centreX = (x0 + x1) / 2;
        const centreY = (y0 + y1) / 2;
        faceOpacity =
          opacity *
          filmVisibility(
            thicknessByGroup.get(fadeGroup(centreX, centreY)) ?? 0,
          );
        faceRegion = regionAt(centreX, centreY);
        faceSurface = "top";
        const exposure = exposureAt?.((x0 + x1) / 2, (y0 + y1) / 2) ?? 0;
        addFace(
          corners.map(([x, y], i) => [x, y, tops[i]] as Point),
          exposure > 0
            ? exposedResistColour(exposure, lighting.glow)
            : colours[0],
        );

        const edges = [
          {
            a: 0,
            b: 1,
            dx: 0,
            dy: -epsilon,
            outside: row === 0,
            colour: colours[2],
          },
          {
            a: 1,
            b: 2,
            dx: epsilon,
            dy: 0,
            outside: col === xs.length - 2,
            colour: colours[1],
          },
          {
            a: 2,
            b: 3,
            dx: 0,
            dy: epsilon,
            outside: row === ys.length - 2,
            colour: colours[2],
          },
          {
            a: 3,
            b: 0,
            dx: -epsilon,
            dy: 0,
            outside: col === 0,
            colour: colours[1],
          },
        ];
        for (const { a, b, dx, dy, outside, colour } of edges) {
          const floor = (i: number) => {
            if (outside) return bases[i];

            const [x, y] = samples[i];
            const neighbourX = x + dx * 2,
              neighbourY = y + dy * 2;

            return Math.max(
              bases[i],
              baseAt(neighbourX, neighbourY) + heightAt(neighbourX, neighbourY),
            );
          };
          const lowA = Math.min(tops[a], floor(a));
          const lowB = Math.min(tops[b], floor(b));
          if (tops[a] - lowA < 0.001 && tops[b] - lowB < 0.001) continue;

          faceSurface =
            dx < 0 ? "left" : dx > 0 ? "right" : dy < 0 ? "back" : "front";
          addFace(
            [
              [corners[a][0], corners[a][1], lowA],
              [corners[b][0], corners[b][1], lowB],
              [corners[b][0], corners[b][1], tops[b]],
              [corners[a][0], corners[a][1], tops[a]],
            ],
            colour,
          );
        }
      }
    }
    faceSurface = undefined;
    const layerFaces = faces.splice(firstFace);
    const topHeight = drawTopLast
      ? layerFaces.reduce(
          (height, face) =>
            Math.max(height, ...face.points.map(([, , z]) => z)),
          -Infinity,
        )
      : 0;
    const topDepth = drawTopLast
      ? layerFaces.reduce(
          (depth, face) => Math.max(depth, face.depth + 1),
          -Infinity,
        )
      : 0;
    const patches = new Map<string, Face[]>();
    for (const face of layerFaces) {
      const key = JSON.stringify([
        face.surface,
        face.fill,
        face.opacity,
        face.region,
      ]);
      if (!patches.has(key)) patches.set(key, []);
      patches.get(key)!.push(face);
    }
    for (const patch of patches.values()) {
      const contours = surfaceContours(patch.map(({ points }) => points));
      const points = contours.flat();
      const flatTop =
        drawTopLast &&
        patch[0].surface === "top" &&
        points.every(([, , z]) => Math.abs(z - topHeight) < 0.001);
      faces.push({
        ...patch[0],
        points,
        contours,
        depth: flatTop
          ? topDepth
          : patch.reduce((sum, face) => sum + face.depth, 0) / patch.length,
      });
    }
    if (inputs) {
      profileCache.current.set(profile, {
        inputs,
        faces: faces.slice(firstFace),
      });
    }
  };
  const siliconTop = (x: number, y: number) =>
    siliconSurfaceHeight(x, y, state);
  const oxideBase = siliconTop(16, 23);
  const geometryXs = [
    ...new Set([
      ...isolationProfileXs,
      8,
      10,
      12,
      14,
      18,
      23,
      24,
      28,
      29,
      34,
      66,
      71,
      72,
      76,
      77,
      82,
      86,
      88,
      90,
      92,
    ]),
  ].sort((a, b) => a - b);
  const geometryYs = [...new Set([0, 6, 10, 12, 20, 26, 53, ymax])]
    .filter((y) => y <= ymax)
    .sort((a, b) => a - b);
  const surfaceXs = isolationProfileXs;
  const surfaceYs = [...new Set([0, 12, 53, ymax])]
    .filter((y) => y <= ymax)
    .sort((a, b) => a - b);
  const gateXs = [...new Set([...surfaceXs, 23, 29, 71, 77])].sort(
    (a, b) => a - b,
  );
  const box = (
    x0: number,
    x1: number,
    y0: number,
    y1: number,
    bottom: number,
    height: number,
    colours: [string, string, string],
    opacity = 1,
    region = "Metal contact",
  ) => {
    if (y0 >= ymax || height <= 0 || opacity <= 0) return;

    layer(
      [x0, x1],
      [y0, Math.min(y1, ymax)],
      bottom,
      () => height,
      colours,
      false,
      opacity,
      region,
    );
  };
  const siliconProfile = [state.oxide, state.isolation, state.gateOxide];
  profileLayer(
    surfaceXs,
    surfaceYs,
    () => -20,
    (x, y) => 20 + siliconTop(x, y),
    [siliconColours.top, siliconColours.side, siliconColours.front],
    1,
    "p-type silicon substrate",
    undefined,
    undefined,
    false,
    siliconProfile,
  );
  const wellXs = surfaceXs.filter((x) => x >= 55);
  profileLayer(
    wellXs,
    surfaceYs,
    () => -16,
    (x, y) => 16 + siliconTop(x, y),
    materialColours.well,
    state.well,
    "n-well",
    undefined,
    undefined,
    false,
    siliconProfile,
  );
  terminals
    .filter((terminal) => !terminal.gate)
    .forEach(({ x, nType }) => {
      const bounds: Record<number, [number, number]> = {
        16: [12, 23],
        36: [29, 40],
        64: [60, 71],
        84: [77, 88],
      };
      box(
        bounds[x][0],
        bounds[x][1],
        12,
        53,
        -9,
        9 + oxideBase,
        nType ? materialColours.n : materialColours.p,
        nType ? state.implantN : state.implantP,
        `${nType ? "n" : "p"}-doped ${x === 16 || x === 84 ? "source" : "drain"}`,
      );
    });
  const insulator = materialColours.insulator;
  const gateColours = materialColours.gate;
  const metalColours = materialColours.metal;
  const metalBase = 14;
  const metalThickness = 3;
  const insulationHeight = (x: number, y: number) =>
    insulationThickness(x, y, state);
  const deviceTop = (x: number, y: number) => deviceSurfaceHeight(x, y, state);
  const contactXs = [
    ...new Set([
      ...geometryXs,
      ...terminals.flatMap(({ x }) => [x - 2, x + 2]),
    ]),
  ].sort((a, b) => a - b);
  const contactYs = geometryYs;
  const dielectricXs = state.contacts > 0 ? contactXs : surfaceXs;
  const dielectricYs = state.contacts > 0 ? contactYs : surfaceYs;
  const coverXs = state.contacts > 0 ? contactXs : gateXs;
  const coverYs = state.contacts > 0 ? contactYs : surfaceYs;

  const oxideProfile = [
    state.oxide,
    state.padOxideStrip,
    state.isolation,
    state.gateOxide,
  ];
  const gateProfile = [...oxideProfile, state.poly, state.patternGate];
  const materialProfile = [
    ...gateProfile,
    state.nitride,
    state.nitrideStrip,
    state.prepareIsolation,
    state.cover,
    state.contactPolish,
    state.metal,
    state.metalPattern,
    state.interconnect,
    state.polish,
    state.upperMetal,
    state.upperMetalPattern,
  ];

  profileLayer(
    dielectricXs,
    dielectricYs,
    siliconTop,
    (x, y) => {
      const hole = contactAt(x, y);
      const thickness = insulationHeight(x, y);
      if (!hole || hole.gate) return thickness;

      const bottom = siliconTop(x, y);

      return Math.min(
        thickness,
        contactEtchHeight(bottom, state.contacts) - bottom,
      );
    },
    insulator,
    1,
    (x) =>
      fieldOxideGrowth(x, state) > 0.001
        ? "Field oxide · insulator"
        : activeSilicon(x) && state.gateOxide > 0
          ? "Gate oxide · insulator"
          : state.nitride > 0
            ? "Thin oxide · insulator"
            : "Screen oxide · insulator",
    undefined,
    undefined,
    false,
    [...oxideProfile, state.contacts, state.nitride],
  );
  profileLayer(
    surfaceXs,
    surfaceYs,
    (x, y) => siliconTop(x, y) + insulationHeight(x, y),
    (x) => nitrideThickness(x, state),
    materialColours.nitride,
    1,
    "Silicon nitride · temporary oxidation barrier",
    undefined,
    (x) => activeSilicon(x),
    false,
    [
      ...oxideProfile,
      state.nitride,
      state.nitrideStrip,
      state.prepareIsolation,
    ],
  );
  profileLayer(
    gateXs,
    surfaceYs,
    (x, y) => siliconTop(x, y) + insulationHeight(x, y),
    (x) => 8 * state.poly * (gateRegion(x) ? 1 : 1 - state.patternGate),
    gateColours,
    1,
    state.patternGate > 0.5
      ? "Polysilicon gate electrode"
      : "Polysilicon layer",
    undefined,
    (x) => gateRegion(x),
    false,
    gateProfile,
  );
  profileLayer(
    coverXs,
    coverYs,
    deviceTop,
    (x, y) => {
      const hole = contactAt(x, y);
      const base = deviceTop(x, y);
      const target = hole?.gate ? base : siliconTop(x, y);
      const top =
        hole && state.contacts > 0
          ? contactEtchHeight(target, state.contacts)
          : contactInsulatorHeight(x, y, state);

      return Math.max(0, top - base) * state.cover;
    },
    insulator,
    0.46,
    "Insulating silicon dioxide",
    undefined,
    (x, y) => contactAt(x, y)?.x ?? "unetched",
    false,
    [...gateProfile, state.contacts, state.cover, state.contactPolish],
  );
  terminals.forEach(({ x, gate, nType }) => {
    const bottom = gate ? deviceTop(x, 6) : siliconTop(x, 20);
    box(
      x - 2,
      x + 2,
      gate ? 6 : 20,
      gate ? 10 : 26,
      bottom,
      (14 - bottom) * state.metalFill,
      metalColours,
      1,
      gate
        ? "Gate contact"
        : `${nType ? "n-type" : "p-type"} ${x === 16 || x === 84 ? "source" : "drain"} contact`,
    );
  });
  const metalXs = [
    ...new Set([0, 100, ...firstMetalTracks.flatMap(([a, b]) => [a, b])]),
  ].sort((a, b) => a - b);
  const metalYs = [
    ...new Set([0, ymax, ...firstMetalTracks.flatMap(([, , a, b]) => [a, b])]),
  ]
    .filter((y) => y <= ymax)
    .sort((a, b) => a - b);
  layer(
    metalXs,
    metalYs,
    metalBase,
    (col, row) =>
      metalThickness *
      state.metal *
      (onMetalTrack(metalXs[col], metalYs[row], firstMetalTracks)
        ? 1
        : 1 - state.metalPattern),
    metalColours,
    false,
    1,
    (x, y) => {
      if (state.metalPattern < 0.5) return "Deposited metal";
      if (x >= 14 && x <= 18) return "0 V metal connection";
      if (x >= 82 && x <= 86) return "+1 V metal connection";
      return y <= 10 ? "Input metal connection" : "Output metal connection";
    },
  );
  const upperXs = [
    ...new Set([
      0,
      48,
      52,
      100,
      ...firstMetalTracks.flatMap(([x0, x1]) => [x0, x1]),
    ]),
  ].sort((a, b) => a - b);
  const upperYs = [
    ...new Set([
      0,
      21,
      25,
      ymax,
      ...firstMetalTracks.flatMap(([, , y0, y1]) => [y0, y1]),
    ]),
  ]
    .filter((y) => y <= ymax)
    .sort((a, b) => a - b);
  const viaCell = (col: number, row: number) =>
    upperXs[col] >= 48 &&
    upperXs[col] < 52 &&
    upperYs[row] >= 21 &&
    upperYs[row] < 25;
  layer(
    upperXs,
    upperYs,
    (col, row) =>
      onMetalTrack(upperXs[col], upperYs[row], firstMetalTracks) ? 17 : 14,
    (col, row) => {
      const hole = viaCell(col, row);
      const bottom = onMetalTrack(upperXs[col], upperYs[row], firstMetalTracks)
        ? 17
        : 14;
      const height =
        upperInsulatorHeight(upperXs[col], upperYs[row], state) - bottom;

      return height * state.interconnect * (hole ? 1 - state.viaOpen : 1);
    },
    insulator,
    false,
    0.34,
    "Insulation between metal layers",
  );
  box(
    48,
    52,
    21,
    25,
    17,
    8 * state.viaFill,
    metalColours,
    1,
    "Metal via · between wiring levels",
  );
  layer(
    [0, 48, 52, 92, 100],
    [0, 4, 25, ymax].filter((y) => y <= ymax),
    25,
    (col, row) =>
      3 *
      state.upperMetal *
      (onMetalTrack([0, 48, 52, 92][col], [0, 4, 25][row], upperMetalTracks)
        ? 1
        : 1 - state.upperMetalPattern),
    metalColours,
    false,
    1,
    "Upper metal interconnect",
  );
  maskCycles.forEach((cycle) => {
    const resist = resistState(state, cycle.id);
    if (resist.amount <= 0.001) return;

    const topHeight = resistTopHeight(state, cycle.id);
    const mesh = maskMeshes[cycle.id];
    const xs = [...new Set([...mesh.xs, ...isolationProfileXs])].sort(
      (a, b) => a - b,
    );
    const ys = [...new Set([...mesh.ys.filter((y) => y < ymax), ymax])].sort(
      (a, b) => a - b,
    );
    profileLayer(
      xs,
      ys,
      (x, y) => materialSurfaceHeight(state, x, y),
      (x, y) => resistThickness(state, cycle.id, x, y, topHeight),
      materialColours.resist,
      1,
      "Photoresist · temporary mask",
      (x, y) => (maskOpens(cycle.id, x, y) ? resist.expose : 0),
      (x, y) => maskOpens(cycle.id, x, y),
      true,
      [
        ...materialProfile,
        resist.amount,
        resist.expose,
        resist.develop,
        lighting.glow,
        maskCycles.indexOf(cycle),
      ],
    );
  });
  faces.sort((a, b) => a.depth - b.depth);
  const step = steps[index];
  const cycle = maskCycles.find((cycle) => cycle.id === step.mask);
  const currentResist = cycle ? resistState(state, cycle.id) : undefined;
  const beamRegions = cycle ? exposureRegions(cycle.id, ymax) : [];
  const targetWell =
    index === stages.growOxide
      ? portion(visit.process, 0.85, 1)
      : fromIndex === stages.growOxide
        ? 1 - portion(progress, 0, 0.18)
        : 0;
  const electrical = inverterOperation(input, progress);
  const supplyColour = input ? logicColours.low : logicColours.high;
  const inputColour = input ? logicColours.high : logicColours.low;
  const supplyX = input ? 16 : 84;
  const drainX = input ? 36 : 64;
  const outputY = 34;
  const wireTop = metalBase + metalThickness * state.metal;
  const trace = (
    name: string,
    points: Point[],
    colour: string,
    amount: number,
  ) => (
    <g
      key={name}
      data-voltage-path={name}
      opacity={amount > 0 ? 1 : 0}
      fill="none"
      stroke={colour}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray="1"
      strokeDashoffset={1 - amount}
    >
      <path
        d={path(points, false)}
        pathLength="1"
        strokeWidth="8"
        opacity=".18"
      />
      <path d={path(points, false)} pathLength="1" strokeWidth="3" />
    </g>
  );
  const camera =
    section > 0.5 ? "Cutaway" : elevation > 1 ? "Top view" : "3D view";

  const drawing = (
    <>
      <defs>
        <clipPath id={`${id}-beam-clip`}>
          <rect x="0" y="8" width="380" height="240" />
        </clipPath>
        <pattern
          id={`${id}-section`}
          width="7"
          height="7"
          patternUnits="userSpaceOnUse"
        >
          <path
            d="M0 7 7 0"
            stroke={siliconColours.hatch}
            strokeWidth={0.6 + crystalRepair * 0.3}
            strokeDasharray={`${10 - crystalDamage * 8} ${crystalDamage * 3}`}
          />
        </pattern>
      </defs>
      {!embedded ? (
        <ellipse
          cx="190"
          cy="225"
          rx="127"
          ry="15"
          fill="var(--fab-object-shadow, #dcd4c5)"
          opacity=".32"
        />
      ) : null}
      {faces.map((face, i) => (
        <path
          key={i}
          d={(face.contours ?? [face.points])
            .map((points) => path(points))
            .join(" ")}
          data-region={face.opacity > 0.5 ? face.region : undefined}
          aria-label={face.region}
          fill={face.fill}
          opacity={face.opacity}
          stroke={face.fill}
          strokeWidth=".45"
          strokeLinejoin="round"
        />
      ))}
      {section > 0.05 ? (
        <path
          d={path([
            [0, ymax, -20],
            [100, ymax, -20],
            ...[...geometryXs]
              .reverse()
              .map((x) => [x, ymax, siliconTop(x, ymax - 0.001)] as Point),
          ])}
          fill={`url(#${id}-section)`}
          data-crystal-repair={crystalRepair}
          opacity={section * (0.26 + crystalRepair * 0.48)}
        />
      ) : null}
      {targetWell > 0 ? (
        <g opacity={targetWell} data-target-well="true">
          <path
            d={path([
              [55, 0, materialSurfaceHeight(state, 55, 0) + 0.3],
              [100, 0, materialSurfaceHeight(state, 100, 0) + 0.3],
              [100, ymax, materialSurfaceHeight(state, 100, ymax) + 0.3],
              [55, ymax, materialSurfaceHeight(state, 55, ymax) + 0.3],
            ])}
            fill={materialColours.well[0]}
            fillOpacity=".15"
            stroke="#8a7993"
            strokeWidth=".8"
            strokeDasharray="3 3"
          />
          <text
            x={project([77, 17, 2])[0]}
            y={project([77, 17, 2])[1]}
            fontSize="9"
            textAnchor="middle"
            fill="#746982"
          >
            Target n-well region
          </text>
        </g>
      ) : null}
      {index >= stages.via && index < stages.upperMetal && state.viaOpen > 0 ? (
        <g data-via-floor={25 - 8 * state.viaOpen} opacity={state.viaOpen}>
          <path
            d={path([
              [48, 21, 25 - 8 * state.viaOpen],
              [52, 21, 25 - 8 * state.viaOpen],
              [52, 25, 25 - 8 * state.viaOpen],
              [48, 25, 25 - 8 * state.viaOpen],
            ])}
            fill="var(--signal-stroke)"
            fillOpacity=".22"
            stroke="var(--signal-stroke)"
            strokeWidth=".8"
          />
          <path
            d={path(
              [
                [48, 25, 25],
                [48, 25, 25 - 8 * state.viaOpen],
              ],
              false,
            )}
            fill="none"
            stroke="var(--signal-stroke)"
            strokeWidth=".7"
          />
        </g>
      ) : null}
      {lighting.beam > 0 && cycle ? (
        <g
          opacity={lighting.beam}
          data-exposure-beam={cycle.id}
          clipPath={`url(#${id}-beam-clip)`}
        >
          <ExposureBeams
            regions={beamRegions}
            surfaceHeight={(x, y) =>
              materialSurfaceHeight(state, x, y) +
              resistThickness(state, cycle.id, x, y)
            }
            project={project}
          />
        </g>
      ) : null}
      {visit.working &&
      (visit.machine === "furnace" || visit.machine === "anneal") ? (
        <g
          stroke="#cf9665"
          fill="none"
          opacity={Math.sin(Math.PI * visit.process) * 0.5}
        >
          {[125, 190, 255].map((x) => (
            <path key={x} d={`M${x} 70q-10-12 0-23t0-23`} strokeWidth="1.4" />
          ))}
        </g>
      ) : null}
      <g clipPath={`url(#${id}-beam-clip)`}>
        <CloseupProcessEffects
          index={index}
          visit={visit}
          state={state}
          project={project}
          ymax={ymax}
        />
      </g>
      {index >= stages.well && index <= stages.anneal ? (
        <g fontSize="9" textAnchor="middle" fill={siliconColours.label}>
          <text x={project([24, ymax, -17])[0]} y={project([24, ymax, -17])[1]}>
            p-type silicon
          </text>
          <text
            opacity={state.well}
            x={project([77, ymax, -13])[0]}
            y={project([77, ymax, -13])[1]}
          >
            n-well
          </text>
        </g>
      ) : null}
      {index >= stages.implant && index <= stages.anneal ? (
        <g
          opacity={Math.max(state.implantN, state.implantP)}
          fontSize="6.5"
          textAnchor="middle"
          fill={siliconColours.label}
        >
          {[16, 36, 64, 84].map((x) => {
            const point = project([x, ymax, -7]);

            return (
              <text
                key={x}
                x={point[0]}
                y={point[1]}
                opacity={x < 50 ? state.implantN : state.implantP}
              >
                {x < 50 ? "n-doped" : "p-doped"}
              </text>
            );
          })}
        </g>
      ) : null}
      {index === 0 || index === stages.inverter ? (
        <g
          data-inverter-input={input}
          data-inverter-output={electrical.output ?? "settling"}
        >
          {([16, 84] as const).map((x) => {
            const colour = x === 16 ? logicColours.low : logicColours.high;
            const points: Point[] = [
              [x, -9, wireTop],
              [x, 23, wireTop],
            ];
            const label = project([x, -9, wireTop]);

            return (
              <g key={x}>
                <path
                  d={path(points, false)}
                  fill="none"
                  stroke={materialColours.metal[1]}
                  strokeWidth="1.2"
                />
                {trace(`supply-${x}`, points, colour, electrical.supply)}
                <text
                  x={label[0]}
                  y={label[1] - 7}
                  textAnchor="middle"
                  fontSize="13"
                  fill={colour}
                >
                  {x === 16 ? "0 V" : "+1 V"}
                </text>
              </g>
            );
          })}
          {trace(
            "input",
            [
              [50, 0, wireTop],
              [50, 8, wireTop],
            ],
            inputColour,
            electrical.input,
          )}
          {[26, 74].map((x) => (
            <g key={x}>
              {trace(
                `gate-${x}`,
                [
                  [50, 8, wireTop],
                  [x, 8, wireTop],
                  [x, 8, deviceTop(x, 8) + 0.3],
                ],
                inputColour,
                electrical.gates,
              )}
              {[0, ymax].map((y) =>
                trace(
                  `electrode-${x}-${y}`,
                  [
                    [x, 8, deviceTop(x, 8) + 0.3],
                    [x, y, deviceTop(x, y) + 0.3],
                  ],
                  inputColour,
                  electrical.electrodes,
                ),
              )}
            </g>
          ))}
          {trace(
            "conducting-transistor",
            [
              [supplyX, 23, wireTop],
              [supplyX, 23, oxideBase - 5.5],
              [drainX, 23, oxideBase - 5.5],
              [drainX, 23, wireTop],
            ],
            supplyColour,
            electrical.transfer,
          )}
          {trace(
            "output-junction",
            [
              [drainX, 23, wireTop],
              [50, 23, wireTop],
            ],
            supplyColour,
            electrical.outputRail,
          )}
          {trace(
            "output-exit",
            [
              [50, 23, wireTop],
              [50, outputY, wireTop],
            ],
            supplyColour,
            electrical.exit,
          )}
          {(
            [
              [50, 0, `Input = ${input}`, inputColour, -13],
              [
                50,
                outputY,
                `Output = ${electrical.output ?? "…"}`,
                electrical.output === undefined ? "#514e47" : supplyColour,
                12,
              ],
            ] as [number, number, string, string, number][]
          ).map(([x, y, label, colour, offset]) => {
            const point = project([x, y, 20]);

            return (
              <text
                key={label}
                x={point[0]}
                y={y === outputY ? 211 : point[1] + offset}
                textAnchor="middle"
                fontSize="12"
                fill={colour}
              >
                {label}
              </text>
            );
          })}
          {[26, 74].map((x) => (
            <text
              key={x}
              x={project([x, 23, 0])[0]}
              y="233"
              textAnchor="middle"
              fontSize="11"
              fill={
                (x === 26 ? input === 1 : input === 0)
                  ? supplyColour
                  : "#8e8271"
              }
              opacity={electrical.electrodes}
            >
              {x === 26 ? "n-type" : "p-type"}{" "}
              {(x === 26 ? input === 1 : input === 0) ? "on" : "off"}
            </text>
          ))}
        </g>
      ) : null}
    </>
  );

  if (embedded) return <g data-embedded-inverter="true">{drawing}</g>;

  return (
    <div
      className="fab-pattern-model"
      data-view={camera}
      onPointerMove={showRegionTip}
      onPointerDown={showRegionTip}
      onPointerLeave={hideRegionTip}
    >
      <svg
        viewBox="0 0 380 264"
        role="img"
        aria-label={`${camera} of the same small wafer region. ${step.operation}. ${cycle ? `Exposure pattern ${cycle.label}.` : ""}`}
        data-mask={cycle?.id}
        data-phase={step.phase}
        data-resist={
          currentResist && currentResist.amount > 0.001 ? "present" : "absent"
        }
      >
        {drawing}
      </svg>
      {regionTip && regionTip.scene === index ? (
        <div
          className="fab-region-tip"
          role="tooltip"
          style={{ left: regionTip.x, top: regionTip.y }}
        >
          {regionTip.label}
        </div>
      ) : null}
    </div>
  );
};
