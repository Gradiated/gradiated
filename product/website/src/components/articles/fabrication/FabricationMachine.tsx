import { useId } from "react";
import {
  exposedResistColour,
  materialColours,
  siliconColours,
} from "./materials";
import type { MachineId } from "./model";
import {
  exposureRegions,
  machineIconSize,
  machineLoadingSpots,
  portion,
  resistState,
} from "./process";
import type { PatternState } from "./process";
import { maskCycles } from "./sequence";

const maskCoverage = maskCycles.map(({ id }) => ({
  id,
  open:
    exposureRegions(id).reduce(
      (area, [x0, x1, y0, y1]) => area + (x1 - x0) * (y1 - y0),
      0,
    ) / 6500,
}));

export const SmallWafer = ({ state }: { state: PatternState }) => {
  const films = [
    [materialColours.insulator[0], state.oxide],
    [siliconColours.top, state.prepareIsolation * (1 - state.gateOxide) * 0.55],
    [materialColours.gate[0], state.poly * (1 - state.patternGate * 0.88)],
    [materialColours.insulator[0], state.cover * 0.6],
    [materialColours.metal[0], state.metal * (1 - state.metalPattern * 0.82)],
    [materialColours.insulator[0], state.interconnect * 0.25],
    [
      materialColours.metal[0],
      state.upperMetal * (1 - state.upperMetalPattern * 0.88),
    ],
  ] as const;

  return (
    <g data-small-wafer="true">
      <circle r="1" fill={siliconColours.top} />
      {films.map(([fill, opacity], i) => (
        <circle key={i} r="1" fill={fill} opacity={opacity} />
      ))}
      {maskCoverage.map(({ id, open }) => {
        const resist = resistState(state, id);

        return (
          <circle
            key={id}
            r={Math.min(1, resist.coat * 1.6)}
            fill={exposedResistColour(resist.expose * open)}
            opacity={resist.amount * (1 - resist.develop * open)}
          />
        );
      })}
      <circle
        r="1"
        fill="none"
        stroke={siliconColours.edge}
        strokeWidth=".08"
      />
    </g>
  );
};

const particlePhase = (process: number, i: number, cycles = 3) =>
  (process * cycles + i * 0.381966) % 1;

