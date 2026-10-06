import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import {
  Band,
  CodeBlock,
  Features,
  Footer,
  Module,
  Nav,
  Substrate,
} from "../components/design";
import { WaitlistButton } from "../components/WaitlistButton";
import { listModels } from "../api/queries";
import { models } from "../models";
import type { ModelPageData } from "../models";
import "../styles/index.css";

/**
 * A model's page: what it is, what it is good for, the numbers, and the way
 * in. The page is built to end one way — "let's post-train this" — so every
 * section leans toward the workload the reader already has: benchmarks says
 * where the model starts, getting started says how traffic becomes traces,
 * and the close says what we do with them.
 *
 * Copy and benchmarks live in src/models.ts. Pricing and context render from
 * the same static mirror, then ModelVitals refreshes them from the live API —
 * the catalog is the source of truth for money, and a repriced model should
 * not wait for a website deploy.
 */

/** The live row for this model, refreshed after mount. The static mirror
 *  renders first — same numbers, same source — so the page needs nothing
 *  from the network to be whole. */
const ModelVitals = ({ model }: { model: ModelPageData }): ReactElement => {
  const [vitals, setVitals] = useState(model.vitals);

  useEffect(() => {
    let cancelled = false;
    void listModels()
      .then((result) => {
        const live = result.data.find((entry) => entry.id === model.id);
        if (!live || cancelled) return;
        const input = live.properties.input_modalities[0];
        const output = live.properties.output_modalities[0];
        const price = (
          entries: { type: string; cost: number }[] | undefined,
          type: string,
        ): string | null => {
          const entry = entries?.find((candidate) => candidate.type === type);
          if (!entry) return null;
          return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: "USD",
            minimumFractionDigits: 2,
            maximumFractionDigits: 4,
          }).format(entry.cost / 1_000);
        };
        const context = input?.supported_inputs.max_context_length.value;
        setVitals({
          input: price(input?.pricing, "prompt") ?? model.vitals.input,
          cachedInput:
            price(input?.pricing, "cached_prompt") ?? model.vitals.cachedInput,
          output: price(output?.pricing, "completion") ?? model.vitals.output,
          context: context
            ? new Intl.NumberFormat("en-US", {
                notation: "compact",
                maximumFractionDigits: 1,
              }).format(context)
            : model.vitals.context,
        });
      })
      .catch(() => {
        // The static mirror is already on screen; a failed refresh changes nothing.
      });
    return () => {
      cancelled = true;
    };
  }, [model]);

  const CELLS = [
    { label: "Input / 1M", value: vitals.input },
    { label: "Cached input / 1M", value: vitals.cachedInput },
    { label: "Output / 1M", value: vitals.output },
    { label: "Context", value: vitals.context },
  ];

  return (
    <dl className="gr-model-vitals">
      {CELLS.map((cell) => (
        <div className="gr-model-vital" key={cell.label}>
          <dt className="gr-label">{cell.label}</dt>
          <dd>{cell.value}</dd>
        </div>
      ))}
    </dl>
  );
};

const CopyModelId = ({ id }: { id: string }): ReactElement => {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="gr-model-id"
      type="button"
      onClick={() => {
        void navigator.clipboard.writeText(id).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1600);
        });
      }}
    >
      <code>{id}</code>
      <span className="gr-label">{copied ? "Copied" : "Copy"}</span>
    </button>
  );
};

