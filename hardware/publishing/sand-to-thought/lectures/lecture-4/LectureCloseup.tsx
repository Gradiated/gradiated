import { useId, type CSSProperties } from "react";

function Box({
  x,
  y,
  w,
  label,
}: {
  x: number;
  y: number;
  w: number;
  label: string;
}) {
  return (
    <g>
      <rect x={x} y={y - 12} width={w} height="24" rx="4" />
      <text x={x + w / 2} y={y}>
        {label}
      </text>
    </g>
  );
}

export function Multipliers({ shared }: { shared: boolean }) {
  const arrow = useId();
  const rows = [38, 92, 146];
  return (
    <svg
      className="lecture-detail"
      viewBox="0 0 400 184"
      role="img"
      aria-label={
        shared
          ? "Three normalisation stages take turns using one multiplier."
          : "Each normalisation stage has its own multiplier. Only one is busy at a time."
      }
    >
      <Arrow id={arrow} />
      {rows.map((y, i) => (
        <g
          key={y}
          className="norm-turn"
          style={{ "--offset": `${((3 - i) % 3) * -1.5}s` } as CSSProperties}
        >
          <Box
            x={16}
            y={y}
            w={135}
            label={
              ["First normalise", "Second normalise", "Final normalise"][i]
            }
          />
          <path
            className="detail-wire"
            d={shared ? `M151 ${y}H202V92H257` : `M151 ${y}H257`}
            markerEnd={`url(#${arrow})`}
          />
          {!shared && <Box x={259} y={y} w={125} label="Multiplier" />}
        </g>
      ))}
      {shared && (
        <g className="detail-active">
          <Box x={259} y={92} w={125} label="Multiplier" />
        </g>
      )}
    </svg>
  );
}

function Arrow({ id }: { id: string }) {
  return (
    <defs>
      <marker
        id={id}
        viewBox="0 0 8 8"
        refX="7.5"
        refY="4"
        markerWidth="4"
        markerHeight="4"
        orient="auto"
      >
        <path d="M0 0L8 4 0 8Z" fill="var(--lecture-signal)" />
      </marker>
    </defs>
  );
}

export function ScoringRows({ count }: { count: number }) {
  const arrow = useId();
  const last = 45 + (count - 1) * 35;
  const mid = (45 + last) / 2;
  return (
    <svg
      className="lecture-detail"
      viewBox={`0 0 400 ${last + 23}`}
      role="img"
      aria-label={`One input feeds ${count} multipliers. Each lane reads its own weight and accumulates a different score on the same tick.`}
    >
      <Arrow id={arrow} />
      <text x="170" y="16">
        Weight bank
      </text>
      <text x="245" y="16">
        Multiply
      </text>
      <text x="346" y="16">
        Add to total
      </text>
      <Box x={2} y={mid} w={81} label="Same input" />
      <path className="detail-wire" d={`M83 ${mid}H104 M104 29V${last - 16}`} />
      {Array.from({ length: count }, (_, i) => {
        const y = 45 + i * 35;
        return (
          <g key={i}>
            <path
              className="detail-wire"
              d={`M104 ${y - 16}H245v4 M192 ${y}H231 M259 ${y}H292`}
              markerEnd={`url(#${arrow})`}
            />
            <Box x={145} y={y} w={47} label={String(i + 1)} />
            <circle cx={245} cy={y} r={12} />
            <text x={245} y={y}>
              ×
            </text>
            <g className="lane-total">
              <Box x={294} y={y} w={102} label={`Score ${i + 1}`} />
            </g>
          </g>
        );
      })}
    </svg>
  );
}
