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
 * The drawing sits INSET in its box the way the photographs did (they
 * carried transparent margins), so the object reads at the same size the
 * photo version did. Flat diagram: no drop shadows — occlusion alone says
 * which layer is on top (the --raw modifier strips the photo shadows).
 */

/** The real mark, on its own 31.75-unit square viewBox (see Logo.tsx). */
const MARK_PATH =
  "M31.7539 31.7539H0V0H31.7539V31.7539ZM6.70605 11.8359V20.9824H12.2314V25.4375H18.332L25.0469 18.7227V14.9004L20.8887 14.8945L16.1523 19.9023H12.2314V11.8359H25.0469V6.31445H12.2314L6.70605 11.8359Z";

const S = 686; /* the layers' shared square, matching the old exports' box */
/* the layer plate, centred in that box */
const P0 = 78;
const PW = 530;
const P1 = P0 + PW;

const line = {
  fill: "none",
  stroke: "currentColor",
  strokeOpacity: 0.3,
  strokeWidth: 1,
  vectorEffect: "non-scaling-stroke",
} as const;

/* a plate occludes whatever sits beneath it — the splay reads as bands of
   each layer — so its ground is the page's own colour, hairline on top */
const plate = {
  fill: "var(--color-substrate)",
  stroke: "currentColor",
  strokeOpacity: 0.3,
  strokeWidth: 1,
  vectorEffect: "non-scaling-stroke",
} as const;

const range = (n: number): number[] => Array.from({ length: n }, (_, i) => i);

const Plate = (): ReactElement => (
  <rect {...plate} height={PW} rx={14} width={PW} x={P0} y={P0} />
);

/** BGA array: the underside, a field of ball outlines. */
const SolderBalls = (): ReactElement => (
  <g>
    <Plate />
    {range(10).map((r) =>
      range(10).map((c) => (
        <circle
          {...line}
          cx={P0 + 42 + c * 50}
          cy={P0 + 42 + r * 50}
          key={`${r}-${c}`}
          r={11}
        />
      )),
    )}
  </g>
);

/** Substrate: perimeter pads and an inner cavity. */
const Substrate = (): ReactElement => (
  <g>
    <Plate />
    {range(12).map((i) => (
      <g key={i}>
        <rect fill="currentColor" fillOpacity={0.3} height={6} width={14} x={P0 + 38 + i * 40} y={P0 + 16} />
        <rect fill="currentColor" fillOpacity={0.3} height={6} width={14} x={P0 + 38 + i * 40} y={P1 - 22} />
        <rect fill="currentColor" fillOpacity={0.3} height={14} width={6} x={P0 + 16} y={P0 + 38 + i * 40} />
        <rect fill="currentColor" fillOpacity={0.3} height={14} width={6} x={P1 - 22} y={P0 + 38 + i * 40} />
      </g>
    ))}
    <rect {...line} height={210} rx={6} width={210} x={P0 + 160} y={P0 + 160} />
    {range(4).map((i) => (
      <g key={i}>
        <path {...line} d={`M${P0 + 176 + i * 18} ${P0 + 160} L${P0 + 140 + i * 22} ${P0 + 92 - i * 12} L${P0 + 44} ${P0 + 92 - i * 12}`} />
        <path {...line} d={`M${P1 - 176 - i * 18} ${P1 - 160} L${P1 - 140 - i * 22} ${P1 - 92 + i * 12} L${P1 - 44} ${P1 - 92 + i * 12}`} />
      </g>
    ))}
  </g>
);

/** The die: a dense matrix of data bits. */
const SiliconDie = (): ReactElement => (
  <g>
    <Plate />
    {/* bits run to the plate's edges so the exposed band below the stack
        shows the die's texture, not blank plate */}
    {range(18).map((r) =>
      range(18).map((c) =>
        (r * 7 + c * 13) % 5 === 0 ? null : (
          <rect
            fill="currentColor"
            fillOpacity={0.55}
            height={6}
            key={`${r}-${c}`}
            width={6}
            x={P0 + 26 + c * 28}
            y={P0 + 26 + r * 28}
          />
        ),
      ),
    )}
  </g>
);

/** Metal layer: the routing grid. */
const MetalLayer = (): ReactElement => (
  <g>
    <Plate />
    {range(12).map((i) => (
      <g key={i}>
        <line {...line} x1={P0 + 24 + i * 44} x2={P0 + 24 + i * 44} y1={P0 + 24} y2={P1 - 24} />
        <line {...line} x1={P0 + 24} x2={P1 - 24} y1={P0 + 24 + i * 44} y2={P0 + 24 + i * 44} />
      </g>
    ))}
  </g>
);

/** Underfill: a sparse 45-degree hatch, clipped to the plate. */
const Underfill = (): ReactElement => (
  <g>
    <clipPath id="gr-underfill-clip">
      <rect height={PW - 8} rx={12} width={PW - 8} x={P0 + 4} y={P0 + 4} />
    </clipPath>
    <Plate />
    <g clipPath="url(#gr-underfill-clip)">
      {range(16).map((i) => (
        <line
          {...line}
          key={i}
          x1={P0 - PW + i * 66}
          x2={P0 + i * 66}
          y1={P0 + PW}
          y2={P0}
        />
      ))}
    </g>
  </g>
);

/** The lid: plate, die perimeter, corner screws, the G. */
const Casing = (): ReactElement => {
  /* the casing plate, centred in the old photo's 900x887 box */
  const CW = 560;
  const cx0 = (900 - CW) / 2;
  const cy0 = (887 - CW) / 2;
  return (
    <svg
      aria-label="A Gradiated inference package, drawn as a blueprint."
      className="gr-chipstack-casing"
      height={887}
      role="img"
      style={{ maxWidth: "100%", height: "auto", color: "var(--color-text)" }}
      viewBox="0 0 900 887"
      width={900}
    >
      <rect {...plate} height={CW} rx={56} width={CW} x={cx0} y={cy0} />
      <rect {...line} height={CW - 128} rx={16} width={CW - 128} x={cx0 + 64} y={cy0 + 64} />
      {[
        [cx0 + 88, cy0 + 88],
        [cx0 + CW - 88, cy0 + 88],
        [cx0 + 88, cy0 + CW - 88],
        [cx0 + CW - 88, cy0 + CW - 88],
      ].map(([sx, sy]) => (
        <g key={`${sx}-${sy}`}>
          <circle {...line} cx={sx} cy={sy} r={9} />
          <circle {...line} cx={sx} cy={sy} r={3.2} />
        </g>
      ))}
      <g transform={`translate(${450 - 60} ${443.5 - 60}) scale(${120 / 31.7539})`}>
        <path d={MARK_PATH} fill="none" stroke="currentColor" strokeOpacity={0.3} strokeWidth={1} vectorEffect="non-scaling-stroke" />
      </g>
    </svg>
  );
};

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
    <div
      className={`gr-chipstack gr-chipstack--raw${open ? " gr-chipstack--open" : ""}`}
    >
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
