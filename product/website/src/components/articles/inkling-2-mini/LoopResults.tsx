import type { CSSProperties, ReactElement } from "react";
import "./article.css";
import "./loop-results.css";

// Every score: TML-d24-varloop-research model card, "5. Evaluations"
// (huggingface.co/thinkingmachines/TML-d24-varloop-research, read 24 Nov 2026).
// Thinking Machines' own runs of its research model at 1 to 5 loops.
const CARD =
  "https://huggingface.co/thinkingmachines/TML-d24-varloop-research#5-evaluations";

const LOOPS = [1, 2, 3, 4, 5];

// BrowseComp, original, no context management.
const BROWSECOMP = [29.4, 53.8, 65.7, 69.4, 71.0];

export const BrowseCompFigure = (): ReactElement => (
  <figure className="lr">
    <p className="lr-title">BrowseComp</p>
    <p className="lr-sub">
      Hard-to-find answers on the web, by number of loops. Inkling 2 Mini always
      runs 3.
    </p>

    <ol className="lr-bars" aria-label="BrowseComp score by number of loops">
      {LOOPS.map((loops, i) => (
        <li
          className={loops === 3 ? "lr-bar lr-bar--mini" : "lr-bar"}
          key={loops}
          style={{ "--h": BROWSECOMP[i] / 100 } as CSSProperties}
          title={`${loops} ${loops === 1 ? "loop" : "loops"}: ${BROWSECOMP[i].toFixed(1)}%`}
        >
          <span className="lr-value">{BROWSECOMP[i].toFixed(1)}%</span>
          <span className="lr-fill" aria-hidden="true" />
          <span className="lr-loops">
            {loops}
            <span className="gr-visually-hidden">
              {loops === 1 ? " loop" : " loops"}
            </span>
          </span>
        </li>
      ))}
    </ol>
    <p className="lr-axis" aria-hidden="true">
      Loops
    </p>

    <figcaption>
      <a href={CARD}>Thinking Machines, 2026</a>
    </figcaption>
  </figure>
);

type Series = {
  name: string;
  needs: "reasoning" | "knowledge";
  scores: number[];
};

const SERIES: Series[] = [
  { name: "BrowseComp", needs: "reasoning", scores: BROWSECOMP },
  {
    name: "DeepSWE",
    needs: "reasoning",
    scores: [0.7, 28.3, 47.4, 46.9, 48.2],
  },
  {
    name: "AA-Omniscience",
    needs: "knowledge",
    scores: [15.5, 16.3, 18.4, 18.0, 17.4],
  },
  {
    name: "SimpleQA Verified",
    needs: "knowledge",
    scores: [6.3, 6.5, 7.3, 6.8, 6.7],
  },
];

const W = 560;
const H = 300;
const PAD = { top: 16, right: 140, bottom: 46, left: 44 };
const MAX = 80;
const x = (i: number): number =>
  PAD.left + (i * (W - PAD.left - PAD.right)) / (LOOPS.length - 1);
const y = (score: number): number =>
  PAD.top + (1 - score / MAX) * (H - PAD.top - PAD.bottom);

export const LoopsChart = (): ReactElement => (
  <figure className="lr">
    <p className="lr-title">Loops vs. Performance</p>

    <svg aria-hidden="true" className="lr-svg" viewBox={`0 0 ${W} ${H}`}>
      {[0, 20, 40, 60, 80].map((tick) => (
        <g key={tick}>
          <line
            className="lr-grid"
            x1={PAD.left}
            x2={W - PAD.right}
            y1={y(tick)}
            y2={y(tick)}
          />
          <text
            className="lr-tick"
            textAnchor="end"
            x={PAD.left - 10}
            y={y(tick) + 4}
          >
            {tick}%
          </text>
        </g>
      ))}

      {LOOPS.map((loops, i) => (
        <text
          className="lr-tick"
          key={loops}
          textAnchor="middle"
          x={x(i)}
          y={H - PAD.bottom + 22}
        >
          {loops}
        </text>
      ))}

      <text
        className="lr-axis-label"
        textAnchor="middle"
        x={(PAD.left + W - PAD.right) / 2}
        y={H - 4}
      >
        LOOPS
      </text>

      {SERIES.map((series) => (
        <g className={`lr-series lr-series--${series.needs}`} key={series.name}>
          <polyline
            points={series.scores
              .map((score, i) => `${x(i)},${y(score)}`)
              .join(" ")}
          />
          {series.scores.map((score, i) => (
            <circle cx={x(i)} cy={y(score)} key={LOOPS[i]} r={3.5} />
          ))}
          <text
            className="lr-label"
            x={x(LOOPS.length - 1) + 12}
            y={y(series.scores[LOOPS.length - 1]) + 4}
          >
            {series.name}
          </text>
        </g>
      ))}
    </svg>

    <table className="gr-visually-hidden">
      <caption>Score by number of loops</caption>
      <thead>
        <tr>
          <th scope="col">Benchmark</th>
          {LOOPS.map((loops) => (
            <th key={loops} scope="col">
              {loops} {loops === 1 ? "loop" : "loops"}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {SERIES.map((series) => (
          <tr key={series.name}>
            <th scope="row">
              {series.name}, needs {series.needs}
            </th>
            {series.scores.map((score, i) => (
              <td key={LOOPS[i]}>{score.toFixed(1)}%</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>

    <figcaption className="lr-foot">
      <span className="lr-key" aria-hidden="true">
        <span className="lr-key-line" /> Needs reasoning
        <span className="lr-key-line lr-key-line--knowledge" /> Needs knowledge
      </span>
      <a href={CARD} rel="noreferrer" target="_blank">
        Hugging Face
      </a>
    </figcaption>
  </figure>
);
