import { useId, useState } from "react";
import type { ReactNode } from "react";
import { Block, Label, Wire } from "./drawing";
import type { MapHighlight } from "./opening";
import { ResourceColumnTracks, ResourceColumnLogic } from "./ResourceColumns";

export type MapFocus = "block" | "junction";

export const chipMapViewBox = "-40 0 640 560";
export const chipMapPositions = [124, 244, 364] as const;
export const chipMapChannels = [100, 220, 340, 460] as const;

const LogicMapBlock = ({
  x,
  y,
  h,
  detail,
  active,
}: {
  x: number;
  y: number;
  h: number;
  detail?: string;
  active: boolean;
}) => {
  const [lastDetail, setLastDetail] = useState(detail);
  if (detail !== undefined && detail !== lastDetail) setLastDetail(detail);

  const shownDetail = detail ?? lastDetail;

  return (
    <g className="fpga-map-logic-block" data-detail={detail !== undefined}>
      <Block x={x} y={y} w={72} h={h} label="CLB" active={active} />
      <g
        className="fpga-tour-layer"
        data-visible={detail !== undefined}
        aria-hidden={detail === undefined}
      >
        <Label
          x={x + 36}
          y={y + h / 2 + 22}
          small
          value={shownDetail !== undefined && !/[a-z]/i.test(shownDetail)}
        >
          {shownDetail}
        </Label>
      </g>
    </g>
  );
};

