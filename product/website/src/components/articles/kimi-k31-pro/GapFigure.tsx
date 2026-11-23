import { useState, type CSSProperties, type ReactElement } from "react";
import "./gap-figure.css";

type Lab = "google" | "anthropic" | "openai" | "moonshot" | "zai" | "deepseek";
type Row = {
  lab: Lab;
  model: string;
  value: number;
  open: boolean;
  solved?: number;
  sub?: string;
  self?: boolean;
};
type View = "kimi" | "field" | "cost";
type Panel = {
  tab: string;
  title: string;
  when: string;
  unit: "pct" | "usd";
  max: number;
  ticks: number[];
  rows: Row[];
  source?: { label: string; href: string; agent: string };
};

const LAB_NAMES: Record<Lab, string> = {
  google: "Google",
  anthropic: "Anthropic",
  openai: "OpenAI",
  moonshot: "Moonshot",
  zai: "Z.ai",
  deepseek: "DeepSeek",
};

const LAB_TONES: Record<Lab, string> = {
  google: "var(--color-hw-pcb)",
  anthropic: "var(--color-kiln-500)",
  openai: "var(--color-text)",
  moonshot: "var(--color-cloud-blue)",
  zai: "var(--color-cloud-lavender)",
  deepseek: "var(--color-cloud-pink)",
};

const FEATURED = "Kimi K3.1 Pro";

// Scores: tbench.ai/leaderboard/terminal-bench/4.1 (read 16 Nov 2026).
// Costs: Artificial Analysis, see below.
const PANELS: Record<View, Panel> = {
  kimi: {
    tab: "Kimi vs Kimi",
    title: "Terminal-Bench 4.1",
    when: "",
    unit: "pct",
    max: 80,
    ticks: [0, 20, 40, 60, 80],
    rows: [
      {
        lab: "moonshot",
        model: FEATURED,
        value: 59.7,
        open: true,
        sub: "October, 2026",
      },
      {
        lab: "moonshot",
        model: "Kimi K3",
        value: 23.0,
        open: true,
        sub: "July, 2026",
      },
    ],
  },
  field: {
    tab: "Kimi vs the Frontier",
    title: "Terminal-Bench 4.1",
    when: "",
    unit: "pct",
    max: 80,
    ticks: [0, 20, 40, 60, 80],
    rows: [
      { lab: "anthropic", model: "Claude Opus 5.5", value: 65.8, open: false },
      { lab: "anthropic", model: "Claude Fable 5.2", value: 65.8, open: false },
      { lab: "google", model: "Gemini 4 Carbon", value: 64.5, open: false },
      {
        lab: "anthropic",
        model: "Claude Sonnet 5.5",
        value: 63.9,
        open: false,
      },
      { lab: "openai", model: "GPT-6.1 Sol", value: 60.9, open: false },
      { lab: "openai", model: "GPT-6 Astra", value: 60.3, open: false },
      { lab: "moonshot", model: FEATURED, value: 59.7, open: true },
      { lab: "zai", model: "GLM-5.3", value: 41.2, open: true },
      {
        lab: "deepseek",
        model: "DeepSeek V4.1 Flash",
        value: 38.5,
        open: true,
      },
    ],
  },
  // artificialanalysis.ai/evaluations/terminalbench-4-0 (read 16 Nov 2026): average cost
  // per task and score, mini-swe-agent for every model, read off the public chart.
  cost: {
    tab: "Cost",
    title: "Cost per Terminal-Bench 4.0 task",
    when: "",
    source: {
      label: "Artificial Analysis",
      href: "https://artificialanalysis.ai/evaluations/terminalbench-4-0",
      agent: "mini-swe-agent",
    },
    unit: "usd",
    max: 35,
    ticks: [0, 10, 20, 30],
    rows: [
      // `solved` is the Terminal-Bench 4.1 score, so rows match the field view's order.
      {
        lab: "anthropic",
        model: "Claude Opus 5.5",
        value: 13.11,
        open: false,
        solved: 65.8,
      },
      {
        lab: "anthropic",
        model: "Claude Fable 5.2",
        value: 31.59,
        open: false,
        solved: 65.8,
      },
      {
        lab: "google",
        model: "Gemini 4 Carbon",
        value: 7.11,
        open: false,
        solved: 64.5,
      },
      {
        lab: "anthropic",
        model: "Claude Sonnet 5.5",
        value: 12.65,
        open: false,
        solved: 63.9,
      },
      {
        lab: "openai",
        model: "GPT-6.1 Sol",
        value: 1.82,
        open: false,
        solved: 60.9,
      },
      {
        lab: "openai",
        model: "GPT-6 Astra",
        value: 8.5,
        open: false,
        solved: 60.3,
      },
      {
        lab: "moonshot",
        model: FEATURED,
        value: 5.27,
        open: true,
        solved: 59.7,
      },
      { lab: "zai", model: "GLM-5.3", value: 8.06, open: true, solved: 41.2 },
      {
        lab: "deepseek",
        model: "DeepSeek V4.1 Flash",
        value: 0.88,
        open: true,
        solved: 38.5,
      },
    ],
  },
};

const VIEWS: View[] = ["kimi", "field", "cost"];

