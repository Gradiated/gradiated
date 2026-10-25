import { materialColours } from "./materials";
import {
  contactAt,
  contactEtchHeight,
  deviceSurfaceHeight,
  exposureRegions,
  materialSurfaceHeight,
  maskMeshes,
  maskOpens,
  patternSurfaceHeight,
  portion,
  siliconSurfaceHeight,
  stages,
  upperInsulatorHeight,
  waferDetailRegion,
} from "./process";
import type { PatternState, Rectangle, Visit } from "./process";
import { steps } from "./sequence";
import type { FabricationStep } from "./sequence";

type Point = [number, number, number];
type Project = (point: Point) => [number, number];

const activity = (visit: Visit) =>
  visit.working ? Math.sin(Math.PI * visit.process) : 0;
const phaseAt = (progress: number, index: number) =>
  (progress * 2 + index * 0.173) % 1;
const inspectionScan = (progress: number) => ({
  local: portion(progress, 0.2, 0.8),
  waferX:
    progress < 0.2
      ? 45 + (waferDetailRegion.x - 45) * portion(progress, 0, 0.2)
      : progress < 0.8
        ? waferDetailRegion.x +
          waferDetailRegion.size * portion(progress, 0.2, 0.8)
        : waferDetailRegion.x +
          waferDetailRegion.size +
          (235 - waferDetailRegion.x - waferDetailRegion.size) *
            portion(progress, 0.8, 1),
});
const sitesInRegions = (regions: Rectangle[], count = 36) => {
  const area = regions.reduce(
    (total, [x0, x1, y0, y1]) => total + (x1 - x0) * (y1 - y0),
    0,
  );
  const spacing = Math.max(7, Math.sqrt(area / count));

  return regions.flatMap(([x0, x1, y0, y1]) => {
    const columns = Math.max(1, Math.ceil((x1 - x0) / spacing));
    const rows = Math.max(1, Math.ceil((y1 - y0) / spacing));

    return Array.from({ length: rows * columns }, (_, i) => {
      const column = i % columns;
      const row = Math.floor(i / columns);

      return [
        x0 + ((column + 0.5) / columns) * (x1 - x0),
        y0 + ((row + 0.5) / rows) * (y1 - y0),
      ] as [number, number];
    });
  });
};

const surfaceSites = (step: FabricationStep, ymax: number) =>
  sitesInRegions(
    step.mask ? exposureRegions(step.mask, ymax) : [[0, 100, 0, ymax]],
  );

const implantSites = (step: FabricationStep, ymax: number) => {
  if (step.mask === "well") return surfaceSites(step, ymax);

  const ranges =
    step.mask === "p"
      ? [
          [60, 71],
          [77, 88],
        ]
      : [
          [12, 23],
          [29, 40],
        ];

  return sitesInRegions(
    ranges.map(([x0, x1]) => [x0, x1, 12, Math.min(53, ymax)]),
    24,
  );
};

const dissolvingSitesFor = (step: FabricationStep, ymax: number) => {
  const mask = step.mask;
  if (!mask) return [];

  const mesh = maskMeshes[mask];
  const regions =
    step.phase === "strip"
      ? mesh.ys.slice(0, -1).flatMap((y0, row) => {
          const y1 = Math.min(ymax, mesh.ys[row + 1]);
          if (y0 >= y1) return [];

          const runs: [number, number, number, number][] = [];
          let start: number | undefined;
          for (let col = 0; col < mesh.xs.length - 1; col++) {
            const retained = !maskOpens(mask, mesh.xs[col], y0);
            if (retained && start === undefined) start = mesh.xs[col];
            if (start === undefined) continue;
            if (retained && col < mesh.xs.length - 2) continue;

            runs.push([
              start,
              retained ? mesh.xs[col + 1] : mesh.xs[col],
              y0,
              y1,
            ]);
            start = undefined;
          }
          return runs;
        })
      : exposureRegions(mask, ymax);

  return sitesInRegions(regions);
};