export const LabMachine = ({
  id,
  working,
  process,
  loaded,
  state,
}: {
  id: MachineId;
  working: boolean;
  process: number;
  loaded: number;
  state: PatternState;
}) => {
  const clip = useId();
  const spot = machineLoadingSpots[id];
  const wet = id === "develop" || id === "strip";
  const heat = id === "furnace" || id === "anneal";
  const deposition = id === "deposit" || id === "metal";
  const envelope = working ? Math.sin(Math.PI * process) : 0;
  const oscillation = working ? Math.sin(process * Math.PI * 4) : 0;
  const padX = 36 + oscillation * 4;
  const lensX = working ? 40 - Math.sin(process * Math.PI) * 12 : 40;
  const lensY = working ? 26 + Math.sin(process * Math.PI * 2) * 4 : 26;

  return (
    <svg
      viewBox={`0 0 ${machineIconSize.width} ${machineIconSize.height}`}
      data-machine-icon={id}
      data-process={process.toFixed(2)}
      data-loaded={loaded.toFixed(2)}
      aria-hidden="true"
    >
      <defs>
        <clipPath id={clip}>
          <ellipse cx={spot.x} cy={spot.y} rx={spot.rx} ry={spot.ry} />
        </clipPath>
      </defs>
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
      {id === "coat" || id === "polish" ? (
        <circle cx="36" cy={spot.y} r="18" fill="#e5e9e1" stroke="#a3b2a5" />
      ) : id === "furnace" ? (
        <>
          <rect
            x="11"
            y="12"
            width="50"
            height="29"
            rx="14"
            fill="#e7dcca"
            stroke="#b29b7e"
          />
          <rect
            x="11"
            y="12"
            width="50"
            height="29"
            rx="14"
            fill="#e8b78e"
            opacity={envelope * 0.6}
          />
          <path d="M7 26h7m44 0h7" stroke="#b29b7e" strokeWidth="3" />
          {[20, 25, 47, 52].map((x) => (
            <path
              key={x}
              d={`M${x} 18v18`}
              stroke="#cf9b6c"
              strokeWidth="2"
              opacity={0.4 + envelope * 0.6}
              strokeLinecap="round"
            />
          ))}
        </>
      ) : id === "implant" ? (
        <>
          <rect
            x="9"
            y="17"
            width="18"
            height="20"
            rx="3"
            fill="#ccd8e0"
            stroke="#99adbc"
          />
          <path d="M14 22v10m5-10v10" stroke="#a1b4c1" />
          <circle cx="53" cy="27" r="13" fill="#e4ebee" stroke="#a8b9c3" />
          <path d="M27 23h14m-14 8h14" stroke="#bbcbd6" />
        </>
      ) : id === "inspect" ? (
        <circle cx="32" cy="30" r="18" fill="#e4e9e0" stroke="#a6b09e" />
      ) : wet ? (
        <>
          <path
            d="M12 22v19q24 9 48 0V22"
            fill={id === "develop" ? "#d7e8e9" : "#eadbe4"}
            stroke={id === "develop" ? "#9cb9b8" : "#bb9aaa"}
          />
          <path
            d={`M12 22q6 ${-1.2 + oscillation * 0.6} 12 0t12 0 12 0 12 0`}
            fill="none"
            stroke="#f9fcfa"
            strokeWidth="1.2"
          />
        </>
      ) : (
        <>
          <rect
            x="11"
            y="9"
            width="50"
            height="36"
            rx="8"
            fill={
              id === "litho"
                ? "#eeebf3"
                : id === "etch"
                  ? "#eee3eb"
                  : heat
                    ? "#ebe2d6"
                    : id === "metal"
                      ? "#e7e3d9"
                      : "#e0e8df"
            }
            stroke={
              id === "litho" ? "#c1bacd" : id === "etch" ? "#bda7ba" : "#a5b6a5"
            }
          />
          {heat ? (
            <rect
              x="11"
              y="9"
              width="50"
              height="36"
              rx="8"
              fill="#f1bf8e"
              opacity={envelope * 0.35}
            />
          ) : null}
        </>
      )}
      <ellipse
        cx={spot.x}
        cy={spot.y}
        rx={spot.rx + 0.8}
        ry={spot.ry + 0.8}
        fill="none"
        stroke="#b2bdb3"
        strokeWidth=".8"
      />
      <g
        opacity={loaded}
        transform={`translate(${spot.x} ${spot.y}) scale(${spot.rx} ${spot.ry})`}
      >
        <SmallWafer state={state} />
      </g>
      {id === "coat" ? (
        <>
          <g clipPath={`url(#${clip})`} opacity={loaded * envelope}>
            <g transform={`rotate(${process * 1080} 36 29)`}>
              <path
                d="M25 25q3-7 11-7m11 15q-3 7-11 7"
                fill="none"
                stroke="#e9ddee"
                strokeWidth="1"
                strokeLinecap="round"
              />
            </g>
          </g>
          <path
            d="M14 9h22v10"
            fill="none"
            stroke="#879e8e"
            strokeWidth="3"
            strokeLinecap="round"
          />
          {working
            ? [0, 1].map((i) => {
                const phase = particlePhase(process, i, 3);

                return (
                  <ellipse
                    key={i}
                    cx="36"
                    cy={20 + phase * 7}
                    rx="1.3"
                    ry="1.7"
                    fill={materialColours.resist[0]}
                    opacity={envelope * Math.sin(Math.PI * phase)}
                  />
                );
              })
            : null}
        </>
      ) : id === "polish" ? (
        <>
          <path
            d={`M18 10H${padX}V25`}
            fill="none"
            stroke="#879e8e"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <g
            transform={`translate(${padX} 28) rotate(${working ? process * 720 : 0})`}
            data-polishing-pad="true"
          >
            <circle r="7" fill="#e5e9d9" stroke="#91a284" strokeWidth="1.2" />
            <path d="M-3-3l6 6m-6 0 6-6" stroke="#b1bfa1" strokeWidth="1" />
          </g>
        </>
      ) : id === "litho" ? (
        <>
          <path
            d="M12 13 25 17 13 27 51 14 36 31"
            fill="none"
            stroke="#aa86cf"
            strokeWidth="1.5"
            opacity={0.25 + envelope * 0.75}
            strokeLinejoin="round"
          />
          <path
            d="m20 13 10 8m-20 3 7 8m30-22 8 8"
            stroke="#777186"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <path
            d="m20 12 10 8m-20 3 7 8m30-22 8 8"
            stroke="#e1dce9"
            strokeWidth="1"
          />
          <circle cx="12" cy="13" r="2" fill="#9d72c6" />
          <path d="M23 40h26m-20 0v3m14-3v3" stroke="#aaa5b6" strokeWidth="2" />
        </>
      ) : wet ? (
        <>
          <path
            d="M15 11h21v7"
            fill="none"
            stroke="#92aaa6"
            strokeWidth="3"
            strokeLinecap="round"
          />
          {working
            ? [0, 1, 2, 3, 4].map((i) => {
                const phase = particlePhase(process, i, 2);
                const fade = envelope * Math.sin(Math.PI * phase);

                return (
                  <g key={i} opacity={fade}>
                    {i < 2 ? (
                      <path
                        d={`M${33 + i * 6} ${19 + phase * 12}v2`}
                        stroke="#83abb3"
                        strokeWidth="1.2"
                        strokeLinecap="round"
                      />
                    ) : null}
                    <circle
                      cx={25 + (i % 3) * 6 + phase * 7}
                      cy={34 - Math.sin(phase * Math.PI) * (3 + (i % 2))}
                      r={0.9 - phase * 0.4}
                      fill={materialColours.resist[0]}
                    />
                  </g>
                );
              })
            : null}
        </>
      ) : id === "anneal" ? (
        <>
          {[22, 36, 50].map((x, i) => {
            const sway = working
              ? envelope * Math.sin(process * Math.PI * 6 + i * 0.8) * 2
              : 0;

            return (
              <g key={x}>
                <path
                  d={`M${x - 4} 15h8`}
                  stroke="#c5ad92"
                  strokeWidth="3"
                  strokeLinecap="round"
                />
                <path
                  d={`M${x - 4} 15h8`}
                  stroke="#d78958"
                  strokeWidth="3"
                  strokeLinecap="round"
                  opacity={envelope}
                />
                <path
                  d={`M${x} 19c${-2 + sway} 2 ${2 + sway} 4 0 6s${-2 - sway} 4 0 6`}
                  fill="none"
                  stroke="#d9a071"
                  strokeWidth="1"
                  opacity={0.25 + envelope * 0.55}
                />
              </g>
            );
          })}
        </>
      ) : id === "implant" ? (
        <>
          {[0, 1, 2, 3].map((i) => {
            const phase = particlePhase(process, i, 3);

            return (
              <circle
                key={i}
                cx={28 + (working ? phase : i / 4) * 24}
                cy={26 + ((i % 3) - 1) * 2}
                r=".9"
                fill="#598da8"
                opacity={working ? envelope * Math.sin(Math.PI * phase) : 0}
              />
            );
          })}
        </>
      ) : id === "inspect" ? (
        <g
          transform={`translate(${lensX} ${lensY})`}
          data-inspection-lens="true"
        >
          <path
            d="m6-6 9-10"
            stroke="#859780"
            strokeWidth="4"
            strokeLinecap="round"
          />
          <circle r="8" fill="#f4f7ec80" stroke="#859780" strokeWidth="2" />
          <path d="M-4 0h8M0-4v8" stroke="#9dad8c" strokeWidth="1" />
        </g>
      ) : deposition || id === "etch" ? (
        <>
          {id === "metal" ? (
            <>
              <path d="M22 14h28v5H22Z" fill="#b5b3ab" stroke="#898c88" />
              <path
                d="M25 20h22"
                stroke="#c4a1d3"
                strokeWidth="2"
                opacity={0.25 + envelope * 0.65}
              />
            </>
          ) : (
            <path
              d="M36 8v6m-14 1h28v4H22Z"
              fill={id === "etch" ? "#bdaebf" : "#becfbd"}
              stroke="#8ea68f"
              strokeWidth="1.5"
            />
          )}
          {[23, 29, 36, 43, 49].map((x, i) => {
            const phase = particlePhase(process, i, id === "etch" ? 4 : 2);

            return (
              <path
                key={x}
                d={`M${x} ${22 + (working ? phase : (i % 3) / 3) * 10}v${id === "etch" ? 2 : 0.4}`}
                stroke={
                  id === "etch"
                    ? "#d56c71"
                    : id === "metal"
                      ? "#8e9292"
                      : "#9eb69a"
                }
                strokeWidth={id === "etch" ? 1.3 : 1.7}
                strokeLinecap="round"
                opacity={working ? envelope * Math.sin(Math.PI * phase) : 0}
              />
            );
          })}
          {id === "etch" && working
            ? [0, 1, 2].map((i) => {
                const phase = particlePhase(process, i, 3);

                return (
                  <circle
                    key={i}
                    cx={29 + i * 7 + (i - 1) * phase * 4}
                    cy={34 - phase * 6}
                    r={0.8 - phase * 0.4}
                    fill="#b5a1b2"
                    opacity={envelope * Math.sin(Math.PI * phase)}
                  />
                );
              })
            : null}
        </>
      ) : null}
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
};
