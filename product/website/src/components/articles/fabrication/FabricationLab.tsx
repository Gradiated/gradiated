import { useId } from "react";
import type { CSSProperties } from "react";
import { machines } from "./model";
import { siliconColours } from "./materials";
import type { MachineId } from "./model";
import {
  ease,
  resistState,
  maskMeshes,
  maskOpens,
  machineIconSize,
  machineLoadingPoint,
  machinePlaces,
  portion,
  stages,
  waferDetailRegion,
} from "./process";
import type { PatternState, Visit } from "./process";
import { maskCycles } from "./sequence";
import type { MaskId } from "./sequence";

const LabMachine = ({
  id,
  working,
  process,
}: {
  id: MachineId;
  working: boolean;
  process: number;
}) => (
  <svg
    viewBox={`0 0 ${machineIconSize.width} ${machineIconSize.height}`}
    data-machine-icon={id}
    aria-hidden="true"
  >
    <rect x="3" y="5" width="66" height="50" rx="7" fill="#dce2dc" />
    <rect
      x="3"
      y="2"
      width="66"
      height="50"
      rx="7"
      fill="#f9faf5"
      stroke="#8c9c90"
    />
    <g>
      {id === "coat" || id === "polish" ? (
        <>
          <circle cx="36" cy="27" r="19" fill="#e3e9e1" stroke="#a3b2a5" />
          <g transform={`rotate(${process * 1080} 36 27)`}>
            <circle cx="36" cy="27" r="13" fill="#c6cfc9" stroke="#738779" />
            <path
              d="M36 14v5m0 16v5m-13-13h5m16 0h5"
              stroke="#edf2eb"
              strokeWidth="2"
            />
          </g>
          <path
            d={id === "coat" ? "M18 8h18v12" : "M18 8h18v15h10v8H26v-8h10"}
            fill="none"
            stroke="#879e8e"
            strokeWidth="4"
          />
        </>
      ) : id === "litho" ? (
        <>
          <rect
            x="11"
            y="11"
            width="50"
            height="32"
            rx="3"
            fill="#e6e3ec"
            stroke="#b5b0c0"
          />
          <path d="M18 15h36v24H18Z" fill="#cfccd9" />
          <path d="M18 27h36m-18-12v24" stroke="#f5f3f8" />
          <circle
            cx="36"
            cy="27"
            r="9"
            fill={working ? "#c1a5dc" : "#9e96b1"}
            stroke="#8b819f"
          />
          <circle
            cx="36"
            cy="27"
            r="4"
            fill="#f1e5fc"
            opacity={working ? 1 : 0.4}
          />
        </>
      ) : id === "develop" || id === "strip" ? (
        <>
          {[
            { x: 8, width: 15 },
            { x: 27, width: 18 },
            { x: 49, width: 15 },
          ].map((bath) => (
            <rect
              key={bath.x}
              x={bath.x}
              y="13"
              width={bath.width}
              height="28"
              rx="2"
              fill={id === "develop" ? "#cddfe0" : "#e2ccd6"}
              stroke={id === "develop" ? "#9cb9b8" : "#bb9aaa"}
            />
          ))}
          <path d="M12 21h7m13 5h8m13-6h7" stroke="#f3faf7" strokeWidth="2" />
        </>
      ) : id === "furnace" ? (
        <>
          <rect
            x="12.5"
            y="13"
            width="47"
            height="28"
            rx="13"
            fill={working ? "#dfb69b" : "#e0d2bf"}
            stroke="#b29b7e"
          />
          {[22.5, 31.5, 40.5, 49.5].map((x) => (
            <path key={x} d={`M${x} 16v22`} stroke="#f8eee1" strokeWidth="2" />
          ))}
          <path d="M6.5 27h6m47 0h6" stroke="#b29b7e" strokeWidth="4" />
        </>
      ) : id === "anneal" ? (
        <>
          <circle
            cx="36"
            cy="27"
            r="20"
            fill={working ? "#e5b496" : "#e1d4c5"}
            stroke="#b39b80"
          />
          <circle cx="36" cy="27" r="13" fill="#f6e8d9" stroke="#c5ac90" />
          <path
            d="M20 14l4 4m28-4-4 4M20 40l4-4m28 4-4-4"
            stroke={working ? "#ca825c" : "#bca58d"}
            strokeWidth="3"
          />
        </>
      ) : id === "metal" ? (
        <>
          <circle cx="36" cy="28" r="18" fill="#ded7c5" stroke="#b0a487" />
          <circle cx="36" cy="28" r="12" fill="#f4eee0" stroke="#bdaf91" />
          <rect
            x="23"
            y="8"
            width="26"
            height="6"
            rx="2"
            fill="#c5ad70"
            stroke="#a78f56"
          />
          <path
            d="M28 17v6m8-6v6m8-6v6"
            stroke={working ? "#b79547" : "#c6b996"}
            strokeWidth="2"
          />
        </>
      ) : id === "implant" ? (
        <>
          <rect
            x="8"
            y="17.5"
            width="28"
            height="19"
            rx="3"
            fill="#c9d4dd"
            stroke="#99adbc"
          />
          <path d="M35 27h16" stroke="#9caec4" strokeWidth="5" />
          <circle cx="54" cy="27" r="10" fill="#dae2e8" stroke="#99adbc" />
          <path d="M14 24h15m-15 6h15" stroke="#9aafbf" />
        </>
      ) : id === "inspect" ? (
        <>
          <rect
            x="11"
            y="11"
            width="50"
            height="32"
            rx="3"
            fill="#e4e5d4"
            stroke="#b6b89e"
          />
          <path d="M18 27h36m-18-12v24" stroke="#b6b89e" />
          <circle
            cx="36"
            cy="27"
            r="10"
            fill="#f2f1e4"
            stroke="#8f997e"
            strokeWidth="2"
          />
          <circle cx="36" cy="27" r="4" fill="#9aab94" />
        </>
      ) : (
        <>
          <circle
            cx="36"
            cy="27"
            r="20"
            fill={id === "etch" ? "#e2d8e7" : "#d1ddd7"}
            stroke="#a6b3a8"
          />
          <circle cx="36" cy="27" r="13" fill="#f5f6ef" stroke="#acb9ac" />
          <path
            d="M16 27h8m24 0h8M36 7v8m0 24v8"
            stroke="#94a897"
            strokeWidth="3"
          />
          <circle
            cx="36"
            cy="27"
            r="6"
            fill={working ? "#b8a6cf" : "#c9d2ca"}
          />
        </>
      )}
    </g>
    <rect
      x="23"
      y="48"
      width="26"
      height="6"
      rx="2"
      fill="#d1dacf"
      stroke="#a4b3a3"
    />
  </svg>
);

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
  preview,
  showPreview,
  hidePreview,
  togglePreview,
}: {
  visit: Visit;
  preview?: MachineId;
  showPreview: (id: MachineId, immediate?: boolean) => void;
  hidePreview: () => void;
  togglePreview: (id: MachineId) => void;
}) => {
  const home = { x: 320, y: 126 };
  const destination = visit.machine ? machinePlaces[visit.machine] : home;
  const origin = visit.from ? machinePlaces[visit.from] : home;
  const person = walk(origin, destination, portion(visit.progress, 0, 0.25));
  const inMachine = visit.machine ? visit.loaded : 0;
  const loadingPoint = visit.machine
    ? machineLoadingPoint(visit.machine)
    : home;
  const heldX = person.x + 12;
  const heldY = person.y + 2;
  const waferX = heldX + (loadingPoint.x - heldX) * inMachine;
  const waferY = heldY + (loadingPoint.y - heldY) * inMachine;
  const waferTilt = 0.625 + 0.375 * inMachine;

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
          fill="#edf0e8"
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
        <path d="M24 126h592" stroke="#e4e9df" strokeWidth="48" />
        <path
          d="M24 109h592m-592 34h592"
          stroke="#d5ded1"
          strokeWidth="1"
          strokeDasharray="3 7"
        />
      </svg>
      {machines.map((machine) => {
        const place = machinePlaces[machine.id];
        const current = visit.machine === machine.id;
        const working = current && visit.working;

        return (
          <div
            key={machine.id}
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
            style={
              {
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
                preview === machine.id ? "fab-machine-description" : undefined
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
      })}
      <svg
        className="fab-room-person"
        viewBox="0 0 640 258"
        role="img"
        aria-label={
          visit.machine
            ? `A clean-room operator carries the wafer to the ${machines.find((m) => m.id === visit.machine)?.label.toLowerCase()}`
            : "A clean-room operator with our wafer"
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
          opacity={1 - 0.12 * inMachine}
          transform={`translate(${waferX} ${waferY}) scale(1 ${waferTilt})`}
        >
          <circle
            className="fab-room-wafer-disc"
            r="8"
            fill={siliconColours.top}
            stroke={siliconColours.edge}
            strokeWidth="1.2"
          />
        </g>
      </svg>
    </div>
  );
};

const waferPatternScale = 0.3;

export const WholeWafer = ({
  index,
  visit,
  state,
}: {
  index: number;
  visit: Visit;
  state: PatternState;
}) => {
  const id = useId();
  const showDicingLines = index === stages.finish;
  const active = visit.working;
  const resists = maskCycles
    .map((cycle) => ({ ...cycle, ...resistState(state, cycle.id) }))
    .filter((resist) => resist.amount > 0.001);
  const windows = Array.from({ length: 35 }, (_, i) => ({
    x: 47 + (i % 7) * 27,
    y: 52 + Math.floor(i / 7) * 27,
  }));
  const activity = active ? Math.sin(Math.PI * visit.process) : 0;
  const permanentPatterns: { mask: MaskId; open: boolean; fill: string }[] = [
    { mask: "isolation", open: true, fill: siliconColours.top },
    { mask: "gate", open: false, fill: "#829a75" },
    { mask: "contact", open: true, fill: "#545961" },
    { mask: "metal", open: false, fill: "#8899af" },
    { mask: "via", open: true, fill: "#545961" },
    { mask: "upper", open: false, fill: "#bdc7d4" },
  ];

  return (
    <svg
      viewBox="0 0 280 264"
      role="img"
      aria-label="The whole wafer with gloved hands at its edges and a marked region enlarged in the view on the right"
      className="fab-whole-wafer"
    >
      <defs>
        <clipPath id={`${id}-disc`}>
          <ellipse cx="140" cy="119" rx="95" ry="76" />
        </clipPath>
        {permanentPatterns.map((pattern) => {
          const mesh = maskMeshes[pattern.mask];

          return (
            <pattern
              key={pattern.mask}
              id={`${id}-surface-${pattern.mask}`}
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
                          ? `color-mix(in srgb, #d7bdce, #b795d1 ${resist.expose * 65}%)`
                          : "#d7bdce"
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
      <ellipse cx="140" cy="201" rx="83" ry="10" fill="#ddd9ce" opacity=".35" />
      <g
        className="fab-gloves"
        opacity={1 - visit.loaded * 0.92}
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
          fill="#c5dce1"
          opacity={state.oxide}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill={`url(#${id}-surface-isolation)`}
          opacity={state.prepareIsolation * (1 - state.gateOxide)}
        />
        <rect
          x="40"
          y="40"
          width="200"
          height="160"
          fill="#94aa88"
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
          fill="#bdd5dc"
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
          fill="#b1bac8"
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
          fill="#bdd5dc"
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
          fill="#b1bac8"
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
        (visit.machine === "develop" || visit.machine === "strip") ? (
          <g fill="#edf6f7" opacity={activity * 0.55}>
            {windows
              .filter((_, i) => i % 3 === 0)
              .map(({ x, y }, i) => (
                <circle
                  key={i}
                  cx={x + 13}
                  cy={y + 15 - visit.process * 15}
                  r="3"
                />
              ))}
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
      </g>
      {index >= 1 ? (
        <rect
          className="fab-wafer-detail-region"
          x={waferDetailRegion.x}
          y={waferDetailRegion.y}
          width={waferDetailRegion.size}
          height={waferDetailRegion.size}
          fill="none"
          stroke="#986b49"
          strokeWidth="1.1"
        />
      ) : null}
      {active && visit.machine === "litho" ? (
        <path
          d="m90 22 18 80h65l17-80Z"
          fill="#c1a3e4"
          opacity={activity * 0.35}
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