const EtchImpact = ({
  point: [x, y, z],
  top,
  phase,
  seed,
  project,
  material,
}: {
  point: Point;
  top: number;
  phase: number;
  seed: number;
  project: Project;
  material: string;
}) => {
  const arrival = portion(phase, 0, 0.55);
  const height = top + (z + 0.5 - top) * arrival;
  const [cx, cy] = project([x, y, height]);
  const [tx, ty] = project([x, y, Math.min(top, height + 4)]);
  const [sx, sy] = project([x, y, z + 0.5]);
  const incoming = portion(phase, 0, 0.05) * (1 - portion(phase, 0.52, 0.6));
  const impact = Math.sin(Math.PI * portion(phase, 0.55, 0.72));
  const scattering = portion(phase, 0.58, 1);

  return (
    <g data-etch-impact="true">
      <g opacity={incoming}>
        <path
          d={`M${tx} ${ty}L${cx} ${cy}`}
          stroke="var(--color-kiln-600)"
          strokeWidth="2.7"
          strokeLinecap="round"
          opacity=".35"
        />
        <path
          d={`M${tx} ${ty}L${cx} ${cy}`}
          stroke="var(--color-light-000)"
          strokeWidth=".9"
          strokeLinecap="round"
        />
        <circle
          cx={cx}
          cy={cy}
          r="2.7"
          fill="var(--color-kiln-600)"
          opacity=".25"
        />
        <circle
          cx={cx}
          cy={cy}
          r="1.15"
          fill="var(--color-light-000)"
          stroke="var(--color-kiln-600)"
          strokeWidth=".55"
        />
      </g>
      <ellipse
        cx={sx}
        cy={sy}
        rx={1 + impact * 3}
        ry={0.7 + impact * 1.5}
        fill="var(--color-light-000)"
        stroke="var(--color-kiln-600)"
        strokeWidth=".65"
        opacity={impact * 0.8}
      />
      {scattering > 0 && scattering < 1
        ? [0, 1, 2].map((fragment) => {
            const angle = seed * 2.399963 + (fragment * Math.PI * 2) / 3;
            const [fx, fy] = project([
              x + Math.cos(angle) * scattering * 9,
              y + Math.sin(angle) * scattering * 6,
              z + 0.5 + scattering * (12 + fragment * 3),
            ]);

            return (
              <circle
                key={fragment}
                data-etch-fragment="true"
                cx={fx}
                cy={fy}
                r={1 - scattering * 0.45}
                fill={material}
                stroke="var(--color-kiln-600)"
                strokeWidth=".4"
                strokeOpacity={1 - scattering}
                opacity={Math.sin(Math.PI * scattering) * 0.85}
              />
            );
          })
        : null}
    </g>
  );
};

