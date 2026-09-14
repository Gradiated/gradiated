import type { CSSProperties, ReactElement } from "react";
import { Logo } from "./Logo";

/** User-selected display scores. Source values are recorded in the README. */

type Model = {
  kind: "base" | "frontier" | "tuned";
  label: string;
  score: number;
  costPerTask: number;
};

type Task = { models: Model[]; name: string };

// USD per task: 8,000 uncached input tokens and 1,000 output tokens.
const taskCost = (input: number, output: number) =>
  (8_000 * input + 1_000 * output) / 1_000_000;
const baseCost = taskCost(0.15, 0.5);
const costPosition = (cost: number) =>
  (Math.log10(cost / 0.0005) / Math.log10(0.15 / 0.0005)) * 100;

const PRODUCT_EVAL: Task = {
  name: "Support resolution",
  models: [
    {
      kind: "base",
      label: "Base GLM-5.3-Flash",
      score: 54,
      costPerTask: baseCost,
    },
    {
      kind: "tuned",
      label: "Post-trained GLM-5.3-Flash — SFT + GRPO",
      score: 76,
      costPerTask: baseCost * 1.2,
    },
    { kind: "frontier", label: "Sol", score: 88, costPerTask: taskCost(4, 20) },
  ],
};

// Use the full percentage range.
const FLOOR = 0;
const ROOF = 100;

const upAt = (score: number) => ((score - FLOOR) / (ROOF - FLOOR)) * 100;

/* Marks instead of names on the badges: three words of the same size as the
   numbers made every badge a sentence, and the scores are what the picture is
   for. The post-trained one is the Gradiated mark — it is ours, and saying so
   with the logo is shorter than saying so in words.

   Icons alone would be a guessing game, so the key below spells them out. Two
   abstract shapes are not self-evident and pretending otherwise just moves the
   reading cost somewhere less convenient. */
const MARKS = {
  /* A hollow square: the weights as they came, unmodified. */
  base: (
    <svg aria-hidden fill="none" viewBox="0 0 12 12">
      <rect
        height="8"
        rx="1.5"
        stroke="currentColor"
        strokeWidth="1.5"
        width="8"
        x="2"
        y="2"
      />
    </svg>
  ),
  /* A filled diamond: a different class of thing, not a better square. */
  frontier: (
    <svg aria-hidden fill="currentColor" viewBox="0 0 12 12">
      <path d="M6 1.2 10.8 6 6 10.8 1.2 6Z" />
    </svg>
  ),
  tuned: null,
} as const;

export const Benchmark = (): ReactElement => {
  const task = PRODUCT_EVAL;
  const base = task.models.find((model) => model.kind === "base");
  const tuned = task.models.find((model) => model.kind === "tuned");
  const regressed = base && tuned ? tuned.score < base.score : false;

  return (
    <figure className="gr-bench">
      <figcaption className="gr-bench-heading">
        <span className="gr-bench-title">{task.name}</span>
        <span className="gr-bench-subtitle">
          Post-training GLM 5.3 Flash for a support resolution agent improved
          the outcomes substantially, at 1/25th of the cost of Sol.
        </span>
      </figcaption>

      <div className="gr-bench-field">
        <span aria-hidden className="gr-bench-grid" />

        <span aria-hidden className="gr-bench-axis gr-bench-axis--y gr-label">
          Score
        </span>
        <span aria-hidden className="gr-bench-axis gr-bench-axis--x gr-label">
          Cost per task
        </span>

        {[0.001, 0.01, 0.1].map((cost) => (
          <span
            key={cost}
            className="gr-bench-cost-tick"
            style={{ left: `${costPosition(cost)}%` }}
          >
            ${Number((cost * 100).toFixed(2))}
          </span>
        ))}

        {task.models.map((model) => (
          <span
            className={`gr-bench-badge gr-bench-badge--${model.kind}${
              model.kind === "tuned" && regressed ? " gr-bench-badge--down" : ""
            }`}
            key={model.kind}
            style={
              {
                "--delay": `${["base", "tuned", "frontier"].indexOf(model.kind) * 70}ms`,
                "--left": `${costPosition(model.costPerTask)}%`,
                "--up": `${upAt(model.score)}%`,
              } as CSSProperties
            }
          >
            <span aria-hidden className="gr-bench-badge-mark">
              {model.kind === "tuned" ? (
                <Logo height={13} mark />
              ) : (
                MARKS[model.kind]
              )}
            </span>
            <span className="gr-visually-hidden">{model.label}</span>
            <span className="gr-bench-badge-score" key={task.name}>
              {model.score}%
            </span>
          </span>
        ))}
      </div>

      {task.models.length > 0 && (
        <p className="gr-bench-key">
          {task.models.map((model) => (
            <span className="gr-bench-key-item" key={model.kind}>
              <span
                aria-hidden
                className={`gr-bench-badge-mark gr-bench-badge-mark--${model.kind}`}
              >
                {model.kind === "tuned" ? (
                  <Logo height={12} mark />
                ) : (
                  MARKS[model.kind]
                )}
              </span>
              <span>
                {model.label}
                <small className="gr-bench-model-cost">
                  ${Number((model.costPerTask * 100).toFixed(3))} / task
                </small>
              </span>
              <span className="gr-bench-key-score">{model.score}%</span>
            </span>
          ))}
        </p>
      )}
    </figure>
  );
};