const format = (value: number, unit: Panel["unit"]): string =>
  unit === "pct" ? `${value.toFixed(1)}%` : `$${value.toFixed(2)}`;

const tickLabel = (tick: number, unit: Panel["unit"]): string =>
  unit === "pct" ? `${tick}%` : `$${tick}`;

const BenchPanel = ({ panel }: { panel: Panel }): ReactElement => (
  <section
    className="kt-panel"
    aria-label={panel.when ? `${panel.title}, ${panel.when}` : panel.title}
  >
    <div className="kt-head">
      <span className="kt-title">{panel.title}</span>
      {panel.when ? <span className="kt-when">{panel.when}</span> : null}
    </div>

    <div className="kt-plot">
      <div aria-hidden="true" className="kt-row kt-axis">
        <span />
        <ol className="kt-ticks">
          {panel.ticks.map((tick) => (
            <li
              key={tick}
              style={{ "--at": tick / panel.max } as CSSProperties}
            >
              {tickLabel(tick, panel.unit)}
            </li>
          ))}
        </ol>
        <span />
      </div>

      <ul className="kt-rows">
        {[...panel.rows]
          .sort((a, b) => (b.solved ?? b.value) - (a.solved ?? a.value))
          .map((row) => (
            <li
              className={
                row.model === FEATURED ? "kt-row kt-row--kimi" : "kt-row"
              }
              key={row.model}
              style={
                {
                  "--w": row.value / panel.max,
                  "--tone": LAB_TONES[row.lab],
                } as CSSProperties
              }
            >
              <span className="kt-name">
                <span className="kt-model">{row.model}</span>
                <span className="kt-lab">
                  {row.sub ?? LAB_NAMES[row.lab]}
                  {row.self ? (
                    <span className="kt-self"> · self-reported</span>
                  ) : null}
                  <span className="gr-visually-hidden">
                    {row.open ? ", open weights" : ", closed"}
                  </span>
                </span>
              </span>

              <span className="kt-track">
                <span
                  className={[
                    "kt-fill",
                    row.open ? "kt-fill--open" : "",
                    row.self ? "kt-fill--self" : "",
                  ].join(" ")}
                />
              </span>

              <span className="kt-value">{format(row.value, panel.unit)}</span>
            </li>
          ))}
      </ul>
    </div>
  </section>
);

export const GapToggle = (): ReactElement => {
  const [view, setView] = useState<View>("kimi");
  const hasSelf = PANELS[view].rows.some((row) => row.self);
  const source = PANELS[view].source;

  return (
    <figure className="kt" aria-label={PANELS[view].title}>
      <div className="kt-bar">
        <div className="kt-switch" role="group" aria-label="Choose a view">
          {VIEWS.map((option) => (
            <button
              aria-pressed={view === option}
              className="kt-switch-btn"
              key={option}
              onClick={() => setView(option)}
              type="button"
            >
              {PANELS[option].tab}
            </button>
          ))}
        </div>
      </div>

      <BenchPanel panel={PANELS[view]} />

      <div className="kt-foot">
        <p className="kt-key" aria-hidden="true">
          <span className="kt-key-item">
            <span className="kt-swatch" /> Closed
          </span>
          <span className="kt-key-item">
            <span className="kt-swatch kt-swatch--open" /> Open weights
          </span>
          {hasSelf ? (
            <span className="kt-key-item">
              <span className="kt-swatch kt-swatch--self" /> Self-reported
            </span>
          ) : null}
        </p>

        {source ? (
          <p className="kt-source">
            Source:{" "}
            <a href={source.href} rel="noreferrer" target="_blank">
              {source.label}
            </a>
            . The same agent ({source.agent}) was used with every model.
          </p>
        ) : null}
      </div>
    </figure>
  );
};

export const GapSources = (): ReactElement => (
  <section className="kt-sources">
    <p className="kt-sources-title">Graph sources</p>
    <ul>
      <li>
        Kimi vs Kimi and Kimi vs the Frontier: the{" "}
        <a href="https://www.tbench.ai/leaderboard/terminal-bench/4.1">
          Terminal-Bench 4.1 leaderboard
        </a>
        , as of 16 Nov 2026. No score comes from a lab&apos;s own announcement.
        Kimi, GLM, DeepSeek and Claude models were run with the Claude Code
        agent, Gemini with Antigravity CLI and GPT with Codex.
      </li>
      <li>
        The six closed models are the six highest-scoring models on the
        leaderboard. Each score has a 95% confidence interval of about ±3–4
        points, so Kimi K3.1 Pro (59.7%) is level with GPT-6 Astra (60.3%) and
        GPT-6.1 Sol (60.9%).
      </li>
      <li>
        Cost: average cost per task on Terminal-Bench 4.0 from{" "}
        <a href="https://artificialanalysis.ai/evaluations/terminalbench-4-0">
          Artificial Analysis
        </a>
        , as of 16 Nov 2026. Artificial Analysis runs every model itself with
        the same agent (mini-swe-agent), so its scores differ from the
        leaderboard&apos;s: Kimi K3.1 Pro scores 67.2% there and Claude Opus 5.5
        59.6%. Rows are in the same order as Kimi vs the Frontier.
      </li>
    </ul>
  </section>
);