export const CloseupProcessEffects = ({
  index,
  visit,
  state,
  project,
  ymax,
}: {
  index: number;
  visit: Visit;
  state: PatternState;
  project: Project;
  ymax: number;
}) => {
  if (!visit.working) return null;

  const step = steps[index];
  const progress = visit.process;
  const incomingHeight =
    Math.max(
      ...[
        [0, 0],
        [26, 8],
        [50, 23],
        [74, 8],
        [94, 23],
      ].map(([x, y]) => patternSurfaceHeight(state, x, y)),
    ) + 12;
  const surface = (x: number, y: number) => {
    if (visit.machine === "etch" && step.mask === "contact") {
      const terminal = contactAt(x, y);
      if (terminal)
        return contactEtchHeight(
          terminal.gate
            ? deviceSurfaceHeight(x, y, state)
            : siliconSurfaceHeight(x, y, state),
          state.contacts,
        );
    }
    if (visit.machine === "etch" && step.mask === "via")
      return (
        upperInsulatorHeight(x, y, state) * (1 - state.viaOpen) +
        17 * state.viaOpen
      );

    return patternSurfaceHeight(state, x, y);
  };
  const path = (points: Point[], close = false) =>
    points
      .map(
        (point, i) =>
          `${i ? "L" : "M"}${project(point)
            .map((n) => n.toFixed(2))
            .join(" ")}`,
      )
      .join(" ") + (close ? "Z" : "");
  const sites = surfaceSites(step, ymax);
  const wet = visit.machine === "develop" || visit.machine === "strip";
  const deposit = visit.machine === "deposit" || visit.machine === "metal";
  const dissolvingSites = wet ? dissolvingSitesFor(step, ymax) : [];
  const etchedMaterial =
    step.mask === "gate"
      ? materialColours.gate[0]
      : step.mask === "metal" || step.mask === "upper"
        ? materialColours.metal[1]
        : materialColours.insulator[1];

  return (
    <g
      aria-hidden="true"
      pointerEvents="none"
      data-process-effect={visit.machine}
      opacity={activity(visit)}
    >
      {visit.machine === "etch" || deposit
        ? sites.map(([x, y], i) => {
            const z = surface(x, y);
            if (visit.machine === "etch")
              return (
                <g key={i} data-surface-site={`${x} ${y}`}>
                  <EtchImpact
                    point={[x, y, z]}
                    top={incomingHeight + 16}
                    phase={phaseAt(progress * 1.6, i)}
                    seed={i}
                    project={project}
                    material={etchedMaterial}
                  />
                </g>
              );

            const phase = phaseAt(progress, i);
            const arrival = portion(phase, 0, 0.8);
            const [cx, cy] = project([
              x,
              y,
              incomingHeight + (z + 0.5 - incomingHeight) * arrival,
            ]);
            const hit = Math.sin(Math.PI * portion(phase, 0.8, 1));
            const [sx, sy] = project([x, y, z + 0.5]);
            const colour = visit.machine === "metal" ? "#c1ccdc" : "#94b9c1";

            return (
              <g key={i} data-surface-site={`${x} ${y}`}>
                <circle
                  cx={cx}
                  cy={cy}
                  r="1.3"
                  fill={colour}
                  opacity={Math.sin(Math.PI * phase) * 0.85}
                />
                <ellipse
                  cx={sx}
                  cy={sy}
                  rx={1 + hit * 1.8}
                  ry={0.7 + hit * 0.5}
                  fill="#d6e6e7"
                  opacity={hit * 0.5}
                />
              </g>
            );
          })
        : null}
      {wet ? (
        <g>
          <path
            d={path(
              Array.from({ length: 14 }, (_, i) => {
                const x = Math.min(100, Math.max(0, -12 + progress * 124));
                const y = (i / 13) * ymax;
                return [x, y, surface(x, y) + 0.6] as Point;
              }),
            )}
            stroke="#d9edef"
            strokeWidth="11"
            opacity=".15"
            fill="none"
          />
          {dissolvingSites.map(([x, y], i) => {
            const phase = phaseAt(progress, i);
            const stripping = visit.machine === "strip";
            const [cx, cy] = project([
              x + phase * (stripping ? 7 : 5),
              y + phase * (stripping ? 2 : 1.5),
              surface(x, y) + 0.5 + phase * (stripping ? 4 : 2),
            ]);
            return (
              <circle
                key={i}
                data-dissolving-site={`${x} ${y}`}
                cx={cx}
                cy={cy}
                r={(stripping ? 1.5 : 1.2) * (1 - phase)}
                fill={stripping ? materialColours.resist[1] : "#d4becb"}
                opacity={Math.sin(Math.PI * phase) * (stripping ? 0.65 : 0.5)}
              />
            );
          })}
        </g>
      ) : null}
      {visit.machine === "implant" ? (
        <g data-implant={index === stages.implantP ? "p-type" : "n-type"}>
          <text x="190" y="20" textAnchor="middle" fontSize="9" fill="#86727f">
            Resist stays on during implantation
          </text>
          {implantSites(step, ymax).map(([x, y], i) => {
            const phase = phaseAt(progress, i);
            const top = materialSurfaceHeight(state, x, y);
            const buried =
              siliconSurfaceHeight(x, y, state) -
              (index === stages.well ? 7 : 3);
            const z =
              phase < 0.7
                ? incomingHeight + (top - incomingHeight) * (phase / 0.7)
                : top + (buried - top) * portion(phase, 0.7, 1);
            const [cx, cy] = project([x, y, z]);
            return (
              <circle
                key={i}
                data-implant-site={`${x} ${y}`}
                cx={cx}
                cy={cy}
                r="1.4"
                fill={
                  index === stages.implantP
                    ? materialColours.p[0]
                    : materialColours.n[0]
                }
                opacity={
                  Math.sin(Math.PI * phase) *
                  (0.85 - 0.4 * portion(phase, 0.68, 0.86))
                }
              />
            );
          })}
        </g>
      ) : null}
      {visit.machine === "polish"
        ? (() => {
            const x = 12 + progress * 76;
            const y = ymax * 0.57;
            const pad = (height: number) =>
              Array.from({ length: 25 }, (_, i) => {
                const angle = (i / 24) * Math.PI * 2;
                const px = x + Math.cos(angle) * 9;
                const py = y + Math.sin(angle) * 7;
                return [
                  px,
                  py,
                  upperInsulatorHeight(px, py, state) + height,
                ] as Point;
              });
            const angle = progress * Math.PI * 6;
            return (
              <g>
                <path d={path(pad(0.6), true)} fill="#b9b4a9" opacity=".55" />
                <path
                  d={path(pad(2), true)}
                  fill="#ddd6c7"
                  stroke="#c1b9aa"
                  strokeWidth=".7"
                  opacity=".8"
                />
                <path
                  d={path(
                    [-1, 1].map(
                      (sign) =>
                        [
                          x + Math.cos(angle) * 7 * sign,
                          y + Math.sin(angle) * 5 * sign,
                          upperInsulatorHeight(x, y, state) + 2.2,
                        ] as Point,
                    ),
                  )}
                  stroke="#afa896"
                  strokeWidth="1"
                  opacity=".65"
                />
                {[0, 1, 2].map((i) => {
                  const phase = phaseAt(progress, i);
                  const [cx, cy] = project([
                    x - 9 - phase * 5,
                    y + 2 + i * 2,
                    upperInsulatorHeight(x, y, state) + 0.5,
                  ]);
                  return (
                    <circle
                      key={i}
                      cx={cx}
                      cy={cy}
                      r="1"
                      fill="#bdd1d3"
                      opacity={(1 - phase) * 0.6}
                    />
                  );
                })}
              </g>
            );
          })()
        : null}
      {visit.machine === "inspect"
        ? (() => {
            const scan = inspectionScan(progress).local;
            const x = scan * 100;
            const outline = Math.max(0, 1 - Math.abs(progress - 0.5) * 10);
            return (
              <g
                stroke="#bfab79"
                fill="none"
                opacity={Math.sin(Math.PI * scan)}
              >
                <path
                  d={path(
                    Array.from({ length: 15 }, (_, i) => {
                      const y = (i / 14) * ymax;
                      return [x, y, surface(x, y) + 0.8] as Point;
                    }),
                  )}
                  strokeWidth="4"
                  opacity=".12"
                />
                <path
                  d={path(
                    Array.from({ length: 15 }, (_, i) => {
                      const y = (i / 14) * ymax;
                      return [x, y, surface(x, y) + 0.8] as Point;
                    }),
                  )}
                  strokeWidth=".9"
                  opacity=".6"
                />
                <path
                  d={path(
                    [
                      [44, 18],
                      [56, 18],
                      [56, 28],
                      [44, 28],
                    ].map(([px, py]) => [px, py, surface(px, py) + 1] as Point),
                    true,
                  )}
                  strokeWidth=".8"
                  opacity={outline * 0.7}
                />
              </g>
            );
          })()
        : null}
    </g>
  );
};

