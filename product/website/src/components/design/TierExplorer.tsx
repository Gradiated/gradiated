import { useEffect, useState } from "react";
import type { CSSProperties, ReactElement } from "react";
import { CodeBlock } from "./CodeBlock";
import { Tabs } from "./Tabs";
import { TIERS, snippetFor } from "./tiers";
import type { Language, Sdk } from "./tiers";

/**
 * The hero's interactive panel: a sample on the left, the tier it is set to on
 * the right.
 *
 * The point of the composition is that the two halves are ONE control. Moving
 * the tier changes the claim, the description and the `service_tier` line in
 * the sample together — the reader is not being shown a price list beside some
 * code, they are being shown what the code does to the price.
 *
 * The tier is a range input rather than three buttons. It is an ordered
 * trade-off — faster, default, flex — and a slider says "these are points on
 * one axis" where buttons say "these are three unrelated options". It also
 * gets keyboard support, labelling and a drag gesture for free.
 */
export const TierExplorer = (): ReactElement => {
  const [tierIndex, setTierIndex] = useState(0);
  const [sdk, setSdk] = useState<Sdk>("openai");
  const [language, setLanguage] = useState<Language>("python");
  const [copied, setCopied] = useState(false);

  /* The confirmation is temporary, and it belongs to the CURRENT sample —
     changing SDK, language or tier makes a copied clipboard stale, so the
     label goes back to its resting state. */
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  useEffect(() => setCopied(false), [sdk, language, tierIndex]);

  const tier = TIERS[tierIndex];

  return (
    <div className="gr-tier">
      <div className="gr-tier-code">
        {/* The SDK row: the choice, and the one action on the sample beside
            it. Ruled off below, so the language tabs read as a control on the
            code rather than a second control of the same kind. */}
        <div className="gr-tier-code-head">
          <Tabs
            label="SDK"
            onChange={(v) =>
              setSdk(v === "Anthropic SDK" ? "anthropic" : "openai")
            }
            options={["OpenAI SDK", "Anthropic SDK"]}
            value={sdk === "openai" ? "OpenAI SDK" : "Anthropic SDK"}
          />
          <button
            className="gr-button gr-button--ghost gr-tier-copy"
            onClick={() => {
              void navigator.clipboard
                .writeText(snippetFor(sdk, language, tier.id))
                .then(() => setCopied(true))
                .catch(() => setCopied(false));
            }}
            type="button"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>

        <Tabs
          label="Language"
          onChange={(v) => setLanguage(v === "Node" ? "node" : "python")}
          options={["Python", "Node"]}
          quiet
          value={language === "python" ? "Python" : "Node"}
        />

        <CodeBlock code={snippetFor(sdk, language, tier.id)} copyable={false} />
      </div>

      {/* The tier card. Its own surface, because it is a control panel rather
          than a continuation of the sample — and it is what the eye should
          reach for after reading one line of the code. */}
      <div className="gr-tier-panel">
        <h2 className="gr-heading">Lower cost when your request can wait.</h2>

        <p className="gr-label gr-tier-legend">Select mode</p>

        <p className="gr-tier-claim">
          <span className="gr-tier-claim-figure">{tier.claim}</span>
          <span className="gr-tier-note">{tier.claimNote}</span>
        </p>

        {/* The native input keeps the interaction — drag, arrow keys, the
            role and the value — but paints nothing. A range's own thumb is
            positioned by its value and cannot be transitioned, so the visible
            thumb is a separate element that FOLLOWS the value, which is what
            lets it ease between stops instead of snapping. */}
        <div
          className="gr-tier-slider"
          style={
            { "--pos": tierIndex / (TIERS.length - 1) } as CSSProperties
          }
        >
          <input
            aria-label="Service tier"
            aria-valuetext={tier.name}
            className="gr-tier-range"
            max={TIERS.length - 1}
            min={0}
            onChange={(event) => setTierIndex(Number(event.target.value))}
            step={1}
            type="range"
            value={tierIndex}
          />
          <span aria-hidden className="gr-tier-thumb" />
        </div>

        {/* Labelled by position rather than by the input's own ticks, so the
            names sit under the stops they belong to at any width. */}
        <div className="gr-tier-stops">
          {TIERS.map((option, index) => (
            <button
              aria-pressed={index === tierIndex}
              className="gr-tier-stop"
              key={option.id}
              onClick={() => setTierIndex(index)}
              type="button"
            >
              {option.name}
            </button>
          ))}
        </div>

        <p className="gr-label gr-tier-legend">Best suited for</p>
        <p className="gr-tier-note gr-tier-note--strong">{tier.description}</p>
      </div>
    </div>
  );
};
