import { useId } from "react";
import { logicColours, siliconColours } from "./materials";
import {
  filmVisibility,
  inverterOperation,
  firstMetalTracks,
  portion,
  upperInsulatorHeight,
  upperMetalTracks,
  onMetalTrack,
  contactEtchHeight,
  stages,
  deviceSurfaceHeight,
  gateRegion,
  materialSurfaceHeight,
  maskOpens,
  maskMeshes,
  resistState,
  resistThickness,
  terminals,
  contactAt,
  insulationThickness,
  siliconSurfaceHeight,
} from "./process";
import type { PatternState, Visit } from "./process";
import { maskCycles, steps } from "./sequence";

type Point = [number, number, number];
type Face = { points: Point[]; fill: string; depth: number; opacity: number };

const mix = (from: number, to: number, progress: number) =>
  from + (to - from) * progress;

export type CameraState = { elevation: number; section: number };

export const patterningCamera = (
  index: number,
  progress: number,
  from: CameraState,
) => {
  const viewChange = portion(progress, 0, 0.28);
  const step = steps[index];
  const angle =
    index === 2 || step.phase === "expose"
      ? 1.05
      : index >= stages.contactInsulation
        ? 0.65
        : 0.55;
  const elevation = mix(from.elevation, angle ?? 0.62, viewChange);
  const section = mix(
    from.section,
    index === 0 || index === 1 || index >= 6 ? 1 : 0,
    viewChange,
  );
  const ymax = mix(65, 34, section);
  const yaw = mix(0.42, 0.08, section);
  const scale = 2.6;
  const project = ([x, y, z]: Point) => {
    const u = (x - 50) * Math.cos(yaw) - (y - 32.5) * Math.sin(yaw);
    const v = (x - 50) * Math.sin(yaw) + (y - 32.5) * Math.cos(yaw);

    return [
      190 + u * scale,
      132 + (v * Math.sin(elevation) - z * Math.cos(elevation)) * scale,
    ] as [number, number];
  };

  return { elevation, section, ymax, yaw, project };
};

