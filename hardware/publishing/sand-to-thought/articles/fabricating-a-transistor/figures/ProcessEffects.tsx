import { materialColours } from "./materials";
import {
  activeSilicon,
  contactAt,
  contactEtchHeight,
  contactInsulatorHeight,
  deviceSurfaceHeight,
  exposureRegions,
  gateRegion,
  maskMeshes,
  maskOpens,
  patternSurfaceHeight,
  portion,
  resistThickness,
  siliconSurfaceHeight,
  stages,
  upperInsulatorHeight,
  waferDetailRegion,
  waferPatternScale,
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

const beamSites = (ymax: number) =>
  Array.from(
    { length: 52 },
    (_, i) =>
      [2 + (i % 13) * 8, (Math.floor(i / 13) * (ymax - 0.001)) / 3] as [
        number,
        number,
      ],
  );

const bombardmentSites = (step: FabricationStep, ymax: number) => {
  const sites = beamSites(ymax);
  for (const [x0, x1, y0, y1] of step.mask
    ? exposureRegions(step.mask, ymax)
    : []) {
    if (!sites.some(([x, y]) => x >= x0 && x < x1 && y >= y0 && y < y1)) {
      sites.push([(x0 + x1) / 2, (y0 + y1) / 2]);
    }
  }

  return sites;
};

const arrivingMaterialFor = (step: FabricationStep) =>
  step.machine === "implant"
    ? step.mask === "p"
      ? materialColours.p
      : materialColours.n
    : step.machine === "metal"
      ? materialColours.metal
      : step.key === "poly"
        ? materialColours.gate
        : step.key === "isolation"
          ? materialColours.nitride
          : materialColours.insulator;

const etchedMaterialFor = (step: FabricationStep) =>
  step.mask === "isolation" || step.key === "nitride-strip"
    ? materialColours.nitride[1]
    : step.mask === "gate"
      ? materialColours.gate[0]
      : step.mask === "metal" || step.mask === "upper"
        ? materialColours.metal[1]
        : materialColours.insulator[1];

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
  blocked = false,
}: {
  point: Point;
  top: number;
  phase: number;
  seed: number;
  project: Project;
  material: string;
  blocked?: boolean;
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
    <g data-etch-impact="true" data-etch-blocked={blocked || undefined}>
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
        opacity={impact * (blocked ? 0.3 : 0.8)}
      />
      {!blocked && scattering > 0 && scattering < 1
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
  const sites =
    visit.machine === "implant"
      ? beamSites(ymax)
      : visit.machine === "etch"
        ? bombardmentSites(step, ymax)
        : surfaceSites(step, ymax);
  const wet = visit.machine === "develop" || visit.machine === "strip";
  const deposit = visit.machine === "deposit" || visit.machine === "metal";
  const dissolvingSites = wet ? dissolvingSitesFor(step, ymax) : [];
  const etchedMaterial = etchedMaterialFor(step);
  const material = arrivingMaterialFor(step);
  const polishingHeight =
    index === stages.contactPolish
      ? contactInsulatorHeight
      : upperInsulatorHeight;

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
                    blocked={
                      step.key === "nitride-strip"
                        ? !activeSilicon(x)
                        : !!step.mask &&
                          resistThickness(state, step.mask, x, y) > 0.1
                    }
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

            return (
              <g key={i} data-surface-site={`${x} ${y}`}>
                <circle
                  cx={cx}
                  cy={cy}
                  r="1.3"
                  fill={material[0]}
                  stroke={material[1]}
                  strokeWidth=".4"
                  opacity={Math.sin(Math.PI * phase) * 0.85}
                />
                <ellipse
                  cx={sx}
                  cy={sy}
                  rx={1 + hit * 1.8}
                  ry={0.7 + hit * 0.5}
                  fill={material[0]}
                  opacity={hit * 0.5}
                />
              </g>
            );
          })
        : null}
      {wet ? (
        <g>
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
                fill={materialColours.resist[stripping ? 1 : 0]}
                opacity={Math.sin(Math.PI * phase) * (stripping ? 0.65 : 0.5)}
              />
            );
          })}
        </g>
      ) : null}
      {visit.machine === "implant" ? (
        <g data-implant={index === stages.implantP ? "p-type" : "n-type"}>
          {sites.map(([x, y], i) => {
            const phase = phaseAt(progress, i);
            const top = patternSurfaceHeight(state, x, y);
            const target =
              step.mask && resistThickness(state, step.mask, x, y) > 0.1
                ? "photoresist"
                : state.poly > 0.5 && gateRegion(x)
                  ? "gate"
                  : "silicon";
            const blocked = target !== "silicon";
            const silicon = siliconSurfaceHeight(x, y, state);
            const depth = index === stages.well ? silicon - 11 : -8;
            const distance = incomingHeight - depth;
            const freeHeight = incomingHeight - (phase / 0.9) * distance;
            const stop = blocked ? top : depth;
            const z = Math.max(stop, freeHeight);
            const arrival = ((incomingHeight - stop) / distance) * 0.9;
            const cutFace = y > ymax - 0.01;
            const visibility =
              portion(phase, 0, 0.03) *
              (1 - portion(phase, arrival, Math.min(1, arrival + 0.1))) *
              (blocked || cutFace ? 1 : portion(z, silicon - 0.5, silicon));
            const tail = project([x, y, Math.min(incomingHeight, z + 2)]);
            const [cx, cy] = project([x, y, z]);
            return (
              <g key={i} opacity=".85">
                <path
                  d={`M${tail[0]} ${tail[1]}L${cx} ${cy}`}
                  stroke={material[0]}
                  strokeWidth=".65"
                  opacity={visibility * 0.5}
                />
                <circle
                  data-implant-site={`${x} ${y}`}
                  data-implant-target={target}
                  data-implant-cut-face={cutFace || undefined}
                  cx={cx}
                  cy={cy}
                  r="1.2"
                  stroke="var(--color-light-000)"
                  strokeWidth=".4"
                  fill={material[0]}
                  opacity={visibility}
                />
              </g>
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
                  polishingHeight(px, py, state) + height,
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
                          polishingHeight(x, y, state) + 2.2,
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
                    polishingHeight(x, y, state) + 0.5,
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

export const WaferProcessEffects = ({
  visit,
  index,
  state,
}: {
  visit: Visit;
  index: number;
  state: PatternState;
}) => {
  if (!visit.working) return null;

  const progress = visit.process;
  const wet = visit.machine === "develop" || visit.machine === "strip";
  const deposit = visit.machine === "deposit" || visit.machine === "metal";
  const material = arrivingMaterialFor(steps[index]);

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
            const localX =
              ((((x / waferPatternScale - 47) % 27) + 27) % 27) / 0.27;
            const localY =
              (((((y / waferPatternScale - 52) % 27) + 27) % 27) * 65) / 27;
            const mask = steps[index].mask;
            const blocked =
              steps[index].key === "nitride-strip"
                ? !activeSilicon(localX)
                : !!mask && resistThickness(state, mask, localX, localY) > 0.1;
            if (visit.machine === "etch")
              return (
                <g key={i} data-wafer-site={`${x} ${y}`}>
                  <EtchImpact
                    point={[x, y, 0]}
                    top={28}
                    phase={phaseAt(progress * 1.6, i)}
                    seed={i}
                    project={([px, py, pz]) => [px, py - pz]}
                    material={etchedMaterialFor(steps[index])}
                    blocked={blocked}
                  />
                </g>
              );

            if (visit.machine === "implant")
              return (
                <circle
                  key={i}
                  data-wafer-implant="true"
                  cx={x}
                  cy={y - (1 - portion(phase, 0, 0.85)) * 18}
                  r="1"
                  fill={material[0]}
                  stroke="var(--color-light-000)"
                  strokeWidth=".3"
                  opacity={
                    portion(phase, 0, 0.03) *
                    (1 - portion(phase, 0.85, 0.95)) *
                    0.65
                  }
                />
              );

            const hit = portion(phase, 0.65, 1);
            return (
              <g key={i} data-wafer-site={`${x} ${y}`}>
                <circle
                  cx={x}
                  cy={y - (1 - phase) * 18}
                  r="1"
                  fill={material[0]}
                  stroke={material[1]}
                  strokeWidth=".35"
                  opacity={Math.sin(Math.PI * phase) * (1 - hit) * 0.75}
                />
                <ellipse
                  cx={x}
                  cy={y}
                  rx={1 + hit * 2}
                  ry={0.7 + hit}
                  fill="none"
                  stroke={material[0]}
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
