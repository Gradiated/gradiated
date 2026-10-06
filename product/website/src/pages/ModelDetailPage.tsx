import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactElement } from "react";
import {
  Band,
  CodeBlock,
  Footer,
  Module,
  Nav,
  Substrate,
  Tabs,
} from "../components/design";
import { listModels } from "../api/queries";
import type { ModelPageData } from "../models";
import "../styles/index.css";

/**
 * A model's page, to the reworked layout: identity on the left — art well
 * and factsheet — with the argument beside it, then a contents rail tracking
 * four sections. The page is still built to end one way — "let's post-train
 * this" — benchmarks say where the model starts, getting started says how
 * traffic becomes traces, and the close says what we do with them.
 *
 * Copy and benchmarks live in src/models.ts. Pricing and context render from
 * the same static mirror as the control catalog, then ModelVitals refreshes
 * them from the live API — the catalog is the source of truth for money, and
 * a repriced model should not wait for a website deploy.
 */

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "good-for", label: "What’s it good for" },
  { id: "benchmarks", label: "Benchmarks" },
  { id: "pricing", label: "Pricing & Specs" },
  { id: "getting-started", label: "Getting Started" },
  { id: "hardware", label: "Hardware" },
] as const;

/** The rail beside the sections: a list that knows where the reader is.
 *  The observer band sits high in the viewport, so a section becomes the
 *  active one as its title crosses the reading line, not when its last
 *  pixel arrives.
 *
 *  The rail holds back until the reader has left the first fold — on the
 *  fold the page IS the overview, and a nav answering "where am I" before
 *  the question exists is noise. Overview leads the list so the top of the
 *  page stays one tap away. */
