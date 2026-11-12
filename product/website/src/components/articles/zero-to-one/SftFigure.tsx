import type { CSSProperties, ReactElement, ReactNode } from "react";
import "./sft-figure.css";

// research/experiments/2026-11-02-posthog-ai-agent/data/epoch_dev_results.csv
const PASSED = [
  { label: "Before", value: 5, base: true },
  { label: "1", value: 4 },
  { label: "2", value: 3 },
  { label: "3", value: 5 },
];

const MAX = 18;
const TICKS = [0, 6, 12, 18];

export const SftFigure = ({
  children,
}: {
  children?: ReactNode;
}): ReactElement => (
  <div className="sf-spread">
    {children ? <div className="sf-text">{children}</div> : null}

    <figure className="sf">
      <div className="sf-chart">
        <p className="sf-title">Tasks Qwen passed, out of 18</p>

        <div className="sf-plot">
          <ol aria-hidden="true" className="sf-ticks">
            {TICKS.map((tick) => (
              <li key={tick} style={{ "--at": tick / MAX } as CSSProperties}>
                {tick}
              </li>
            ))}
          </ol>

          <ul className="sf-bars">
            {PASSED.map((bar) => (
              <li
                className={bar.base ? "sf-bar sf-bar--base" : "sf-bar"}
                key={bar.label}
                style={{ "--h": bar.value / MAX } as CSSProperties}
              >
                <span className="sf-value">{bar.value}</span>
                <span className="sf-fill" />
                <span className="sf-label">{bar.label}</span>
              </li>
            ))}
          </ul>
        </div>

        <p className="sf-axis">Rounds of training (epochs)</p>
      </div>
    </figure>
  </div>
);