export const ChipMap = ({
  focus = "block",
  miniature = false,
  rule,
  inputs,
  output,
  source = 1,
  highlight,
  selectedBlocks,
  expanded = false,
  columns = false,
  blockDetails,
  blockVerticalInsets,
  hideVerticalConnectionsFor,
}: {
  focus?: MapFocus;
  miniature?: boolean;
  rule?: string;
  inputs?: readonly [number, number];
  output?: ReactNode;
  source?: 1 | 4;
  highlight?: MapHighlight;
  selectedBlocks?: readonly number[];
  expanded?: boolean;
  columns?: boolean;
  blockDetails?: Record<number, string>;
  blockVerticalInsets?: Record<number, readonly [number, number]>;
  hideVerticalConnectionsFor?: number;
}) => {
  const id = useId();
  const extension = columns ? 844 : expanded ? 204 : 0;
  const routing = focus === "junction";
  const showCircuitPins = !highlight && !routing && !miniature;
  const positions = chipMapPositions;
  const channels = chipMapChannels;
  const lanes = [-8, 0, 8];
  const fades = [
    { side: "left", x1: 84, y1: 0, x2: 92, y2: 0 },
    { side: "right", x1: 476, y1: 0, x2: 468, y2: 0 },
    { side: "top", x1: 0, y1: 84, x2: 0, y2: 92 },
    { side: "bottom", x1: 0, y1: 476, x2: 0, y2: 468 },
  ];

  const fadedWire = (side: string, d: string, active = false) => (
    <g>
      <path
        d={d}
        className="fpga-wire"
        style={{ stroke: `url(#${id}-${side}-wire)` }}
      />
      {active && (
        <path
          d={d}
          className="fpga-signal"
          style={{ stroke: `url(#${id}-${side}-signal)` }}
          pathLength={1}
        />
      )}
    </g>
  );

  return (
    <g
      className="fpga-map-drawing"
      data-expanded={expanded}
      data-columns={columns}
      data-highlight={highlight}
    >
      <defs>
        {fades.flatMap(({ side, ...gradient }) =>
          ["wire", "signal"].map((kind) => (
            <linearGradient
              key={`${side}-${kind}`}
              id={`${id}-${side}-${kind}`}
              gradientUnits="userSpaceOnUse"
              {...gradient}
            >
              <stop
                offset="0"
                stopColor={
                  kind === "signal"
                    ? "var(--signal-stroke)"
                    : "var(--fpga-map-track-ink, var(--fpga-ink))"
                }
                stopOpacity={0}
              />
              <stop
                offset="1"
                stopColor={
                  kind === "signal"
                    ? "var(--signal-stroke)"
                    : "var(--fpga-map-track-ink, var(--fpga-ink))"
                }
              />
            </linearGradient>
          )),
        )}
      </defs>
      <rect
        x={48}
        y={columns ? -192 : 48}
        width={464 + extension}
        height={columns ? 1304 : 464}
        rx={9}
        className="fpga-chip-outline"
      />
      <g className="fpga-map-available">
        <ResourceColumnTracks visible={columns} />
        <g
          className="fpga-tour-layer fpga-map-extension"
          data-visible={expanded && !columns}
          aria-hidden={!expanded || columns}
        >
          {[100, 220, 340, 460].flatMap((y) =>
            [-8, 0, 8].map((lane) => (
              <Wire key={`${y}-${lane}`} d={`M468 ${y + lane}H672`} />
            )),
          )}
        </g>

        {channels.flatMap((centre) =>
          lanes.map((lane) => {
            const track = centre + lane;

            return (
              <g key={track}>
                <Wire d={`M92 ${track}H468M${track} 92V468`} />
                {fadedWire("left", `M84 ${track}H92`)}
                {fadedWire("right", `M468 ${track}H476`)}
                {fadedWire("top", `M${track} 84V92`)}
                {fadedWire("bottom", `M${track} 468V476`)}
              </g>
            );
          }),
        )}
        <g className="fpga-map-local-wires">
          {positions.map((y, row) =>
            positions.map((x, column) => {
              const number = row * 3 + column + 1;
              const [top, bottom] = blockVerticalInsets?.[number] ?? [0, 0];

              return (
                <g key={`${x}-${y}`}>
                  {[16, 36, 56].map((offset, lane) => (
                    <Wire
                      key={offset}
                      d={`M${channels[column] + lanes[lane]} ${y + offset}H${x}M${x + 72} ${y + offset}H${channels[column + 1] + lanes[lane]}${number === hideVerticalConnectionsFor ? "" : `M${x + offset} ${channels[row] + lanes[lane]}V${y + top}M${x + offset} ${y + (columns ? 36 : 72) - bottom}V${channels[row + 1] + lanes[lane]}`}`}
                    />
                  ))}
                </g>
              );
            }),
          )}
        </g>
      </g>
      {routing ? (
        <>
          <Wire d="M140 196V212H212" active={!miniature && source === 1} />
          <Wire d="M180 244V228H212" active={!miniature && source === 4} />
          <g className="fpga-map-junction-symbol">
            <path d="M212 204L228 210V230L212 236Z" className="fpga-gate" />
            <Wire
              d={source === 1 ? "M212 212L228 220" : "M212 228L228 220"}
              active={!miniature}
            />
          </g>
          <Wire d="M228 220H280V244" active={!miniature} />
        </>
      ) : !highlight ? (
        <>
          <Wire
            d="M92 100H100V160H124M92 220H108V180H124M196 160H220V220H468"
            active={!miniature}
          />
          {fadedWire("left", "M84 100H92M84 220H92", !miniature)}
          {fadedWire("right", "M468 220H476", !miniature)}
          {!miniature && (
            <>
              <Label x={24} y={105} small value anchor="end">
                {inputs ? `A = ${inputs[0]}` : "A"}
              </Label>
              <Label x={24} y={225} small value anchor="end">
                {inputs ? `B = ${inputs[1]}` : "B"}
              </Label>
              <Label x={536} y={212} small anchor="start">
                Output
              </Label>
              {output !== undefined && (
                <Label x={536} y={238} small value anchor="start">
                  = {output}
                </Label>
              )}
            </>
          )}
        </>
      ) : null}
      {highlight === "junctions" && (
        <g className="fpga-map-switchboxes">
          {channels.flatMap((y) =>
            channels.map((x) => (
              <rect
                key={`${x}-${y}`}
                x={x - 12}
                y={y - 12}
                width={24}
                height={24}
                rx={3}
              />
            )),
          )}
        </g>
      )}
      <ResourceColumnLogic visible={columns} />
      {positions.map((y, row) =>
        positions.map((x, column) => {
          const number = row * 3 + column + 1;
          const [top, bottom] = blockVerticalInsets?.[number] ?? [0, 0];
          const selected =
            selectedBlocks
              ? selectedBlocks.includes(number)
              : highlight
                ? highlight === "logic"
                : routing
                  ? number === source || number === 5
                  : number === 1;

          return miniature ? (
            <rect
              key={number}
              x={x}
              y={y + top}
              width={72 - top - bottom}
              height={(columns ? 36 : 72) - top - bottom}
              rx={4}
              className={`fpga-map-tile ${selected && !routing ? "is-selected" : ""}`}
            />
          ) : (
            <LogicMapBlock
              key={number}
              x={x}
              y={y + top}
              h={(columns ? 36 : 72) - top - bottom}
              detail={
                !highlight
                  ? routing
                    ? String(number)
                    : number === 1
                      ? rule
                      : undefined
                  : blockDetails?.[number]
              }
              active={selected}
            />
          );
        }),
      )}
      <g className="fpga-map-pins">
        {channels.map((position, index) => {
          const dx = columns ? 220 + index * 300 - position : 0;
          const dy = columns ? -40 + index * 320 - position : 0;

          return (
            <g key={position}>
              <path
                d={`M32 ${position}H60`}
                className={`fpga-map-edge-pin ${showCircuitPins && (position === 100 || position === 220) ? "is-selected" : ""}`}
                style={{ transform: `translateY(${dy}px)` }}
              />
              <path
                d={`M${position} 32V60`}
                className="fpga-map-edge-pin"
                style={{
                  transform: `translate(${dx}px, ${columns ? -240 : 0}px)`,
                }}
              />
              <path
                d={`M${position} 500V528`}
                className="fpga-map-edge-pin"
                style={{
                  transform: `translate(${dx}px, ${columns ? 600 : 0}px)`,
                }}
              />
              <path
                d={`M500 ${position}H528`}
                className={`fpga-map-right-pins${showCircuitPins && position === 220 ? " is-selected" : ""}`}
                style={{ transform: `translate(${extension}px, ${dy}px)` }}
              />
            </g>
          );
        })}
      </g>
      {showCircuitPins && (
        <g className="fpga-map-directions">
          <path d="M516 216L520 220L516 224" />
        </g>
      )}
      <g className="fpga-map-ports">
        {channels.map((position, index) => {
          const dx = columns ? 220 + index * 300 - position : 0;
          const dy = columns ? -40 + index * 320 - position : 0;

          return (
            <g key={position}>
              <g
                className="fpga-map-edge-ports"
                style={{ transform: `translateY(${dy}px)` }}
              >
                <rect
                  x={60}
                  y={position - 12}
                  width={24}
                  height={24}
                  rx={2}
                  className={
                    showCircuitPins && (position === 100 || position === 220)
                      ? "is-selected"
                      : undefined
                  }
                />
                {!miniature && (
                  <Label x={72} y={position + 5}>
                    I/O
                  </Label>
                )}
              </g>
              <g
                className="fpga-map-right-ports"
                style={{ transform: `translate(${extension}px, ${dy}px)` }}
              >
                <rect
                  x={476}
                  y={position - 12}
                  width={24}
                  height={24}
                  rx={2}
                  className={
                    showCircuitPins && position === 220
                      ? "is-selected"
                      : undefined
                  }
                />
                {!miniature && (
                  <Label x={488} y={position + 5}>
                    I/O
                  </Label>
                )}
              </g>
              <g
                className="fpga-map-edge-ports"
                style={{
                  transform: `translate(${dx}px, ${columns ? -240 : 0}px)`,
                }}
              >
                <rect x={position - 12} y={60} width={24} height={24} rx={2} />
                {!miniature && (
                  <Label x={position} y={77}>
                    I/O
                  </Label>
                )}
              </g>
              <g
                className="fpga-map-edge-ports"
                style={{
                  transform: `translate(${dx}px, ${columns ? 600 : 0}px)`,
                }}
              >
                <rect x={position - 12} y={476} width={24} height={24} rx={2} />
                {!miniature && (
                  <Label x={position} y={493}>
                    I/O
                  </Label>
                )}
              </g>
            </g>
          );
        })}
      </g>
      {routing && (
        <rect
          x={202}
          y={202}
          width={36}
          height={36}
          rx={5}
          className="fpga-map-focus"
        />
      )}
    </g>
  );
};

export const ChipContext = ({
  children,
  part,
  enabled = true,
}: {
  children: ReactNode;
  part: "lut" | "block" | "junction";
  enabled?: boolean;
}) => {
  if (!enabled) return children;

  const focus = part === "junction" ? "junction" : "block";
  const location =
    part === "lut"
      ? "Whole FPGA › Highlighted CLB › LUT"
      : part === "block"
        ? "Whole FPGA › Highlighted CLB"
        : "Whole FPGA › Routing junction";

  return (
    <div className="fpga-chip-context">
      <div className="fpga-map-location">
        <svg
          viewBox={chipMapViewBox}
          aria-hidden="true"
          className="fpga-map-locator"
        >
          <ChipMap focus={focus} miniature />
        </svg>
        <span>{location}</span>
      </div>
      {children}
    </div>
  );
};