const ContentsRail = (): ReactElement => {
  const [active, setActive] = useState<string>(SECTIONS[0].id);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort(
            (a, b) => a.boundingClientRect.top - b.boundingClientRect.top,
          )[0];
        if (visible) setActive(visible.target.id);
      },
      { rootMargin: "-15% 0px -70% 0px" },
    );
    for (const section of SECTIONS) {
      const element = document.getElementById(section.id);
      if (element) observer.observe(element);
    }

    /* The moment the reader starts leaving the fold, not once it is gone —
       a tenth of a viewport is "they have started scrolling". */
    const onScroll = () => setShown(window.scrollY > window.innerHeight * 0.1);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });

    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  return (
    <nav
      aria-label="On this page"
      className={`gr-model-rail${shown ? " gr-model-rail--shown" : ""}`}
    >
      <ul>
        {SECTIONS.map((section) => (
          <li key={section.id}>
            <a
              className={`gr-model-rail-link${
                active === section.id ? " gr-model-rail-link--active" : ""
              }`}
              href={`#${section.id}`}
            >
              {section.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
};

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

/** The benchmark bars, grown on arrival: each bar draws from zero to its
 *  score as the section reaches the reader, one beat apart. The width lives
 *  in a custom property so CSS owns the motion; the observer only says
 *  "now", and only once — a chart that redraws on every pass reads as a
 *  toy. */
const BenchmarkBars = ({
  benchmarks,
}: {
  benchmarks: ModelPageData["benchmarks"];
}): ReactElement => {
  const [seen, setSeen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setSeen(true);
          observer.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    observer.observe(root);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      className={`gr-model-bench${seen ? " gr-model-bench--seen" : ""}`}
      ref={rootRef}
    >
      {benchmarks.map((benchmark) => (
        <div className="gr-model-bench-row" key={benchmark.name}>
          <span className="gr-model-bench-name">{benchmark.name}</span>
          {benchmark.bar ? (
            <span className="gr-model-bench-track" aria-hidden>
              <span
                className="gr-model-bench-bar"
                style={{ "--bench-bar": `${benchmark.bar}%` } as CSSProperties}
              />
            </span>
          ) : (
            <span aria-hidden />
          )}
          <span className="gr-model-bench-score">{benchmark.score}</span>
          {benchmark.note ? (
            <span className="gr-model-bench-note">{benchmark.note}</span>
          ) : null}
        </div>
      ))}
    </div>
  );
};

/** The snippets, tabbed the way the docs tab their SDKs — one visible
 *  sample, the others a click away. A single snippet renders plain: a
 *  one-option tab control is a label with extra steps. */
const SnippetTabs = ({
  snippets,
}: {
  snippets: ModelPageData["gettingStarted"]["snippets"];
}): ReactElement => {
  const [current, setCurrent] = useState(snippets[0].label);
  const active =
    snippets.find((snippet) => snippet.label === current) ?? snippets[0];

  if (snippets.length === 1) {
    return (
      <div className="gr-model-snippet">
        <p className="gr-label">{snippets[0].label}</p>
        <CodeBlock code={snippets[0].code} language={snippets[0].language} />
      </div>
    );
  }

  return (
    <div className="gr-model-snippet">
      <Tabs
        label="Code sample language"
        onChange={setCurrent}
        options={snippets.map((snippet) => snippet.label)}
        quiet
        value={current}
      />
      <CodeBlock code={active.code} language={active.language} />
    </div>
  );
};

/** The id as what it is — a parameter for the snippets below, not a
 *  command. No prompt glyph: a `$` dresses it as something to run, and a
 *  reader who takes the costume literally gets `command not found`. */
const ModelId = ({ id }: { id: string }): ReactElement => {
  const [copied, setCopied] = useState(false);
  return (
    <div className="gr-model-id-row">
      <span className="gr-model-id">
        <code>{id}</code>
      </span>
      <button
        className="gr-model-copy"
        type="button"
        onClick={() => {
          void navigator.clipboard.writeText(id).then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
          });
        }}
      >
        {copied ? "Copied" : "Copy ID"}
      </button>
    </div>
  );
};

export const ModelDetailPage = ({
  model,
}: {
  model: ModelPageData;
}): ReactElement => {
  return (
    <Substrate>
      <Nav />

      <Band>
        <Module bleed className="gr-module--model" index={0}>
          <a className="gr-label gr-model-back" href="/inference/">
            &larr; All models
          </a>
          {/* ONE grid for the whole page, so the left column is one column:
              the identity floats at the top of the viewport and the section
              nav holds its foot, the full length of the scroll. */}
          <div className="gr-model-layout">
            <aside className="gr-model-left">
              <div className="gr-model-side">
                {/* The art well. The provider's mark holds it until each
                    model has artwork of its own. */}
                <div className="gr-model-art">
                  {model.icon ? <img alt="" src={model.icon} /> : model.mark}
                </div>
                <dl className="gr-model-facts">
                  {model.facts.map((fact) => (
                    <div className="gr-model-fact" key={fact.label}>
                      <dt className="gr-label">{fact.label}</dt>
                      <dd>{fact.value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
              <ContentsRail />
            </aside>

            <div className="gr-model-main">
              <div className="gr-model-intro" id="overview">
                <h1 className="gr-model-name">{model.name}</h1>
                <p className="gr-lede gr-muted gr-model-lede">
                  {model.oneLiner}
                </p>
                <div className="gr-model-overview">
                  {model.overview.map((paragraph) => (
                    <p className="gr-body" key={paragraph.slice(0, 32)}>
                      {paragraph}
                    </p>
                  ))}
                </div>
                <ModelId id={model.id} />
              </div>

              <div className="gr-model-sections">
                <section className="gr-model-section" id="good-for">
                  <h2 className="gr-model-section-title">
                    What&rsquo;s it good for
                  </h2>
                  <div className="gr-model-good">
                    {model.goodFor.map((item) => (
                      <div className="gr-model-good-row" key={item.title}>
                        {/* PLACEHOLDER — a spot illustration per use, when the
                          art exists. An empty well in the meantime. */}
                        <span aria-hidden className="gr-model-good-art" />
                        <div>
                          <h3 className="gr-heading">{item.title}</h3>
                          <p className="gr-body gr-muted">{item.body}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="gr-model-section" id="benchmarks">
                  <h2 className="gr-model-section-title">Benchmarks</h2>
                  <p className="gr-body gr-muted gr-model-section-lede">
                    {model.benchmarksNote}
                  </p>
                  <BenchmarkBars benchmarks={model.benchmarks} />
                </section>

                <section className="gr-model-section" id="pricing">
                  <h2 className="gr-model-section-title">
                    Pricing &amp; Specs
                  </h2>
                  <p className="gr-body gr-muted gr-model-section-lede">
                    Latency is a choice, not a property of the model —{" "}
                    <a className="gr-link" href="/inference/">
                      pick the service tier
                    </a>{" "}
                    your workload needs.
                  </p>
                  <ModelVitals model={model} />
                  <dl className="gr-model-specs">
                    {model.specs.map((spec) => (
                      <div className="gr-model-spec" key={spec.label}>
                        <dt className="gr-label">{spec.label}</dt>
                        <dd className="gr-body">{spec.value}</dd>
                      </div>
                    ))}
                  </dl>
                </section>

                <section className="gr-model-section" id="getting-started">
                  <h2 className="gr-model-section-title">Getting Started</h2>
                  <p className="gr-body gr-muted gr-model-section-lede">
                    {model.gettingStarted.lede}
                  </p>
                  <div className="gr-model-snippets">
                    <SnippetTabs snippets={model.gettingStarted.snippets} />
                  </div>
                  <p className="gr-body gr-muted">
                    <a className="gr-link" href={model.gettingStarted.docsHref}>
                      {model.gettingStarted.docsLabel}
                    </a>
                  </p>
                </section>

                <section className="gr-model-section" id="hardware">
                  <h2 className="gr-model-section-title">Hardware</h2>
                  <p className="gr-body gr-muted gr-model-section-lede">
                    What {model.name} runs on — our serving fleet first, then
                    what the open weights support anywhere else.
                  </p>
                  <dl className="gr-model-specs">
                    {model.hardware.map((row) => (
                      <div className="gr-model-spec" key={row.name}>
                        <dt className="gr-label">{row.name}</dt>
                        <dd className="gr-body">{row.support}</dd>
                      </div>
                    ))}
                  </dl>
                </section>
              </div>
            </div>
          </div>
        </Module>
      </Band>

      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