export const PatterningModel = ({
  index,
  progress,
  fromIndex,
  view,
  visit,
  state,
  input,
}: {
  index: number;
  progress: number;
  fromIndex: number;
  view: ReturnType<typeof patterningCamera>;
  visit: Visit;
  state: PatternState;
  input: number;
}) => {
  const id = useId();
  const { elevation, section, ymax, yaw, project } = view;
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
  let faceOpacity = 1;
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
            ? `color-mix(in srgb, ${colours[0]}, #b795d1 ${exposure * 65}%)`
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
  const siliconTop = (x: number, y: number) =>
    siliconSurfaceHeight(x, y, state);
  const oxideBase = siliconTop(16, 23);
  const geometryXs = [
    0, 2, 4, 8, 10, 12, 14, 18, 23, 24, 28, 29, 34, 38, 40, 52, 55, 60, 62, 66,
    71, 72, 76, 77, 80, 82, 86, 88, 90, 92, 96, 98, 100,
  ];
  const geometryYs = [...new Set([0, 6, 10, 12, 20, 26, 53, ymax])]
    .filter((y) => y <= ymax)
    .sort((a, b) => a - b);
  const surfaceXs = [0, 2, 40, 52, 55, 60, 80, 98, 100];
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
    );
  };
  layer(
    surfaceXs,
    surfaceYs,
    -20,
    (col, row) => 20 + siliconTop(surfaceXs[col], surfaceYs[row]),
    [siliconColours.top, siliconColours.side, siliconColours.front],
  );
  const wellXs = surfaceXs.filter((x) => x >= 55);
  layer(
    wellXs,
    surfaceYs,
    -16,
    (col, row) => 16 + siliconTop(wellXs[col], surfaceYs[row]),
    ["#99adbb", "#758d9e", "#849dab"],
    false,
    state.well,
  );
  const implantColour = (nType: boolean): [string, string, string] =>
    nType
      ? ["#8cabc8", "#5f7d9a", "#7493b0"]
      : ["#c397aa", "#9c6f85", "#ae8298"];
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
        implantColour(nType),
        nType ? state.implantN : state.implantP,
      );
    });
  const insulator: [string, string, string] = ["#bdd5dc", "#89b0bb", "#9cbdc5"];
  const gateColours: [string, string, string] = [
    "#94aa88",
    "#62795b",
    "#788d6c",
  ];
  const metalColours: [string, string, string] = [
    "#b1bac8",
    "#75859d",
    "#8c9bb0",
  ];
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

  layer(
    dielectricXs,
    dielectricYs,
    (col, row) => siliconTop(dielectricXs[col], dielectricYs[row]),
    (col, row) => {
      const x = dielectricXs[col],
        y = dielectricYs[row];
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
  );
  layer(
    gateXs,
    surfaceYs,
    (col, row) =>
      siliconTop(gateXs[col], surfaceYs[row]) +
      insulationHeight(gateXs[col], surfaceYs[row]),
    (col) =>
      8 * state.poly * (gateRegion(gateXs[col]) ? 1 : 1 - state.patternGate),
    gateColours,
  );
  layer(
    coverXs,
    coverYs,
    (col, row) => deviceTop(coverXs[col], coverYs[row]),
    (col, row) => {
      const hole = contactAt(coverXs[col], coverYs[row]);
      const base = deviceTop(coverXs[col], coverYs[row]);
      const target = hole?.gate ? base : siliconTop(coverXs[col], coverYs[row]);
      const top = hole ? contactEtchHeight(target, state.contacts) : 14;

      return Math.max(0, top - base) * state.cover;
    },
    insulator,
    false,
    0.46,
  );
  terminals.forEach(({ x, gate }) => {
    const bottom = gate ? deviceTop(x, 6) : siliconTop(x, 20);
    box(
      x - 2,
      x + 2,
      gate ? 6 : 20,
      gate ? 10 : 26,
      bottom,
      (14 - bottom) * state.metalFill,
      metalColours,
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
    14,
    (col, row) =>
      3 *
      state.metal *
      (onMetalTrack(metalXs[col], metalYs[row], firstMetalTracks)
        ? 1
        : 1 - state.metalPattern),
    metalColours,
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
  );
  box(48, 52, 21, 25, 17, 8 * state.viaFill, metalColours);
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
  );
  maskCycles.forEach((cycle) => {
    const resist = resistState(state, cycle.id);
    if (resist.amount <= 0.001) return;

    const mesh = maskMeshes[cycle.id];
    const xs = mesh.xs;
    const ys = [...new Set([...mesh.ys.filter((y) => y < ymax), ymax])].sort(
      (a, b) => a - b,
    );
    layer(
      xs,
      ys,
      (col, row) => materialSurfaceHeight(state, xs[col], ys[row]),
      (col, row) => resistThickness(state, cycle.id, xs[col], ys[row]),
      ["#d7bdce", "#b694ac", "#c3a1b9"],
      (col, row) => (maskOpens(cycle.id, xs[col], ys[row]) ? resist.expose : 0),
    );
  });
  faces.sort((a, b) => a.depth - b.depth);
  const step = steps[index];
  const cycle = maskCycles.find((cycle) => cycle.id === step.mask);
  const currentResist = cycle ? resistState(state, cycle.id) : undefined;
  const beam = visit.working && step.phase === "expose";
  const maskOpacity = beam ? Math.sin(Math.PI * visit.process) * 0.85 : 0;
  const maskZ = materialSurfaceHeight(state, 50, 0) + 28;
  const mesh = cycle ? maskMeshes[cycle.id] : undefined;
  const apertures = mesh
    ? mesh.xs.slice(0, -1).flatMap((x, col) =>
        mesh.ys.slice(0, -1).flatMap((y, row) => {
          if (!maskOpens(cycle!.id, x, y) || y >= ymax) return [];

          return [
            {
              x,
              x1: mesh.xs[col + 1],
              y,
              y1: Math.min(mesh.ys[row + 1], ymax),
            },
          ];
        }),
      )
    : [];
  const activeRemoval =
    visit.working &&
    (step.phase === "develop" ||
      step.phase === "strip" ||
      visit.machine === "etch");
  const layoutPlan =
    index === 2
      ? portion(progress, 0, 0.22)
      : fromIndex === 2
        ? 1 - portion(progress, 0, 0.22)
        : 0;
  const electrical = inverterOperation(input, progress);
  const supplyColour = input ? logicColours.low : logicColours.high;
  const inputColour = input ? logicColours.high : logicColours.low;
  const supplyX = input ? 16 : 84;
  const drainX = input ? 36 : 64;
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

  return (
    <div className="fab-pattern-model" data-view={camera}>
      <svg
        viewBox="0 0 380 264"
        role="img"
        aria-label={`${camera} of the same small wafer region. ${step.operation}. ${cycle ? `Photomask pattern ${cycle.label}.` : ""}`}
        data-mask={cycle?.id}
        data-phase={step.phase}
        data-resist={
          currentResist && currentResist.amount > 0.001 ? "present" : "absent"
        }
      >
        <defs>
          <pattern
            id={`${id}-section`}
            width="7"
            height="7"
            patternUnits="userSpaceOnUse"
          >
            <path d="M0 7 7 0" stroke={siliconColours.hatch} strokeWidth=".6" />
          </pattern>
        </defs>
        <ellipse
          cx="190"
          cy="225"
          rx="127"
          ry="15"
          fill="#dcd4c5"
          opacity=".32"
        />
        {faces.map((face, i) => (
          <path
            key={i}
            d={path(face.points)}
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
            opacity={section * 0.26}
          />
        ) : null}
        {layoutPlan > 0 ? (
          <g opacity={layoutPlan} data-layout-plan="well">
            <path
              d={path([
                [55, 0, 1],
                [100, 0, 1],
                [100, ymax, 1],
                [55, ymax, 1],
              ])}
              fill="#99adbb"
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
              First implant area
            </text>
          </g>
        ) : null}
        {maskOpacity > 0 ? (
          <g opacity={maskOpacity} data-photomask={cycle?.id}>
            <path
              d={`${path([
                [0, 0, maskZ],
                [100, 0, maskZ],
                [100, ymax, maskZ],
                [0, ymax, maskZ],
              ])} ${apertures
                .map(({ x, x1, y, y1 }) =>
                  path([
                    [x, y, maskZ],
                    [x1, y, maskZ],
                    [x1, y1, maskZ],
                    [x, y1, maskZ],
                  ]),
                )
                .join(" ")}`}
              fill="#7f8190"
              fillRule="evenodd"
            />
            {apertures.map(({ x, x1, y, y1 }, i) => (
              <path
                key={i}
                d={path([
                  [x, y, maskZ - 1],
                  [x1, y, maskZ - 1],
                  [x1, y1, maskZ - 1],
                  [x, y1, maskZ - 1],
                ])}
                fill="#b697da"
                opacity=".25"
              />
            ))}
            {apertures.map(({ x, x1, y, y1 }, i) => (
              <path
                key={`light-${i}`}
                d={path(
                  [
                    [(x + x1) / 2, (y + y1) / 2, maskZ - 1],
                    [
                      (x + x1) / 2,
                      (y + y1) / 2,
                      materialSurfaceHeight(state, x, y) + 9,
                    ],
                  ],
                  false,
                )}
                stroke="#b399d3"
                strokeWidth="2"
                opacity=".6"
              />
            ))}
          </g>
        ) : null}
        {activeRemoval ? (
          <g
            fill={visit.machine === "etch" ? "#a3bbc0" : "#ba98b1"}
            opacity={Math.sin(Math.PI * visit.process) * 0.7}
          >
            {Array.from({ length: 14 }, (_, i) => {
              const phase = (visit.process * 2 + i * 0.17) % 1;
              const positions =
                step.phase === "strip"
                  ? [{ x: 0, x1: 100, y: 0, y1: ymax }]
                  : apertures;
              const opening = positions[i % positions.length];
              if (!opening) return null;

              const x = opening.x + (opening.x1 - opening.x) * ((i * 0.37) % 1);
              const y = opening.y + (opening.y1 - opening.y) * ((i * 0.23) % 1);
              const [cx, cy] = project([
                x,
                y,
                materialSurfaceHeight(state, x, y) +
                  (currentResist?.amount ?? 0) * 9 +
                  phase * 15,
              ]);

              return (
                <circle key={i} cx={cx} cy={cy} r="1.3" opacity={1 - phase} />
              );
            })}
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
        {visit.working && visit.machine === "polish" ? (
          <g opacity={Math.sin(Math.PI * visit.process) * 0.65}>
            <path
              d={path(
                [
                  [
                    visit.process * 100,
                    0,
                    upperInsulatorHeight(visit.process * 100, 0, state) + 0.4,
                  ],
                  [
                    visit.process * 100,
                    ymax,
                    upperInsulatorHeight(
                      visit.process * 100,
                      ymax - 0.01,
                      state,
                    ) + 0.4,
                  ],
                ],
                false,
              )}
              stroke="#ede5d5"
              strokeWidth="7"
              fill="none"
            />
            {Array.from({ length: 12 }, (_, i) => {
              const phase = (visit.process * 2 + i * 0.17) % 1;
              const [cx, cy] = project([8 + i * 7, ymax - 3, 26 + phase * 9]);

              return (
                <circle
                  key={i}
                  cx={cx}
                  cy={cy}
                  r="1.2"
                  fill="#a9c2c9"
                  opacity={1 - phase}
                />
              );
            })}
          </g>
        ) : null}
        {visit.working && visit.machine === "implant" ? (
          <g
            data-implant={index === stages.implantP ? "p-type" : "n-type"}
            opacity={Math.sin(Math.PI * visit.process)}
          >
            <text
              x="190"
              y="20"
              textAnchor="middle"
              fontSize="9"
              fill="#86727f"
            >
              Resist stays on during implantation
            </text>
            <g fill={index === stages.implantP ? "#ba8ca3" : "#829fb7"}>
              {Array.from({ length: 20 }, (_, i) => {
                const phase = (visit.process * 2 + i * 0.13) % 1;
                const x =
                  index === stages.well
                    ? 59 + (i % 7) * 5
                    : (index === stages.implantP ? [64, 84] : [16, 36])[i % 2];
                const [cx, cy] = project([
                  x,
                  14 + (i % 4) * 4,
                  materialSurfaceHeight(state, x, 15) + 20 - phase * 26,
                ]);

                return (
                  <circle
                    key={i}
                    cx={cx}
                    cy={cy}
                    r="1.4"
                    opacity={Math.sin(Math.PI * phase)}
                  />
                );
              })}
            </g>
          </g>
        ) : null}
        {index >= stages.well && index <= stages.anneal ? (
          <g fontSize="9" textAnchor="middle" fill={siliconColours.label}>
            <text
              x={project([24, ymax, -11])[0]}
              y={project([24, ymax, -11])[1]}
            >
              p-type silicon
            </text>
            <text
              opacity={state.well}
              x={project([77, ymax, -11])[0]}
              y={project([77, ymax, -11])[1]}
            >
              n-well
            </text>
          </g>
        ) : null}
        {index >= stages.implant && index <= stages.anneal ? (
          <g
            opacity={Math.max(state.implantN, state.implantP)}
            fontSize="8"
            textAnchor="middle"
            fill="#f5f3ed"
          >
            {[16, 36, 64, 84].map((x) => {
              const point = project([x, ymax, oxideBase - 1.5]);

              return (
                <text
                  key={x}
                  x={point[0]}
                  y={point[1]}
                  opacity={x < 50 ? state.implantN : state.implantP}
                >
                  {x < 50 ? "n+" : "p+"}
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
                [x, -9, 18],
                [x, 23, 18],
              ];
              const label = project([x, -9, 18]);

              return (
                <g key={x}>
                  <path
                    d={path(points, false)}
                    fill="none"
                    stroke="#75859d"
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
            {[26, 74].map((x) =>
              trace(
                `gate-${x}`,
                [
                  [50, 8, 18],
                  [x, 8, 18],
                  [x, 8, deviceTop(x, 8) + 0.3],
                ],
                inputColour,
                electrical.gates,
              ),
            )}
            {trace(
              "conducting-transistor",
              [
                [supplyX, 23, 18],
                [supplyX, 23, oxideBase - 0.2],
                [drainX, 23, oxideBase - 0.2],
                [drainX, 23, 18],
                [input ? 64 : 36, 23, 18],
              ],
              supplyColour,
              electrical.transfer,
            )}
            {(
              [
                [50, 8, `A = ${input}`, inputColour, -9],
                [
                  50,
                  28,
                  `Q = ${electrical.output ?? "…"}`,
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
                  y={point[1] + offset}
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
                y="207"
                textAnchor="middle"
                fontSize="11"
                fill={
                  (x === 26 ? input === 1 : input === 0)
                    ? supplyColour
                    : "#8e8271"
                }
                opacity={electrical.gates}
              >
                {x === 26 ? "n-type" : "p-type"}{" "}
                {(x === 26 ? input === 1 : input === 0) ? "on" : "off"}
              </text>
            ))}
          </g>
        ) : null}
        <text x="190" y="254" textAnchor="middle" className="fab-view-label">
          {camera}
          {section > 0.5 ? " · front portion hidden" : ""}
        </text>
      </svg>
    </div>
  );
};
