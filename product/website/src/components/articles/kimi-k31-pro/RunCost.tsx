import type { CSSProperties, ReactElement } from "react";
import "./run-cost.css";

// recipes.vllm.ai/moonshotai/Kimi-K3.1-Pro (read 15 Nov 2026): MXFP4 checkpoint
// in memory; baseline is one 8x B300 node.
const NEED_GB = 1874;
const AXIS_GB = 3000;
const TICKS_TB = [0, 1, 2, 3];

type Setup = {
  gpus: number;
  gpu: string;
  memGb: number;
  perGpuHour: number;
};

// nebius.com/prices, on-demand USD per GPU-hour (read 15 Nov 2026).
const SETUPS: Setup[] = [
  { gpus: 8, gpu: "H100", memGb: 80, perGpuHour: 4.5 },
  { gpus: 8, gpu: "H200", memGb: 141, perGpuHour: 5.4 },
  { gpus: 8, gpu: "B200", memGb: 180, perGpuHour: 8.5 },
  { gpus: 8, gpu: "B300", memGb: 268, perGpuHour: 9.5 },
  { gpus: 16, gpu: "H200", memGb: 141, perGpuHour: 5.4 },
  { gpus: 16, gpu: "B200", memGb: 180, perGpuHour: 8.5 },
];

const totalGb = (setup: Setup): number => setup.gpus * setup.memGb;
const perHour = (setup: Setup): number => setup.gpus * setup.perGpuHour;

const usd = (value: number): string =>
  `$${Math.round(value).toLocaleString("en-US")}`;

export const RunIt = (): ReactElement => (
  <figure className="rc">
    <div className="rc-head">
      <span className="rc-title">GPU memory per server</span>
      <span className="rc-when">Rent per hour</span>
    </div>

    <div className="rc-plot">
      <div aria-hidden="true" className="rc-row rc-axis">
        <span />
        <div className="rc-scale">
          <ol className="rc-ticks">
            {TICKS_TB.map((tick) => (
              <li
                key={tick}
                style={{ "--at": (tick * 1000) / AXIS_GB } as CSSProperties}
              >
                {tick} TB
              </li>
            ))}
          </ol>
          <span
            className="rc-need"
            style={{ "--at": NEED_GB / AXIS_GB } as CSSProperties}
          >
            <span className="rc-need-label">
              {(NEED_GB / 1000).toFixed(2)} TB
            </span>
          </span>
        </div>
        <span />
      </div>

      <ul className="rc-rows">
        {SETUPS.map((setup) => {
          const fits = totalGb(setup) >= NEED_GB;

          return (
            <li
              className={`rc-row${fits ? " rc-row--fits" : ""}`}
              key={`${setup.gpus}-${setup.gpu}`}
            >
              <span className="rc-name">
                {setup.gpus}× {setup.gpu}
                <span className="gr-visually-hidden">
                  , {(totalGb(setup) / 1000).toFixed(2)} TB,{" "}
                  {fits ? "fits the model" : "too little memory"}
                </span>
              </span>
              <span className="rc-track">
                <span
                  className="rc-fill"
                  style={{ "--w": totalGb(setup) / AXIS_GB } as CSSProperties}
                />
              </span>
              <span className="rc-value">{usd(perHour(setup))}/h</span>
            </li>
          );
        })}
      </ul>
    </div>

    <p className="rc-sources">
      Prices: on-demand list prices from{" "}
      <a href="https://nebius.com/prices" rel="noreferrer" target="_blank">
        Nebius
      </a>
      , as of 15 Nov 2026.
    </p>
  </figure>
);
