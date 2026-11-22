import { useContext, useEffect, useId, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { createPortal } from "react-dom";
import { FigureSlot } from "./FigureSlot";

export const Label = ({
  x,
  y,
  children,
  small = false,
  value = false,
  anchor = "middle",
  className = "",
}: {
  x: number;
  y: number;
  children: ReactNode;
  small?: boolean;
  value?: boolean;
  anchor?: "middle" | "start" | "end";
  className?: string;
}) => (
  <text
    x={x}
    y={y}
    textAnchor={anchor}
    className={`${small ? "fpga-small" : ""} ${value ? "fpga-value" : ""} ${className}`}
  >
    {children}
  </text>
);

export const Wire = ({
  d,
  active = false,
  faint = false,
  control = false,
  bus,
}: {
  d: string;
  active?: boolean;
  faint?: boolean;
  control?: boolean;
  bus?: { x: number; y: number; width?: number };
}) => (
  <g className={faint ? "fpga-faint" : undefined}>
    <path d={d} className={`fpga-wire ${control ? "fpga-config-wire" : ""}`} />
    {active && (
      <path
        d={d}
        className={`fpga-signal ${control ? "fpga-config-signal" : ""}`}
        pathLength={1}
      />
    )}
    {bus && (
      <g className="fpga-bus">
        <path d={`M${bus.x - 4} ${bus.y + 7}l8 -14`} />
        {bus.width !== undefined && (
          <Label x={bus.x + 10} y={bus.y - 9} small value>
            {bus.width}
          </Label>
        )}
      </g>
    )}
  </g>
);

export const SramFeedback = () => (
  <g className="fpga-tour-sram-symbol">
    <Wire d="M22 -22H48V22H20M-22 22H-48V-22H-20" />
    <path
      d="M-20 -38L12 -22L-20 -6Z M20 6L-12 22L20 38Z"
      className="fpga-gate"
    />
    <circle cx={17} cy={-22} r={5} className="fpga-gate" />
    <circle cx={-17} cy={22} r={5} className="fpga-gate" />
  </g>
);

export const Transfer = ({ d, trigger }: { d: string; trigger: number }) =>
  trigger > 0 ? (
    <circle
      key={trigger}
      r={4}
      className="fpga-data-transfer"
      style={{ offsetPath: `path("${d}")` } as CSSProperties}
    />
  ) : null;

export const Block = ({
  x,
  y,
  w = 100,
  h = 65,
  label,
  detail,
  active = false,
  kind = "logic",
}: {
  x: number;
  y: number;
  w?: number;
  h?: number;
  label: string;
  detail?: ReactNode;
  active?: boolean;
  kind?: "logic" | "storage" | "config" | "memory" | "arithmetic";
}) => (
  <g
    className={`fpga-block fpga-block--${kind} ${active ? "is-selected" : ""}`}
  >
    <rect x={x} y={y} width={w} height={h} rx={4} />
    <Label
      x={x + w / 2}
      y={y + (detail !== undefined ? (h < 60 ? 20 : h / 2 - 8) : h / 2 + 6)}
      value={/^(?:[−-]?\d+(?:\.\d+)?|—)$/.test(label)}
    >
      {label}
    </Label>
    {detail !== undefined && (
      <Label
        x={x + w / 2}
        y={y + (h < 60 ? h - 7 : h / 2 + 22)}
        small
        value={
          typeof detail === "number" ||
          (typeof detail === "string" && !/[a-z]/i.test(detail))
        }
      >
        {detail}
      </Label>
    )}
  </g>
);

export const Mux = ({
  x,
  y,
  selection,
  name,
  showSelectionLabel = true,
}: {
  x: number;
  y: number;
  selection: number;
  name: string;
  showSelectionLabel?: boolean;
}) => (
  <g className="fpga-mux">
    <path d={`M${x} ${y - 30}l32 12v36l-32 12z`} />
    <Label x={x + 16} y={y + 5} small>
      MUX
    </Label>
    <Wire d={`M${x + 16} ${y + 24}v23`} control />
    {showSelectionLabel && (
      <Label x={x + 16} y={y + 66} small value>
        {name} = {selection}
      </Label>
    )}
  </g>
);

export const FlipFlop = ({
  x,
  y,
  value,
  label = "Flip-flop",
  width = 1,
  capture = 0,
  captionInside = false,
  showTerminals = false,
}: {
  x: number;
  y: number;
  value: ReactNode;
  label?: string;
  width?: number;
  capture?: number;
  captionInside?: boolean;
  showTerminals?: boolean;
}) => (
  <g className="fpga-flip-flop">
    <Block
      x={x}
      y={y}
      w={105}
      h={85}
      label={captionInside ? `${label} · ${width} bits` : label}
      detail={value}
      kind="storage"
    />
    {showTerminals && (
      <>
        <Label x={x + 10} y={y + 19} small value anchor="start">
          D
        </Label>
        <Label x={x + 95} y={y + 19} small value anchor="end">
          Q
        </Label>
      </>
    )}
    <path d={`M${x + 41} ${y + 85}l11 -10 11 10`} className="fpga-wire" />
    {capture > 0 && (
      <rect
        key={capture}
        x={x - 3}
        y={y - 3}
        width={111}
        height={91}
        rx={6}
        className="fpga-captured"
      />
    )}
    {width > 1 && !captionInside && (
      <Label x={x + 52} y={y - 14} small>
        {width}-bit register
      </Label>
    )}
  </g>
);

export const Figure = ({
  children,
  title,
  viewBox = "0 0 560 370",
  compact,
}: {
  children: ReactNode;
  title: string;
  viewBox?: string;
  compact?: { viewBox: string; children: ReactNode };
}) => {
  const id = useId();
  const slot = useContext(FigureSlot);
  const viewport = useRef<HTMLDivElement>(null);
  const [scrollable, setScrollable] = useState(false);

  useEffect(() => {
    const element = viewport.current;
    if (!element) return;

    const update = () =>
      setScrollable(
        element.scrollHeight > element.clientHeight + 1 ||
          element.scrollWidth > element.clientWidth + 1,
      );
    const resize = new ResizeObserver(update);
    resize.observe(element);
    for (const child of element.children) resize.observe(child);
    update();

    return () => resize.disconnect();
  }, []);

  if (slot) {
    if (!slot.target) return null;

    return createPortal(
      <g className="fpga-chip-detail" role="img" aria-labelledby={id}>
        <title id={id}>{title}</title>
        <rect width={560} height={400} rx={8} className="fpga-tour-boundary" />
        <svg
          x={10}
          y={10}
          width={540}
          height={380}
          viewBox={viewBox}
          className={compact ? "fpga-chip-detail-wide" : undefined}
        >
          {children}
        </svg>
        {compact && (
          <svg
            x={10}
            y={10}
            width={540}
            height={380}
            viewBox={compact.viewBox}
            className="fpga-chip-detail-compact"
          >
            {compact.children}
          </svg>
        )}
      </g>,
      slot.target,
    );
  }

  return (
    <div className="fpga-diagram">
      <div
        ref={viewport}
        className="fpga-diagram-viewport"
        tabIndex={scrollable ? 0 : undefined}
        role={scrollable ? "region" : undefined}
        aria-label={scrollable ? "Scrollable diagram" : undefined}
        aria-describedby={scrollable ? `${id}-scroll` : undefined}
      >
        <svg
          className={`fpga-drawing ${compact ? "fpga-drawing--wide" : ""}`}
          viewBox={viewBox}
          role="img"
          aria-labelledby={id}
        >
          <title id={id}>{title}</title>
          {children}
        </svg>
        {compact && (
          <svg
            className="fpga-drawing fpga-drawing--compact"
            viewBox={compact.viewBox}
            role="img"
            aria-labelledby={`${id}-compact`}
          >
            <title id={`${id}-compact`}>{title}</title>
            {compact.children}
          </svg>
        )}
      </div>
      {scrollable && (
        <p className="fpga-diagram-hint" id={`${id}-scroll`}>
          Scroll diagram to inspect
        </p>
      )}
    </div>
  );
};

export const BitControls = ({
  name,
  value,
  onChange,
  disabled = false,
}: {
  name: string;
  value: number;
  onChange: () => void;
  disabled?: boolean;
}) => (
  <button
    type="button"
    className="fpga-bit-control"
    disabled={disabled}
    onClick={onChange}
    aria-label={`Toggle ${name}, currently ${value}`}
  >
    <span>{name}</span>
    <code>{value}</code>
  </button>
);

export const ClockControls = ({
  capture,
  reset,
  running,
  setRunning,
  reduced = false,
  disabled = false,
}: {
  capture: () => void;
  reset: () => void;
  running?: boolean;
  setRunning?: (value: boolean) => void;
  reduced?: boolean;
  disabled?: boolean;
}) => (
  <div className="fpga-controls">
    <button type="button" onClick={capture} disabled={disabled || running}>
      Clock edge
    </button>
    {setRunning && !reduced && (
      <button
        type="button"
        onClick={() => setRunning(!running)}
        disabled={disabled}
      >
        {running ? "Pause clock" : "Run clock"}
      </button>
    )}
    <button type="button" onClick={reset}>
      Reset example
    </button>
  </div>
);

export const ClockLine = ({
  x,
  y,
  edge,
}: {
  x: number;
  y: number;
  edge: number;
}) => (
  <g>
    <Wire d={`M${x} ${y + 45}V${y}`} />
    <Label x={x} y={y + 68} small>
      Clock
    </Label>
    {edge > 0 && (
      <path
        key={edge}
        d={`M${x} ${y + 45}V${y}`}
        className="fpga-clock-pulse"
      />
    )}
  </g>
);