export const ModelDetailPage = ({
  model,
}: {
  model: ModelPageData;
}): ReactElement => {
  const similar = models.filter((entry) => entry.slug !== model.slug);

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module bleed index={0}>
          <div className="gr-model-head">
            {/* The provider's mark where one exists; the monogram holds the
                space until every model has its own. */}
            <div className="gr-model-mark">
              {model.icon ? <img alt="" src={model.icon} /> : model.mark}
            </div>
            <div>
              <p className="gr-label gr-model-maker">{model.maker}</p>
              <h1 className="gr-section-title">{model.name}</h1>
              <p className="gr-lede gr-muted gr-model-lede">{model.oneLiner}</p>
              <ul className="gr-model-tags">
                {model.tags.map((tag) => (
                  <li className="gr-badge" key={tag}>
                    {tag}
                  </li>
                ))}
              </ul>
              <CopyModelId id={model.id} />
            </div>
          </div>
        </Module>

        <Module index={1}>
          <div className="gr-model-overview">
            {model.overview.map((paragraph) => (
              <p className="gr-body" key={paragraph.slice(0, 32)}>
                {paragraph}
              </p>
            ))}
          </div>
        </Module>

        <Module index={2}>
          <h2 className="gr-heading gr-pair-title" id="good-for">
            What it&rsquo;s good for
          </h2>
          <Features items={model.goodFor} />
        </Module>

        <Module index={3}>
          <h2 className="gr-heading gr-pair-title" id="benchmarks">
            Benchmarks
          </h2>
          <div className="gr-model-bench">
            {model.benchmarks.map((benchmark) => (
              <div className="gr-model-bench-row" key={benchmark.name}>
                <span className="gr-model-bench-name">{benchmark.name}</span>
                {benchmark.bar ? (
                  <span className="gr-model-bench-track" aria-hidden>
                    <span
                      className="gr-model-bench-bar"
                      style={{ width: `${benchmark.bar}%` }}
                    />
                  </span>
                ) : (
                  <span aria-hidden />
                )}
                <span className="gr-model-bench-score">
                  {benchmark.score}
                  {benchmark.note ? (
                    <span className="gr-model-bench-note">
                      {benchmark.note}
                    </span>
                  ) : null}
                </span>
              </div>
            ))}
          </div>
          <p className="gr-body gr-muted gr-model-bench-footnote">
            {model.benchmarksNote}
          </p>
        </Module>

        <Module index={4}>
          <h2 className="gr-heading gr-pair-title" id="pricing">
            Pricing &amp; specs
          </h2>
          <ModelVitals model={model} />
          <dl className="gr-model-specs">
            {model.specs.map((spec) => (
              <div className="gr-model-spec" key={spec.label}>
                <dt className="gr-label">{spec.label}</dt>
                <dd className="gr-body">{spec.value}</dd>
              </div>
            ))}
          </dl>
          <p className="gr-body gr-muted">
            Latency is a choice, not a property of the model —{" "}
            <a className="gr-link" href="/inference/">
              pick the service tier
            </a>{" "}
            your workload needs.
          </p>
        </Module>

        <Module index={5}>
          <h2 className="gr-heading gr-pair-title" id="getting-started">
            Getting started
          </h2>
          <p className="gr-body gr-muted gr-model-start-lede">
            {model.gettingStarted.lede}
          </p>
          <div className="gr-model-snippets">
            {model.gettingStarted.snippets.map((snippet) => (
              <div
                className="gr-model-snippet gr-model-code"
                key={snippet.label}
              >
                <p className="gr-label">{snippet.label}</p>
                <CodeBlock code={snippet.code} />
              </div>
            ))}
          </div>
          <p className="gr-body gr-muted">
            <a className="gr-link" href={model.gettingStarted.docsHref}>
              {model.gettingStarted.docsLabel}
            </a>
          </p>
        </Module>

        <Module index={6}>
          <div className="gr-model-close">
            <h2 className="gr-heading" id="post-train">
              Then make it yours.
            </h2>
            <p className="gr-body gr-muted">
              These numbers are where {model.name} starts, not where it ends.
              Once your traffic runs through Gradiated, we turn your traces into
              an RL environment, build the evals, and post-train the model on
              your actual workload — same API, same base URL, better model every
              week.
            </p>
            <div className="gr-model-close-actions">
              <WaitlistButton className="gr-button gr-button--main">
                Join the waitlist
              </WaitlistButton>
              <a className="gr-button gr-button--secondary" href="/training/">
                How post-training works
              </a>
            </div>
          </div>
        </Module>

        <Module index={7}>
          <h2 className="gr-heading gr-pair-title" id="similar">
            Other models
          </h2>
          <div className="gr-model-similar">
            {similar.map((entry) => (
              <a
                className="gr-model-similar-card"
                href={`/models/${entry.slug}/`}
                key={entry.slug}
              >
                <span className="gr-model-mark gr-model-mark--small">
                  {entry.icon ? <img alt="" src={entry.icon} /> : entry.mark}
                </span>
                <span>
                  <span className="gr-model-similar-name">{entry.name}</span>
                  <span className="gr-body gr-muted gr-model-similar-line">
                    {entry.oneLiner}
                  </span>
                </span>
              </a>
            ))}
          </div>
        </Module>
      </Band>

      <Band>
        <Footer index={8} />
      </Band>
    </Substrate>
  );
};
