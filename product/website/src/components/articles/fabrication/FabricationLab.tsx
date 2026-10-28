import { useId } from "react";
import type { CSSProperties } from "react";
import { machines } from "./model";
import { LabMachine, SmallWafer } from "./FabricationMachine";
import {
  exposedResistColour,
  materialColours,
  siliconColours,
} from "./materials";
import { WaferProcessEffects } from "./ProcessEffects";
import { ExposureBeams } from "./ExposureBeams";
import type { MachineId } from "./model";
import {
  ease,
  exposureLighting,
  exposureRegions,
  resistState,
  maskMeshes,
  maskOpens,
  machineLoadingSpots,
  machineLoadingPoint,
  machinePlaces,
  portion,
  stages,
  waferDetailRegion,
  waferPatternScale,
} from "./process";
import type { PatternState, Visit } from "./process";
import { maskCycles, steps } from "./sequence";
import type { MaskId } from "./sequence";

const walk = (
  from: { x: number; y: number },
  to: { x: number; y: number },
  t: number,
) => {
  const startY = from.y === 126 ? 126 : from.y < 120 ? 95 : 158;
  const endY = to.y === 126 ? 126 : to.y < 120 ? 95 : 158;
  if (from.x === to.x && from.y === to.y) return { x: to.x, y: endY };

  const points = [
    { x: from.x, y: startY },
    { x: from.x, y: 126 },
    { x: to.x, y: 126 },
    { x: to.x, y: endY },
  ];
  const lengths = points
    .slice(1)
    .map((p, i) => Math.hypot(p.x - points[i].x, p.y - points[i].y));
  let distance = lengths.reduce((sum, n) => sum + n, 0) * ease(t);
  for (let i = 0; i < lengths.length; i++) {
    if (distance <= lengths[i] || i === lengths.length - 1) {
      const fraction = lengths[i] ? distance / lengths[i] : 1;

      return {
        x: points[i].x + (points[i + 1].x - points[i].x) * fraction,
        y: points[i].y + (points[i + 1].y - points[i].y) * fraction,
      };
    }
    distance -= lengths[i];
  }

  return points[points.length - 1];
};

