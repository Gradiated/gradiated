import { useEffect, useState } from "react";
import type { CSSProperties, ReactElement } from "react";

/**
 * The chip stack, in the homepage's raw ink language.
 *
 * Same object and same choreography as ChipStack — a package whose layers
 * drop straight down out of it — but drawn instead of photographed: every
 * layer is an inline-SVG technical drawing on the one 30% hairline, so the
 * hardware page speaks the same pen as the chip fold's blueprint. Inline,
 * not files, so the ink follows the theme through currentColor.
 *
 * The splay is untouched: these render under the same gr-chipstack classes
 * the photographic version used, and the CSS owns the motion.
 */

/** The real mark, on its own 31.75-unit square viewBox (see Logo.tsx). */
const MARK_PATH =
  "M31.7539 31.7539H0V0H31.7539V31.7539ZM6.70605 11.8359V20.9824H12.2314V25.4375H18.332L25.0469 18.7227V14.9004L20.8887 14.8945L16.1523 19.9023H12.2314V11.8359H25.0469V6.31445H12.2314L6.70605 11.8359Z";

const S = 686; /* the layers' shared square, matching the exports' box */

/* one pen for every line */
const line = {
  fill: "none",
  stroke: "currentColor",
  strokeOpacity: 0.3,
  strokeWidth: 1,
  vectorEffect: "non-scaling-stroke",
} as const;

/* a plate occludes whatever sits beneath it — the splay reads as bands of
   each layer, exactly as the photographic stack did — so its ground is the
   page's own colour with the hairline on top */
const plate = {
  fill: "var(--color-substrate)",
  stroke: "currentColor",
  strokeOpacity: 0.3,
  strokeWidth: 1,
  vectorEffect: "non-scaling-stroke",
} as const;

const range = (n: number): number[] => Array.from({ length: n }, (_, i) => i);

/** BGA array: the underside, a field of ball outlines. */
const SolderBalls = (): ReactElement => (
  <g>
    <rect {...plate} height={S - 12} rx={18} width={S - 12} x={6} y={6} />
    {range(12).map((r) =>
      range(12).map((c) => (
        <circle
          {...line}
          cx={73 + c * 49}
          cy={73 + r * 49}
          key={`${r}-${c}`}
          r={13}
        />
      )),
    )}
  </g>
);

/** Substrate: perimeter pads and a few escape routes. */
const Substrate = (): ReactElement => (
  <g>
    <rect {...plate} height={S - 12} rx={18} width={S - 12} x={6} y={6} />
    {range(16).map((i) => (
      <g key={i}>
        <rect fill="currentColor" fillOpacity={0.3} height={8} width={18} x={48 + i * 38} y={30} />
        <rect fill="currentColor" fillOpacity={0.3} height={8} width={18} x={48 + i * 38} y={S - 38} />
        <rect fill="currentColor" fillOpacity={0.3} height={18} width={8} x={30} y={48 + i * 38} />
        <rect fill="currentColor" fillOpacity={0.3} height={18} width={8} x={S - 38} y={48 + i * 38} />
      </g>
    ))}
    <rect {...line} height={306} rx={8} width={306} x={190} y={190} />
    {/* escape routing: four corner fans */}
    {range(5).map((i) => (
      <g key={i}>
        <path {...line} d={`M${206 + i * 20} 190 L${160 + i * 26} ${120 - i * 14} L60 ${120 - i * 14}`} />
        <path {...line} d={`M${480 - i * 20} ${S - 190} L${526 - i * 26} ${S - 120 + i * 14} L${S - 60} ${S - 120 + i * 14}`} />
      </g>
    ))}
  </g>
);

/** The die: a dense matrix of data bits. */
const SiliconDie = (): ReactElement => (
  <g>
    <rect {...plate} height={S - 12} rx={18} width={S - 12} x={6} y={6} />
    <rect {...line} height={430} rx={6} width={430} x={128} y={128} />
    {range(14).map((r) =>
      range(14).map((c) =>
        (r * 7 + c * 13) % 5 === 0 ? null : (
          <rect
            fill="currentColor"
            fillOpacity={0.55}
            height={7}
            key={`${r}-${c}`}
            width={7}
            x={152 + c * 28}
            y={152 + r * 28}
          />
        ),
      ),
    )}
  </g>
);

/** Metal layer: the routing grid. */
const MetalLayer = (): ReactElement => (
  <g>
    <rect {...plate} height={S - 12} rx={18} width={S - 12} x={6} y={6} />
    {range(15).map((i) => (
      <g key={i}>
        <line {...line} x1={44 + i * 43} x2={44 + i * 43} y1={44} y2={S - 44} />
        <line {...line} x1={44} x2={S - 44} y1={44 + i * 43} y2={44 + i * 43} />
      </g>
    ))}
  </g>
);

/** Underfill: a sparse 45-degree hatch. */
const Underfill = (): ReactElement => (
  <g>
    <rect {...plate} height={S - 12} rx={18} width={S - 12} x={6} y={6} />
    {range(16).map((i) => (
      <line
        {...line}
        key={i}
        x1={Math.max(20, i * 84 - S + 40)}
        x2={Math.min(S - 20, 40 + i * 84)}
        y1={Math.min(S - 20, 40 + i * 84)}
        y2={Math.max(20, i * 84 - S + 40)}
      />
    ))}
  </g>
);

/** The lid: plate, die perimeter, corner screws, the G. */
const Casing = (): ReactElement => (
  <svg
    aria-label="A Gradiated inference package, drawn as a blueprint."
    className="gr-chipstack-casing"
    height={887}
    role="img"
    style={{ maxWidth: "100%", height: "auto", color: "var(--color-text)" }}
    viewBox="0 0 900 887"
    width={900}
  >
    <rect {...plate} height={863} rx={96} width={876} x={12} y={12} />
    <rect {...line} height={663} rx={24} width={676} x={112} y={112} />
    {[
      [146, 146],
      [754, 146],
      [146, 741],
      [754, 741],
    ].map(([cx, cy]) => (
      <g key={`${cx}-${cy}`}>
        <circle {...line} cx={cx} cy={cy} r={11} />
        <circle {...line} cx={cx} cy={cy} r={4} />
      </g>
    ))}
    <g transform={`translate(${450 - 80} ${443.5 - 80}) scale(${160 / 31.7539})`}>
      <path d={MARK_PATH} fill="none" stroke="currentColor" strokeOpacity={0.3} strokeWidth={1} vectorEffect="non-scaling-stroke" />
    </g>
  </svg>
);

const LAYERS = [
  { Art: SolderBalls, name: "solder-balls" },
  { Art: Substrate, name: "substrate" },
  { Art: SiliconDie, name: "silicon-die" },
  { Art: MetalLayer, name: "metal-layer" },
  { Art: Underfill, name: "underfill" },
] as const;

export const ChipStackRaw = (): ReactElement => {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setOpen(true);
      return;
    }
    const frame = requestAnimationFrame(() => setOpen(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <div className={`gr-chipstack${open ? " gr-chipstack--open" : ""}`}>
      <div className="gr-chipstack-frame">
        <Casing />
        {LAYERS.map((layer, index) => (
          <svg
            aria-hidden
            className="gr-chipstack-layer"
            height={S}
            key={layer.name}
            style={
              {
                "--layer": LAYERS.length - index,
                color: "var(--color-text)",
              } as CSSProperties
            }
            viewBox={`0 0 ${S} ${S}`}
            width={S}
          >
            <layer.Art />
          </svg>
        ))}
      </div>
    </div>
  );
};