export const WaferProcessEffects = ({ visit }: { visit: Visit }) => {
  if (!visit.working) return null;

  const progress = visit.process;
  const wet = visit.machine === "develop" || visit.machine === "strip";
  const deposit = visit.machine === "deposit" || visit.machine === "metal";

  return (
    <g
      aria-hidden="true"
      pointerEvents="none"
      data-wafer-effect={visit.machine}
      opacity={activity(visit)}
    >
      {visit.machine === "etch" || deposit || visit.machine === "implant"
        ? Array.from({ length: 28 }, (_, i) => {
            const phase = phaseAt(progress, i);
            const radius = Math.sqrt((i + 0.5) / 28);
            const angle = i * Math.PI * (3 - Math.sqrt(5));
            const x = 140 + Math.cos(angle) * radius * 92;
            const y = 119 + Math.sin(angle) * radius * 73;
            if (visit.machine === "etch")
              return (
                <g key={i} data-wafer-site={`${x} ${y}`}>
                  <EtchImpact
                    point={[x, y, 0]}
                    top={28}
                    phase={phaseAt(progress * 1.6, i)}
                    seed={i}
                    project={([px, py, pz]) => [px, py - pz]}
                    material={materialColours.insulator[1]}
                  />
                </g>
              );

            const hit = portion(phase, 0.65, 1);
            return (
              <g key={i} data-wafer-site={`${x} ${y}`}>
                <circle
                  cx={x}
                  cy={y - (1 - phase) * 18}
                  r="1"
                  fill="#e0e8e9"
                  opacity={Math.sin(Math.PI * phase) * (1 - hit) * 0.5}
                />
                <ellipse
                  cx={x}
                  cy={y}
                  rx={1 + hit * 2}
                  ry={0.7 + hit}
                  fill="none"
                  stroke="#dfebec"
                  strokeWidth=".6"
                  opacity={Math.sin(Math.PI * hit) * 0.4}
                />
              </g>
            );
          })
        : null}
      {wet ? (
        <path
          d={`M${25 + progress * 230} 40v160`}
          fill="none"
          stroke="#d9edef"
          strokeWidth="18"
          opacity=".12"
        />
      ) : null}
      {visit.machine === "polish" ? (
        <g transform={`translate(${75 + progress * 130} 119)`}>
          <ellipse
            rx="15"
            ry="12"
            fill="#d1c8b7"
            stroke="#a99e87"
            strokeWidth=".7"
            opacity=".65"
          />
          <path
            d="M-11 0h22"
            transform={`rotate(${progress * 1080})`}
            fill="none"
            stroke="#a99e87"
            strokeWidth=".8"
            opacity=".6"
          />
        </g>
      ) : null}
      {visit.machine === "inspect" ? (
        <g fill="none" stroke="#c3ad78">
          <path
            d={`M${inspectionScan(progress).waferX} 40v160`}
            strokeWidth="5"
            opacity=".1"
          />
          <path
            d={`M${inspectionScan(progress).waferX} 40v160`}
            strokeWidth="1"
            opacity=".5"
          />
          <rect
            x={waferDetailRegion.x}
            y={waferDetailRegion.y}
            width={waferDetailRegion.size}
            height={waferDetailRegion.size}
            strokeWidth="1"
            opacity={Math.max(0, 1 - Math.abs(progress - 0.5) * 10) * 0.8}
          />
        </g>
      ) : null}
    </g>
  );
};
