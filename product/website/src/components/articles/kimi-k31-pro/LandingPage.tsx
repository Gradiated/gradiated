import { ArrowUpRight, ChartNoAxesColumn } from "lucide-react";
import { useId, useState } from "react";
import type { KeyboardEvent, ReactElement } from "react";
import "./landing-page.css";

// One unedited attempt per model at maximum reasoning, 19–23 Nov 2026.
// Kimi K3.1 Pro cost is tokens × our $8/M list price; the rest are OpenRouter bills.
const PROMPT =
  "Make a landing page for a new SaaS product. Impress me with what you can do.";
const DIR = "/benchmark/saas-landing-page";

type Run = {
  model: string;
  slug: string;
  servedBy: string;
  tokens: number;
  tokensPerSecond: number;
  seconds: number;
  costUsd: number;
  joules?: number;
};

const RUNS: Run[] = [
  {
    model: "Kimi K3.1 Pro",
    slug: "kimi-k3.1-pro",
    servedBy: "Gradiated",
    tokens: 31_781,
    tokensPerSecond: 276,
    seconds: 115,
    costUsd: 0.254,
    joules: 524_000,
  },
  {
    model: "Kimi K3",
    slug: "kimi-k3",
    servedBy: "Modal, via OpenRouter",
    tokens: 13_821,
    tokensPerSecond: 77.5,
    seconds: 179,
    costUsd: 0.207,
  },
  {
    model: "Sonnet 5.5",
    slug: "claude-sonnet-5.5",
    servedBy: "Google, via OpenRouter",
    tokens: 85_658,
    tokensPerSecond: 164.8,
    seconds: 523,
    costUsd: 0.857,
  },
  {
    model: "Opus 5.5",
    slug: "claude-opus-5.5",
    servedBy: "Azure, via OpenRouter",
    tokens: 126_620,
    tokensPerSecond: 124.7,
    seconds: 1019,
    costUsd: 2.533,
  },
];

export const LandingPage = (): ReactElement => {
  const [active, setActive] = useState(0);
  const id = useId();
  const run: Run | undefined = RUNS[active];
  const tabs = [...RUNS.map((item) => item.model), "Compare"];

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>): void => {
    const step =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;

    event.preventDefault();
    const next = (active + step + tabs.length) % tabs.length;
    setActive(next);
    document.getElementById(`${id}-tab-${next}`)?.focus();
  };

  return (
    <div className="lp">
      <p className="lp-prompt">“{PROMPT}”</p>

      <div aria-label="Model" className="lp-tabs" role="tablist">
        {tabs.map((label, index) => (
          <button
            aria-controls={`${id}-panel`}
            aria-selected={index === active}
            className={
              index === RUNS.length ? "lp-tab lp-tab--compare" : "lp-tab"
            }
            id={`${id}-tab-${index}`}
            key={label}
            onClick={() => setActive(index)}
            onKeyDown={onKeyDown}
            role="tab"
            tabIndex={index === active ? 0 : -1}
            type="button"
          >
            {index === RUNS.length && (
              <ChartNoAxesColumn aria-hidden="true" className="lp-tab__icon" />
            )}
            {label}
          </button>
        ))}
      </div>

      <div
        aria-labelledby={`${id}-tab-${active}`}
        id={`${id}-panel`}
        role="tabpanel"
      >
        {run ? <RunView run={run} /> : <Compare />}
      </div>
    </div>
  );
};

const RunView = ({ run }: { run: Run }): ReactElement => (
  <>
    <a
      className="lp-preview"
      href={`${DIR}/${run.slug}.html`}
      rel="noopener"
      target="_blank"
    >
      <span aria-hidden="true" className="lp-bar">
        <i />
        <i />
        <i />
        <ArrowUpRight className="lp-arrow" />
      </span>
      <img
        alt={`The top of the landing page ${run.model} made. Opens the full page.`}
        className="lp-shot"
        height={1000}
        loading="lazy"
        src={`${DIR}/${run.slug}.jpg`}
        width={1600}
      />
    </a>

    <p className="lp-summary">
      <span>{formatDuration(run.seconds)}</span>
      <span>${run.costUsd.toFixed(3)}</span>
      {run.joules ? (
        <span>{`${run.joules / 1000}\u00a0kJ`}</span>
      ) : (
        <span className="lp-summary__muted">GPU energy not shared</span>
      )}
      <span className="lp-summary__served">Served by {run.servedBy}</span>
    </p>
  </>
);

const formatDuration = (seconds: number): string => {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);

  // U+00A0 no-break space keeps each number with its unit.
  return minutes ? `${minutes}\u00a0min ${rest}\u00a0s` : `${rest}\u00a0s`;
};

const MEASURES: {
  label: string;
  value: (run: Run) => number | undefined;
  format: (value: number) => string;
}[] = [
  {
    label: "Output tokens",
    value: (run) => run.tokens,
    format: (value) => value.toLocaleString("en-US"),
  },
  {
    label: "Tokens per second",
    value: (run) => run.tokensPerSecond,
    format: (value) => String(value),
  },
  {
    label: "Time",
    value: (run) => run.seconds,
    format: formatDuration,
  },
  {
    label: "Cost",
    value: (run) => run.costUsd,
    format: (value) => `$${value.toFixed(2)}`,
  },
  {
    label: "GPU energy",
    value: (run) => (run.joules ? run.joules / 1000 : undefined),
    format: (value) => `${value}\u00a0kJ`,
  },
];

const Compare = (): ReactElement => (
  <div className="lp-compare">
    {MEASURES.map((measure) => {
      const max = Math.max(...RUNS.map((run) => measure.value(run) ?? 0));

      return (
        <div className="lp-measure" key={measure.label}>
          <p className="lp-measure__title">{measure.label}</p>
          {RUNS.map((run) => {
            const value = measure.value(run);

            return (
              <div className="lp-measure__row" key={run.slug}>
                <span>{run.model}</span>
                <span className="lp-measure__track">
                  {value === undefined ? (
                    <span className="lp-measure__ghost" />
                  ) : (
                    <span
                      className="lp-measure__bar"
                      style={{ width: `${Math.max(2, (value / max) * 100)}%` }}
                    />
                  )}
                </span>
                <b className={value === undefined ? "lp-measure__none" : ""}>
                  {value === undefined ? "not shared" : measure.format(value)}
                </b>
              </div>
            );
          })}
        </div>
      );
    })}
    <p className="lp-served">
      Kimi K3, Sonnet 5.5 and Opus 5.5 ran through OpenRouter.
    </p>
  </div>
);
