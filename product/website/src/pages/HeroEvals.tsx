import type { CSSProperties, ReactElement } from "react";

/* The hero's two eval cards, drawn from the designs in
   homepage-imgs/agr-eval-score.png and eval-viz-1.png (both 4x). Each is one
   SVG whose viewBox is the card in design px, so its type and marks scale
   with the rest of the desk; the animation is CSS, in home-lab.css, and
   plays once on load. Illustrative figures for a model being trained, not
   measurements. */

/* -- Aggregate eval score: a line over twelve versions ------------------- */

const SCORES = [63, 68, 74, 75, 80, 84, 85, 88, 74, 89, 94, 96];
const REGRESSION = 8; /* v9 */

const CHART = { bottom: 135.25, left: 42.75, right: 303, top: 55 };
const pointX = (i: number) => 45.75 + i * 23.09;
const pointY = (score: number) =>
  CHART.top + ((100 - score) / 60) * (CHART.bottom - CHART.top);

const linePath = SCORES.map(
  (score, i) =>
    `${i ? "L" : "M"}${pointX(i).toFixed(2)} ${pointY(score).toFixed(2)}`,
).join(" ");

const areaPath = `${linePath} L${pointX(SCORES.length - 1).toFixed(2)} ${
  CHART.bottom
} L${pointX(0).toFixed(2)} ${CHART.bottom} Z`;

export const EvalChart = (): ReactElement => (
  <svg
    aria-hidden="true"
    className="gr-lab-chart-svg"
    viewBox="0 0 326.7 173.8"
  >
    <defs>
      <linearGradient id="gr-lab-chart-fill" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stopColor="#8fdcae" stopOpacity="0.2" />
        <stop offset="1" stopColor="#8fdcae" stopOpacity="0" />
      </linearGradient>
    </defs>

    <text className="gr-lab-chart-title" x="17.25" y="22.5">
      Aggregate eval score
    </text>
    <text className="gr-lab-chart-figure" x="17.25" y="37.5">
      96%
    </text>
    <text className="gr-lab-chart-delta" x="44.5" y="37">
      ↗ 33 pts
    </text>
    <text
      className="gr-lab-chart-label gr-lab-chart-muted"
      textAnchor="end"
      x="311"
      y="31.25"
    >
      12 versions
    </text>

    {[100, 80, 60, 40].map((tick) => (
      <g key={tick}>
        <line
          className="gr-lab-chart-grid"
          x1={CHART.left}
          x2={CHART.right}
          y1={pointY(tick)}
          y2={pointY(tick)}
        />
        <text
          className="gr-lab-chart-axis"
          textAnchor="end"
          x="37.5"
          y={pointY(tick) + 2.2}
        >
          {tick}%
        </text>
      </g>
    ))}

    {SCORES.map((_, i) => (
      <text
        className="gr-lab-chart-axis"
        key={i}
        textAnchor="middle"
        x={pointX(i)}
        y="151.5"
      >
        v{i + 1}
      </text>
    ))}

    <path className="gr-lab-chart-area" d={areaPath} />
    <path className="gr-lab-chart-line" d={linePath} pathLength={1} />

    {SCORES.map((score, i) =>
      i === REGRESSION ? null : (
        <circle
          className="gr-lab-chart-dot"
          cx={pointX(i)}
          cy={pointY(score)}
          key={i}
          r="1.9"
          style={{ "--n": i } as CSSProperties}
        />
      ),
    )}

    <g
      className="gr-lab-chart-regression"
      style={{ "--n": REGRESSION } as CSSProperties}
    >
      <circle
        className="gr-lab-chart-ring"
        cx={pointX(REGRESSION)}
        cy={pointY(SCORES[REGRESSION])}
        r="7.6"
      />
      <circle
        className="gr-lab-chart-flag"
        cx={pointX(REGRESSION)}
        cy={pointY(SCORES[REGRESSION])}
        r="2.6"
      />
      <text
        className="gr-lab-chart-flag-label"
        textAnchor="middle"
        x={pointX(REGRESSION)}
        y="108"
      >
        Regression
      </text>
    </g>
  </svg>
);

/* -- Evaluation performance: eight criteria by twelve versions ----------- */

/* 0 failing to 5 strongest: the design's six fills. */
const LEVELS = [
  "#e49e93",
  "#eec5a6",
  "#e8e6c8",
  "#c5e3d1",
  "#8bc6a3",
  "#4f9670",
];

const CRITERIA: [string, number[]][] = [
  ["Correctness", [1, 2, 2, 2, 3, 3, 3, 3, 1, 4, 4, 5]],
  ["Reasoning", [0, 1, 1, 2, 1, 3, 3, 4, 1, 3, 4, 4]],
  ["Faithfulness", [2, 3, 3, 4, 3, 4, 4, 4, 4, 4, 5, 5]],
  ["Tool selection", [0, 0, 1, 1, 2, 3, 3, 3, 0, 3, 4, 4]],
  ["Instruction", [3, 3, 4, 3, 4, 4, 4, 4, 4, 4, 5, 5]],
  ["Completeness", [1, 1, 2, 3, 3, 3, 3, 4, 3, 4, 4, 4]],
  ["Safety", [4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5]],
  ["Consistency", [0, 0, 2, 1, 3, 3, 2, 3, 1, 3, 4, 5]],
];

/* One pitch both ways, so the gutter between cells is the same 3px
   horizontally and vertically. */
const CELL = 12.5;
const PITCH = CELL + 3;
const colX = (c: number) => 80.25 + c * PITCH;
const rowY = (r: number) => 64 + r * PITCH;

export const EvalHeatmap = (): ReactElement => (
  <svg
    aria-hidden="true"
    className="gr-lab-heatmap-svg"
    viewBox="0 0 278.3 211.2"
  >
    <text className="gr-lab-heatmap-title" x="21.25" y="24">
      Evaluation performance
    </text>
    <text className="gr-lab-heatmap-sub" x="21.25" y="33.75">
      8 evaluation criteria · 12 model versions
    </text>

    {CRITERIA[0][1].map((_, c) => (
      <text
        className={`gr-lab-heatmap-col${c === 11 ? " gr-lab-heatmap-col--now" : ""}`}
        key={c}
        textAnchor="middle"
        x={colX(c)}
        y="51.25"
      >
        {String(c + 1).padStart(2, "0")}
      </text>
    ))}

    {CRITERIA.map(([name, scores], r) => (
      <g key={name}>
        <text className="gr-lab-heatmap-row" x="21.25" y={rowY(r) + 2.3}>
          {name}
        </text>
        {scores.map((level, c) => (
          <rect
            className="gr-lab-heatmap-cell"
            fill={LEVELS[level]}
            height={CELL}
            key={c}
            style={{ "--c": c, "--r": r } as CSSProperties}
            width={CELL}
            x={colX(c) - CELL / 2}
            y={rowY(r) - CELL / 2}
          />
        ))}
      </g>
    ))}

    {/* v9, the regression the chart flags. */}
    <rect
      className="gr-lab-heatmap-flag"
      height="128.25"
      pathLength={1}
      rx="2.5"
      width="16.5"
      x="196"
      y="53.25"
    />
  </svg>
);
