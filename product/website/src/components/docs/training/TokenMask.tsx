import { useState } from "react";
import type { ReactElement } from "react";

import { renderMessages } from "./data";
import type { ChatMessage, RenderOptions } from "./data";

type Example = { id: string; label: string; messages: ChatMessage[] };

const EXAMPLES: Example[] = [
  {
    id: "chat",
    label: "Support chat",
    messages: [
      {
        role: "system",
        content: "You are Acme's support assistant. Be brief.",
      },
      { role: "user", content: "I was charged twice this month." },
      {
        role: "assistant",
        content: "Sorry about that. Which card was charged?",
      },
      { role: "user", content: "The Visa ending 4242." },
      {
        role: "assistant",
        content:
          "I've refunded the duplicate charge to that Visa. It arrives in 3-5 days.",
      },
    ],
  },
  {
    id: "agent",
    label: "Agent with a tool",
    messages: [
      { role: "user", content: "How many users signed up yesterday?" },
      {
        role: "assistant",
        content:
          '{"tool": "sql", "query": "SELECT count(*) FROM users WHERE created_at >= current_date - 1"}',
      },
      { role: "tool", content: '{"rows": [[412]]}' },
      { role: "assistant", content: "412 people signed up yesterday." },
    ],
  },
  {
    id: "thinking",
    label: "With reasoning",
    messages: [
      { role: "user", content: "Is 391 prime?" },
      {
        role: "assistant",
        content: "<think>391 = 17 x 23.</think>No: 391 = 17 x 23.",
      },
      { role: "user", content: "And 397?" },
      {
        role: "assistant",
        content:
          "<think>Not divisible by 2, 3, 5, 7, 11, 13, 17 or 19; 20^2 > 397.</think>Yes, 397 is prime.",
      },
    ],
  },
];

const Segmented = <T extends string>({
  label,
  options,
  labels,
  value,
  onChange,
}: {
  label: string;
  options: readonly T[];
  labels?: Record<string, string>;
  value: T;
  onChange: (value: T) => void;
}): ReactElement => (
  <fieldset className="gr-dx-seg">
    <legend>{label}</legend>
    <div>
      {options.map((option) => (
        <label key={option}>
          <input
            checked={option === value}
            name={label}
            onChange={() => onChange(option)}
            type="radio"
          />
          <span>{labels?.[option] ?? option}</span>
        </label>
      ))}
    </div>
  </fieldset>
);

const nextOverride = (value: boolean | undefined): boolean | undefined =>
  value === undefined ? true : value ? false : undefined;

export const TokenMask = (): ReactElement => {
  const [exampleId, setExampleId] = useState("chat");
  const [options, setOptions] = useState<RenderOptions>({
    train_on: "last",
    thinking: "auto",
    preserve_thinking: false,
  });
  const [overrides, setOverrides] = useState<
    Record<string, boolean | undefined>
  >({});

  const example = EXAMPLES.find((item) => item.id === exampleId) ?? EXAMPLES[0];
  const messages = example.messages.map((message, index) => ({
    ...message,
    train: overrides[`${example.id}:${index}`],
  }));
  const rendered = renderMessages("r_1", messages, options);
  const setOption = <K extends keyof RenderOptions>(
    key: K,
    value: RenderOptions[K],
  ) => setOptions((current) => ({ ...current, [key]: value }));

  const recipeArgs = [
    options.train_on !== "last" ? `train_on="${options.train_on}"` : null,
    options.thinking !== "auto" ? `thinking="${options.thinking}"` : null,
    options.preserve_thinking ? "preserve_thinking=True" : null,
  ].filter(Boolean);

  return (
    <section aria-label="Loss mask preview" className="gr-dx gr-dx-mask">
      <div className="gr-dx-mask-controls">
        <Segmented
          label="Record"
          labels={Object.fromEntries(
            EXAMPLES.map((item) => [item.id, item.label]),
          )}
          onChange={(id) => setExampleId(id)}
          options={EXAMPLES.map((item) => item.id)}
          value={exampleId}
        />
        <Segmented
          label="train_on"
          onChange={(value) => setOption("train_on", value)}
          options={["last", "all_assistant"] as const}
          value={options.train_on}
        />
        <Segmented
          label="thinking"
          onChange={(value) => setOption("thinking", value)}
          options={["auto", "on", "off"] as const}
          value={options.thinking}
        />
        <label className="gr-dx-check">
          <input
            checked={options.preserve_thinking}
            onChange={(event) =>
              setOption("preserve_thinking", event.target.checked)
            }
            type="checkbox"
          />
          preserve_thinking
        </label>
      </div>

      <div className="gr-dx-mask-legend" aria-hidden="true">
        <span>
          <i className="gr-dx-mask-swatch" data-trained="true" /> trained (loss
          counted)
        </span>
        <span>
          <i className="gr-dx-mask-swatch" /> context only
        </span>
        <span>
          <i className="gr-dx-mask-swatch" data-stripped="true" /> removed
          before training
        </span>
      </div>

      {rendered.ok ? (
        <>
          <pre className="gr-dx-mask-render">
            {rendered.spans.map((span, i) => {
              if (span.kind === "header") {
                const key = `${example.id}:${span.message}`;
                const override = overrides[key];
                return (
                  <span className="gr-dx-mask-header" key={i}>
                    {span.text.trimEnd()}
                    <button
                      aria-label={`Message ${span.message + 1}: train ${override === undefined ? "auto" : String(override)}. Change it.`}
                      className="gr-dx-mask-override"
                      data-set={override === undefined ? undefined : "true"}
                      onClick={() =>
                        setOverrides((current) => ({
                          ...current,
                          [key]: nextOverride(current[key]),
                        }))
                      }
                      type="button"
                    >
                      train:{" "}
                      {override === undefined ? "auto" : String(override)}
                    </button>
                    {"\n"}
                  </span>
                );
              }
              return (
                <span key={i}>
                  {span.stripped ? (
                    <del className="gr-dx-mask-stripped">{span.stripped}</del>
                  ) : null}
                  <span
                    className="gr-dx-mask-body"
                    data-trained={span.trained ? "true" : undefined}
                  >
                    {span.text}
                  </span>
                </span>
              );
            })}
          </pre>
          <p className="gr-dx-mask-stats">
            <span>
              <strong>~{rendered.trainedTokens}</strong> of ~
              {rendered.totalTokens} tokens trained (
              {Math.round(
                (rendered.trainedTokens / rendered.totalTokens) * 100,
              )}
              %)
            </span>
            <span className="gr-dx-muted">
              estimated at about 4 characters per token, as{" "}
              <code>grad render</code> reports them
            </span>
          </p>
        </>
      ) : (
        <div className="gr-dx-mask-error" role="alert">
          <code>render_conflict</code> {rendered.error} The plan fails with this
          error instead of guessing.
        </div>
      )}

      <p className="gr-dx-mask-call">
        <code>
          SFTRecipe(
          {[`model="qwen/qwen3-8b"`, ...recipeArgs].join(", ")})
        </code>
        <code>
          grad render support-sft
          {options.train_on !== "last" ? ` --train-on ${options.train_on}` : ""}
          {options.thinking !== "auto" ? ` --thinking ${options.thinking}` : ""}
        </code>
      </p>
      <p className="gr-dx-caption">
        The <code>train:</code> switch on each message sets that message's own{" "}
        <code>train</code> field, which wins over <code>train_on</code>. Earlier
        assistant turns lose their <code>&lt;think&gt;</code> blocks unless{" "}
        <code>preserve_thinking</code> is on, and a conflict fails the plan
        rather than being patched.
      </p>
    </section>
  );
};

export default TokenMask;