export const CleanRoom = ({
  visit,
  state,
  preview,
  showPreview,
  hidePreview,
  togglePreview,
  machinesOpacity = 1,
  operatorOpacity = 1,
  entry = 1,
  held = 1,
  door = 0,
  doorOpen = 0,
}: {
  machinesOpacity?: number;
  operatorOpacity?: number;
  entry?: number;
  held?: number;
  door?: number;
  doorOpen?: number;
  visit: Visit;
  state: PatternState;
  preview?: MachineId;
  showPreview: (id: MachineId, immediate?: boolean) => void;
  hidePreview: () => void;
  togglePreview: (id: MachineId) => void;
}) => {
  const home = { x: 320, y: 126 };
  const destination = visit.machine ? machinePlaces[visit.machine] : home;
  const origin = visit.from ? machinePlaces[visit.from] : home;
  const walked = walk(origin, destination, portion(visit.progress, 0, 0.25));
  const person = {
    x: walked.x + (658 - walked.x) * (1 - entry),
    y: walked.y,
  };
  const inMachine = visit.machine ? visit.loaded : 0;
  const loadingPoint = visit.machine
    ? machineLoadingPoint(visit.machine)
    : home;
  const heldX = person.x + 12;
  const heldY = person.y + 2;
  const waferX = heldX + (loadingPoint.x - heldX) * inMachine;
  const waferY = heldY + (loadingPoint.y - heldY) * inMachine;
  const shape = visit.machine
    ? machineLoadingSpots[visit.machine]
    : { rx: 8, ry: 5 };
  const waferRx = 8 + (shape.rx - 8) * inMachine;
  const waferRy = 5 + (shape.ry - 5) * inMachine;
  const seated = portion(inMachine, 0.9, 1);

  return (
    <div
      className="fab-room"
      data-machine={visit.machine ?? "none"}
      data-working={visit.working}
    >
      <svg viewBox="0 0 640 258" className="fab-room-floor" aria-hidden="true">
        <defs>
          <pattern
            id="fab-floor"
            width="24"
            height="24"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M24 0H0v24"
              fill="none"
              stroke="#dfe5dd"
              strokeWidth=".7"
            />
          </pattern>
        </defs>
        <rect
          x="8"
          y="5"
          width="624"
          height="247"
          rx="14"
          fill="#eceeea"
          stroke="#ced7cb"
        />
        <rect
          x="9"
          y="6"
          width="622"
          height="245"
          rx="13"
          fill="url(#fab-floor)"
        />
        <path d="M24 126h592" stroke="#f1f2ef" strokeWidth="48" />
        <path
          d="M24 109h592m-592 34h592"
          stroke="#d5ded1"
          strokeWidth="1"
          strokeDasharray="3 7"
        />
        <g opacity={door} data-room-door="true">
          <path d="M632 103v46" stroke="#f7f3ec" strokeWidth="5" />
          <path d="M633 102h-5m5 48h-5" stroke="#839784" strokeWidth="2" />
          <g transform={`translate(632 104) rotate(${doorOpen * 86})`}>
            <path d="M0 0v44" stroke="#7d9185" strokeWidth="3" />
            <circle cx="-3" cy="37" r="1.5" fill="#7d9185" />
          </g>
        </g>
      </svg>
      {machinesOpacity > 0
        ? machines.map((machine) => {
            const place = machinePlaces[machine.id];
            const current = visit.machine === machine.id;
            const working = current && visit.working;

            return (
              <div
                key={machine.id}
                data-machine={machine.id}
                className={`fab-room-machine ${current ? "is-current" : ""} ${place.y > 120 ? "is-bottom" : ""}`}
                onPointerEnter={(event) => {
                  if (
                    event.pointerType !== "touch" &&
                    window.matchMedia("(any-hover: hover)").matches
                  ) {
                    showPreview(machine.id);
                  }
                }}
                onPointerLeave={hidePreview}
                aria-hidden={machinesOpacity < 0.01}
                inert={machinesOpacity < 0.99}
                style={
                  {
                    opacity: machinesOpacity,
                    left: `${place.x / 6.4}%`,
                    top: `${place.y / 2.58}%`,
                  } as CSSProperties
                }
              >
                <a
                  href={`https://en.wikipedia.org/wiki/${machine.wiki}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`${machine.label} on Wikipedia, opens in a new tab`}
                  aria-describedby={
                    preview === machine.id
                      ? "fab-machine-description"
                      : undefined
                  }
                  onFocus={(event) => {
                    if (event.currentTarget.matches(":focus-visible")) {
                      showPreview(machine.id, true);
                    }
                  }}
                  onBlur={hidePreview}
                >
                  <LabMachine
                    id={machine.id}
                    working={working}
                    process={visit.process}
                    loaded={current ? seated : 0}
                    state={state}
                  />
                  <span>{machine.label}</span>
                </a>
                <button
                  className="fab-room-info"
                  aria-label={`About ${machine.label}`}
                  aria-expanded={preview === machine.id}
                  aria-controls="fab-machine-preview"
                  onClick={() => togglePreview(machine.id)}
                >
                  i
                </button>
                {current ? (
                  <span className="fab-room-progress" aria-hidden="true">
                    <i style={{ width: `${visit.process * 100}%` }} />
                  </span>
                ) : null}
              </div>
            );
          })
        : null}
      <svg
        style={{ opacity: operatorOpacity }}
        className="fab-room-person"
        viewBox="0 0 640 258"
        role="img"
        aria-label={
          visit.machine
            ? `A clean-room operator carries the wafer to the ${machines.find((m) => m.id === visit.machine)?.label.toLowerCase()}`
            : held > 0.5
              ? "A clean-room operator with our wafer"
              : "A clean-room operator entering empty-handed"
        }
      >
        <g
          transform={`translate(${person.x} ${person.y})`}
          stroke="#75877c"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <ellipse cy="12" rx="13" ry="4" fill="#697e6820" stroke="none" />
          <path
            d="M-5 5-7 12m12-7 2 7"
            fill="none"
            stroke="#7d9185"
            strokeWidth="5"
          />
          <path d="M-7-6q7-5 14 0l3 11q-10 7-20 0Z" fill="#fafbf8" />
          <path
            d="M-7-3-11 2l7 3m11-8 9 5-3 3"
            fill="none"
            stroke="#f9fbf7"
            strokeWidth="5"
          />
          <path d="M0-5v12" stroke="#ccd6ca" />
          <image
            href="/brand/favicon.svg"
            x="-7.5"
            y="-0.5"
            width="6"
            height="6"
            aria-hidden="true"
          />
          <ellipse cy="-11" rx="8" ry="9" fill="#fcfcf9" />
          <path
            d="M-5-10q5-3 10 0v5H-5Z"
            fill="#cbd8d6"
            stroke="#a7bab7"
            strokeWidth="1"
          />
          <path d="M-3-3h6" stroke="#b4c5bc" />
        </g>
        <g
          className="fab-room-wafer"
          data-placement={inMachine > 0.999 ? "loaded" : "carried"}
          opacity={(1 - seated) * held}
          transform={`translate(${waferX} ${waferY}) scale(${waferRx} ${waferRy})`}
        >
          <SmallWafer state={state} />
        </g>
      </svg>
    </div>
  );
};

export const WholeWafer = ({
  index,
  visit,
  state,
  gloves = 1,
  detail = 1,
}: {
  index: number;
  visit: Visit;
  state: PatternState;
  gloves?: number;
  detail?: number;
}) => {
  const id = useId();
  const lighting = exposureLighting(visit);
  const exposureMask =
    steps[index].phase === "expose" ? steps[index].mask : undefined;
  const showDicingLines = index === stages.finish;
  const gloveOpacity = gloves * (visit.machine ? 1 - visit.loaded : 1);
  const active = visit.working;
  const resists = maskCycles
    .map((cycle) => ({ ...cycle, ...resistState(state, cycle.id) }))
    .filter((resist) => resist.amount > 0.001);
  const activity = active ? Math.sin(Math.PI * visit.process) : 0;
  const permanentPatterns: {
    name: string;
    mask: MaskId;
    open: boolean;
    fill: string;
  }[] = [
    {
      name: "nitride",
      mask: "isolation",
      open: false,
      fill: materialColours.nitride[0],
    },
    {
      name: "isolation",
      mask: "isolation",
      open: false,
      fill: siliconColours.top,
    },
    { name: "gate", mask: "gate", open: false, fill: materialColours.gate[0] },
    { name: "contact", mask: "contact", open: true, fill: "#545961" },
    {
      name: "metal",
      mask: "metal",
      open: false,
      fill: materialColours.metal[1],
    },
    { name: "via", mask: "via", open: true, fill: "#545961" },
    {
      name: "upper",
      mask: "upper",
      open: false,
      fill: materialColours.metal[0],
    },
  ];

  return (
    <svg
      viewBox="0 0 280 264"
      role="img"
      aria-label={
        detail > 0.5
          ? "The whole wafer with a small region marked for enlargement"
          : "A continuous silicon wafer"
      }
      className="fab-whole-wafer"
    >
      <defs>
        <clipPath id={`${id}-disc`}>
          <ellipse cx="140" cy="119" rx="95" ry="76" />
        </clipPath>
        {exposureMask ? (
          <pattern
            id={`${id}-exposure-pattern`}
            width="27"
            height="27"
            x="47"
            y="52"
            patternUnits="userSpaceOnUse"
            patternTransform={`scale(${waferPatternScale})`}
            overflow="visible"
          >
            <ExposureBeams
              regions={exposureRegions(exposureMask)}
              surfaceHeight={() => 0}
              project={([x, y, z]) => [x * 0.27, (y * 27) / 65 - z * 0.45]}
            />
          </pattern>
        ) : null}
        {permanentPatterns.map((pattern) => {
          const mesh = maskMeshes[pattern.mask];

          return (
            <pattern
              key={pattern.name}
              id={`${id}-surface-${pattern.name}`}
              width="27"
              height="27"
              x="47"
              y="52"
              patternUnits="userSpaceOnUse"
              patternTransform={`scale(${waferPatternScale})`}
            >
              {mesh.xs
                .slice(0, -1)
                .flatMap((x, col) =>
                  mesh.ys
                    .slice(0, -1)
                    .map((y, row) =>
                      maskOpens(pattern.mask, x, y) === pattern.open ? (
                        <rect
                          key={`${col}-${row}`}
                          x={x * 0.27}
                          y={(y * 27) / 65}
                          width={(mesh.xs[col + 1] - x) * 0.27 + 0.05}
                          height={((mesh.ys[row + 1] - y) * 27) / 65 + 0.05}
                          fill={pattern.fill}
                        />
                      ) : null,
                    ),
                )}
            </pattern>
          );
        })}
        {resists.map((resist) => {
          const mesh = maskMeshes[resist.id];

          return (
            <pattern
              key={resist.id}
              id={`${id}-${resist.id}`}
              width="27"
              height="27"
              x="47"
              y="52"
              patternUnits="userSpaceOnUse"
              patternTransform={`scale(${waferPatternScale})`}
            >
              {mesh.xs.slice(0, -1).flatMap((x, col) =>
                mesh.ys.slice(0, -1).map((y, row) => {
                  const open = maskOpens(resist.id, x, y);

                  return (
                    <rect
                      key={`${col}-${row}`}
                      x={x * 0.27}
                      y={(y * 27) / 65}
                      width={(mesh.xs[col + 1] - x) * 0.27 + 0.1}
                      height={((mesh.ys[row + 1] - y) * 27) / 65 + 0.1}
                      fill={
                        open
                          ? exposedResistColour(resist.expose, lighting.glow)
                          : materialColours.resist[0]
                      }
                      opacity={open ? 1 - resist.develop : 1}
                    />
                  );
                }),
              )}
            </pattern>
          );
        })}
      </defs>
      <ellipse
        cx="140"
        cy="201"
        rx="83"
        ry="10"
        fill="#ddd9ce"
        opacity={0.35 * gloveOpacity}
      />
      <g
        className="fab-gloves"
        opacity={gloveOpacity}
        fill="#edf1eb"
        stroke="#b8c7bd"
        strokeWidth="1.3"
      >
        <path d="M5 228 35 194q8-11 10-32l4-28q2-9 8-8 6 0 5 9l-2 27 13-19q5-7 10-4 5 4 0 11l-14 25 2 25-32 47Z" />
        <path d="M275 228 245 194q-8-11-10-32l-4-28q-2-9-8-8-6 0-5 9l2 27-13-19q-5-7-10-4-5 4 0 11l14 25-2 25 32 47Z" />
        <path
          d="m12 220 32 24-10 16L0 240m268-20-32 24 10 16 34-20"
          fill="#dce5dd"
        />
        <path d="m44 188 14-17m178 17-14-17" fill="none" />
      </g>
      <path
        d="M45 119v5a95 76 0 0 0 190 0v-5"
        fill={siliconColours.side}
        stroke={siliconColours.edge}
        strokeWidth="1.2"
      />
      <ellipse
        cx="140"
        cy="119"
        rx="95"
        ry="76"
        fill={siliconColours.top}
        stroke={siliconColours.edge}
        strokeWidth="1.2"
      />
      <g clipPath={`url(#${id}-disc)`}>
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={materialColours.insulator[0]}
          opacity={state.oxide}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={`url(#${id}-surface-isolation)`}
          opacity={state.padOxideStrip * (1 - state.gateOxide)}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={materialColours.nitride[0]}
          opacity={
            state.nitride *
            (1 - state.prepareIsolation) *
            (1 - state.nitrideStrip)
          }
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={`url(#${id}-surface-nitride)`}
          opacity={
            state.nitride * state.prepareIsolation * (1 - state.nitrideStrip)
          }
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={materialColours.gate[0]}
          opacity={state.poly * (1 - state.patternGate)}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={`url(#${id}-surface-gate)`}
          opacity={state.poly * state.patternGate}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={materialColours.insulator[0]}
          opacity={state.cover * 0.6}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={`url(#${id}-surface-contact)`}
          opacity={state.contacts * (1 - state.metalFill)}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={materialColours.metal[0]}
          opacity={state.metal * (1 - state.metalPattern)}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={`url(#${id}-surface-metal)`}
          opacity={state.metal * state.metalPattern}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={materialColours.insulator[0]}
          opacity={state.interconnect * 0.25}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={`url(#${id}-surface-via)`}
          opacity={state.viaOpen * (1 - state.viaFill)}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={materialColours.metal[0]}
          opacity={state.upperMetal * (1 - state.upperMetalPattern)}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={`url(#${id}-surface-upper)`}
          opacity={state.upperMetal * state.upperMetalPattern}
        />
        {resists.map((resist) => (
          <ellipse
            key={resist.id}
            cx="140"
            cy="119"
            rx={95 * Math.min(1, resist.coat * 1.6)}
            ry={76 * Math.min(1, resist.coat * 1.6)}
            fill={`url(#${id}-${resist.id})`}
            opacity={resist.amount}
          />
        ))}
        {showDicingLines ? (
          <g
            stroke="#6d8580"
            strokeWidth=".6"
            opacity={0.28 * portion(visit.progress, 0, 0.28)}
          >
            {Array.from({ length: 8 }, (_, i) => (
              <path key={`x${i}`} d={`M${47 + i * 27} 40v160`} />
            ))}
            {Array.from({ length: 6 }, (_, i) => (
              <path key={`y${i}`} d={`M40 ${52 + i * 27}h200`} />
            ))}
          </g>
        ) : null}
        {active && visit.machine === "coat" ? (
          <g
            transform={`rotate(${visit.process * 1080} 140 119)`}
            stroke="#f9eaf0"
            fill="none"
            opacity={activity * 0.7}
          >
            <ellipse
              cx="140"
              cy="119"
              rx="56"
              ry="43"
              strokeDasharray="30 45"
              strokeWidth="2"
            />
            <ellipse
              cx="140"
              cy="119"
              rx="77"
              ry="60"
              strokeDasharray="45 65"
            />
          </g>
        ) : null}
        {active &&
        (visit.machine === "furnace" || visit.machine === "anneal") ? (
          <rect
            x="40"
            y="40"
            width="200"
            height="160"
            fill="#d9a46c"
            opacity={activity * 0.25}
          />
        ) : null}
        {lighting.beam > 0 && exposureMask ? (
          <rect
            data-wafer-exposure-beam={exposureMask}
            x="40"
            y="40"
            width="200"
            height="160"
            fill={`url(#${id}-exposure-pattern)`}
            opacity={lighting.beam * 0.55}
          />
        ) : null}
        <WaferProcessEffects visit={visit} index={index} state={state} />
      </g>
      {detail > 0 ? (
        <rect
          opacity={detail}
          className="fab-wafer-detail-region"
          x={waferDetailRegion.x}
          y={waferDetailRegion.y}
          width={waferDetailRegion.size}
          height={waferDetailRegion.size}
          fill="none"
          stroke="var(--color-kiln-600)"
          strokeWidth="1.2"
        />
      ) : null}
      {active && visit.machine === "coat" ? (
        <path
          d={`M140 ${28 + visit.process * 57}q-8 12 0 12t0-12`}
          fill="#b48fa6"
          opacity={Math.sin(Math.PI * Math.min(1, visit.process * 2))}
        />
      ) : null}
    </svg>
  );
};
