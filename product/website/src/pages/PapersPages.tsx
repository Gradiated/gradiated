import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ReactElement } from "react";

import { Band, Footer, Module, Nav, Substrate } from "../components/design";
import { CONSOLE_BASE_URL } from "../urls";
import { paperCategories, papers } from "../papers";
import type { PaperCategory, PaperGuide } from "../papers";
import "../styles/index.css";

const consoleLaunchUrl = (
  slug: string,
  base: string,
  dataset: string,
): string => {
  const params = new URLSearchParams({
    template: `papers/${slug}`,
    base,
    dataset,
  });
  return `${CONSOLE_BASE_URL}/run?${params.toString()}`;
};

const cliCommandFor = (slug: string, base: string, dataset: string): string =>
  `grad run papers/${slug} --base ${base} --dataset ${dataset} --wait`;

const agentPromptFor = (
  paper: PaperGuide,
  base: string,
  dataset: string,
): string =>
  [
    `Reproduce "${paper.title}" (arXiv:${paper.arxivId}) using the Gradiated CLI and SDK.`,
    "",
    `Paper guide: https://gradiated.com/papers/${paper.slug}/`,
    "Training docs: https://gradiated.com/docs/training.md",
    "",
    "Steps:",
    `1. Run \`grad init papers/${paper.slug}\` to scaffold the template locally.`,
    `2. Preview dataset coverage and cost with \`grad run papers/${paper.slug} --base ${base} --dataset ${dataset} --dry-run --json\`.`,
    "3. Run the reproduction on Gradiated Cloud (using GRADIATED_API_KEY from env) or adapt the dataset path to my repository's data.",
    "4. Report the eval metrics and exported artifact ID.",
  ].join("\n");

const readmeBadgeFor = (paper: PaperGuide): string => {
  const url = consoleLaunchUrl(
    paper.slug,
    paper.models[0].id,
    paper.datasets[0].id,
  );
  return `[![Run on Gradiated](https://gradiated.com/badge/run.svg)](${url})`;
};

const useCopyState = () => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const copy = (key: string, text: string) => {
    void navigator.clipboard
      .writeText(text)
      .then(() => setCopiedKey(key))
      .catch(() => setCopiedKey(null));
    window.setTimeout(() => setCopiedKey(null), 1600);
  };
  return { copiedKey, copy };
};

/* ---------------------------------------------------------------------------
   /papers/ — 50-Paper Reproducible Tutorials Hub
   --------------------------------------------------------------------------- */

export const PapersIndexPage = (): ReactElement => {
  const [category, setCategory] = useState<PaperCategory | "All">("All");
  const [modeFilter, setModeFilter] = useState<
    "All" | "Managed recipe" | "Custom loop"
  >("All");
  const [query, setQuery] = useState("");
  const { copiedKey, copy } = useCopyState();

  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of papers) {
      counts.set(p.category, (counts.get(p.category) ?? 0) + 1);
    }
    return counts;
  }, []);

  const medianLoc = useMemo(() => {
    const sorted = [...papers.map((p) => p.linesOfCode)].sort((a, b) => a - b);
    return sorted[Math.floor(sorted.length / 2)] ?? 30;
  }, []);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return papers.filter((p) => {
      if (category !== "All" && p.category !== category) return false;
      if (modeFilter !== "All" && p.mode !== modeFilter) return false;
      if (!q) return true;
      return (
        p.title.toLowerCase().includes(q) ||
        p.shortTitle.toLowerCase().includes(q) ||
        p.slug.toLowerCase().includes(q) ||
        p.authors.toLowerCase().includes(q) ||
        p.arxivId.toLowerCase().includes(q) ||
        p.oneLiner.toLowerCase().includes(q) ||
        p.category.toLowerCase().includes(q) ||
        p.primitives.some((pr) => pr.label.toLowerCase().includes(q))
      );
    });
  }, [category, modeFilter, query]);

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module className="gr-module--top" index={0}>
          <div className="gr-papers-wrap">
            <header className="gr-papers-head">
              <div className="gr-papers-kicker">
                {papers.length} reproducible tutorials · Public datasets ·
                Median {medianLoc} lines of grad
              </div>
              <h1 className="gr-papers-title">Paper reproductions</h1>
              <p className="gr-papers-lede">
                Interactive, walkthrough-first implementations of{" "}
                {papers.length} landmark post-training papers. Every tutorial
                breaks down why the paper mattered, walks through the core math
                step by step, and launches on public data in one click or one
                CLI command.
              </p>

              <div className="gr-papers-cli-bar">
                <div className="gr-papers-cli-line">
                  <span aria-hidden="true" className="gr-papers-prompt">
                    $
                  </span>
                  <code>
                    brew install gradiated/tap/grad &amp;&amp; grad run
                    papers/routellm --wait
                  </code>
                </div>
                <button
                  className="gr-papers-btn-ghost"
                  onClick={() =>
                    copy(
                      "hero-cli",
                      "brew install gradiated/tap/grad && grad run papers/routellm --wait",
                    )
                  }
                  type="button"
                >
                  {copiedKey === "hero-cli" ? "Copied" : "Copy"}
                </button>
              </div>
            </header>

            <div className="gr-papers-toolbar">
              <input
                aria-label="Search papers by title, method, arXiv ID, or primitive"
                className="gr-papers-search"
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search 50 papers (e.g. GRPO, SimPO, SDFT, Cartridges, 2503.14476)…"
                type="search"
                value={query}
              />

              <div
                aria-label="Filter by implementation mode"
                className="gr-doc-seg"
                role="tablist"
              >
                {(["All", "Managed recipe", "Custom loop"] as const).map(
                  (m) => (
                    <button
                      key={m}
                      aria-selected={modeFilter === m}
                      className="gr-doc-seg-btn"
                      data-active={modeFilter === m ? "true" : undefined}
                      onClick={() => setModeFilter(m)}
                      role="tab"
                      type="button"
                    >
                      {m}
                    </button>
                  ),
                )}
              </div>
            </div>

            <div
              aria-label="Filter papers by category"
              className="gr-papers-filters"
              role="tablist"
            >
              <button
                aria-selected={category === "All"}
                className="gr-papers-filter"
                data-active={category === "All" ? "true" : undefined}
                onClick={() => setCategory("All")}
                role="tab"
                type="button"
              >
                All ({papers.length})
              </button>
              {paperCategories.map((item) => (
                <button
                  key={item}
                  aria-selected={category === item}
                  className="gr-papers-filter"
                  data-active={category === item ? "true" : undefined}
                  onClick={() => setCategory(item)}
                  role="tab"
                  type="button"
                >
                  {item} ({categoryCounts.get(item) ?? 0})
                </button>
              ))}
            </div>

            {visible.length === 0 ? (
              <div className="gr-papers-empty">
                <p>No papers match &ldquo;{query}&rdquo;.</p>
                <button
                  className="gr-papers-btn-secondary"
                  onClick={() => {
                    setCategory("All");
                    setModeFilter("All");
                    setQuery("");
                  }}
                  type="button"
                >
                  Reset filters
                </button>
              </div>
            ) : (
              <div className="gr-papers-grid">
                {visible.map((paper) => {
                  const defaultModel = paper.models[0];
                  const defaultDataset = paper.datasets[0];
                  const quickCmd = `grad run papers/${paper.slug} --wait`;
                  const launchHref = consoleLaunchUrl(
                    paper.slug,
                    defaultModel.id,
                    defaultDataset.id,
                  );

                  return (
                    <article key={paper.slug} className="gr-paper-card">
                      <div className="gr-paper-card-meta">
                        <span className="gr-paper-cat">{paper.category}</span>
                        <span className="gr-paper-arxiv">
                          arXiv:{paper.arxivId} · {paper.year}
                        </span>
                      </div>

                      <h2 className="gr-paper-card-title">
                        <Link to={`/papers/${paper.slug}/`}>{paper.title}</Link>
                      </h2>

                      <p className="gr-paper-card-desc">{paper.oneLiner}</p>

                      <div className="gr-paper-specs">
                        <div>
                          <span className="gr-paper-spec-k">Footprint</span>
                          <span className="gr-paper-spec-v">
                            {paper.linesOfCode} lines · {paper.smoothness.rating}
                          </span>
                        </div>
                        <div>
                          <span className="gr-paper-spec-k">Compute</span>
                          <span className="gr-paper-spec-v">
                            {defaultModel.compute} · {defaultModel.duration}
                          </span>
                        </div>
                        <div>
                          <span className="gr-paper-spec-k">Est. cost</span>
                          <span className="gr-paper-spec-v">
                            {defaultModel.estCost}
                          </span>
                        </div>
                      </div>

                      <div className="gr-paper-card-cmd">
                        <code>$ {quickCmd}</code>
                        <button
                          aria-label={`Copy CLI command for ${paper.shortTitle}`}
                          className="gr-paper-cmd-copy"
                          onClick={() => copy(paper.slug, quickCmd)}
                          type="button"
                        >
                          {copiedKey === paper.slug ? "Copied" : "Copy"}
                        </button>
                      </div>

                      <div className="gr-paper-card-actions">
                        <a
                          className="gr-papers-btn-primary"
                          href={launchHref}
                          rel="noreferrer"
                          target="_blank"
                        >
                          Run on Gradiated →
                        </a>
                        <Link
                          className="gr-papers-btn-secondary"
                          to={`/papers/${paper.slug}/`}
                        >
                          Read tutorial
                        </Link>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}

            <section className="gr-papers-author-strip">
              <div>
                <div className="gr-papers-kicker">For paper authors</div>
                <h2>Ship a one-click &ldquo;Run on Gradiated&rdquo; button</h2>
                <p>
                  Drop a <code>paper.yaml</code> and a 20–50 line{" "}
                  <code>grad</code> script into your repository so any
                  researcher can reproduce your paper on public data in one
                  click — zero GPU cluster setup.
                </p>
              </div>
              <div className="gr-papers-author-actions">
                <Link className="gr-papers-btn-secondary" to="/docs/training/">
                  Read training docs
                </Link>
                <Link
                  className="gr-papers-btn-secondary"
                  to="/docs/training/custom-loops/"
                >
                  Custom loops guide
                </Link>
              </div>
            </section>
          </div>
        </Module>
      </Band>

      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};

/* ---------------------------------------------------------------------------
   /papers/<slug>/ — Engaging Walkthrough Tutorial + One-Click Launch
   --------------------------------------------------------------------------- */

export const PaperDetailPage = ({
  paper,
}: {
  paper: PaperGuide;
}): ReactElement => {
  const [modelId, setModelId] = useState(paper.models[0].id);
  const [datasetId, setDatasetId] = useState(paper.datasets[0].id);
  const [codeTab, setCodeTab] = useState<"code" | "yaml" | "dryrun">("code");
  const { copiedKey, copy } = useCopyState();

  const selectedModel =
    paper.models.find((m) => m.id === modelId) ?? paper.models[0];
  const selectedDataset =
    paper.datasets.find((d) => d.id === datasetId) ?? paper.datasets[0];

  const launchHref = consoleLaunchUrl(paper.slug, modelId, datasetId);
  const cliCmd = cliCommandFor(paper.slug, modelId, datasetId);
  const initCmd = `grad init papers/${paper.slug}`;

  const related = useMemo(() => {
    const sameCategory = papers.filter(
      (p) => p.slug !== paper.slug && p.category === paper.category,
    );
    const others = papers.filter(
      (p) => p.slug !== paper.slug && p.category !== paper.category,
    );
    return [...sameCategory, ...others].slice(0, 3);
  }, [paper.category, paper.slug]);

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module className="gr-module--top" index={0}>
          <article className="gr-papers-wrap gr-papers-detail">
            <nav aria-label="Breadcrumb" className="gr-paper-crumb">
              <Link to="/papers/">← All {papers.length} paper reproductions</Link>
              <span>·</span>
              <span>{paper.category}</span>
              <span>·</span>
              <a href={paper.arxivUrl} rel="noreferrer" target="_blank">
                arXiv:{paper.arxivId} ↗
              </a>
            </nav>

            <header className="gr-paper-hero">
              <h1 className="gr-papers-title">{paper.title}</h1>
              <p className="gr-papers-lede">{paper.oneLiner}</p>
              <div className="gr-paper-byline">
                <span>
                  {paper.authors}, {paper.year}
                </span>
                <span>·</span>
                <span>{paper.mode}</span>
                <span>·</span>
                <span>
                  <strong>{paper.linesOfCode} lines</strong> in{" "}
                  <code>grad</code> (vs. {paper.typicalBaselineLoc})
                </span>
              </div>
            </header>

            {/* Vercel-Deploy-style One-Click Launch Panel */}
            <section
              aria-label="One-click launch configurator"
              className="gr-launch-panel"
            >
              <div className="gr-launch-head">
                <span className="gr-papers-kicker">
                  One-click reproduction · Pre-configured public data
                </span>
                <span className="gr-launch-estimate">
                  {selectedModel.compute} · {selectedModel.duration} ·{" "}
                  <strong>{selectedModel.estCost}</strong>
                </span>
              </div>

              <div className="gr-launch-controls">
                <label className="gr-launch-field">
                  <span>Base model</span>
                  <select
                    onChange={(e) => setModelId(e.target.value)}
                    value={modelId}
                  >
                    {paper.models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="gr-launch-field">
                  <span>Public dataset</span>
                  <select
                    onChange={(e) => setDatasetId(e.target.value)}
                    value={datasetId}
                  >
                    {paper.datasets.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.label} ({d.examples})
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="gr-launch-actions">
                <a
                  className="gr-papers-btn-primary gr-papers-btn-lg"
                  href={launchHref}
                  rel="noreferrer"
                  target="_blank"
                >
                  Run on Gradiated →
                </a>
                <button
                  className="gr-papers-btn-secondary"
                  onClick={() => copy("cli", cliCmd)}
                  type="button"
                >
                  {copiedKey === "cli" ? "Copied CLI" : "Copy CLI command"}
                </button>
                <button
                  className="gr-papers-btn-secondary"
                  onClick={() =>
                    copy(
                      "prompt",
                      agentPromptFor(paper, modelId, datasetId),
                    )
                  }
                  type="button"
                >
                  {copiedKey === "prompt"
                    ? "Copied prompt"
                    : "Copy coding-agent prompt"}
                </button>
                <button
                  className="gr-papers-btn-ghost"
                  onClick={() => copy("badge", readmeBadgeFor(paper))}
                  type="button"
                >
                  {copiedKey === "badge" ? "Copied badge" : "Copy README badge"}
                </button>
              </div>

              <div className="gr-launch-cmd">
                <code>$ {cliCmd}</code>
              </div>
              <div className="gr-launch-sub">
                Want to hack on the loss or swap in your own dataset first? Run{" "}
                <code>{initCmd}</code> to pull the {paper.linesOfCode}-line
                template locally, then preview cost at $0 with{" "}
                <code>--dry-run</code>.
              </div>
            </section>

            {/* The Story & Core Insight */}
            <section className="gr-paper-section">
              <h2>The problem this paper solved</h2>
              <p className="gr-paper-copy">{paper.story}</p>

              <aside className="gr-doc-callout gr-doc-callout--tip">
                <div className="gr-doc-callout-label">Core idea</div>
                <div className="gr-doc-callout-body">
                  <p>{paper.insight}</p>
                </div>
              </aside>
            </section>

            {/* Step-by-Step Walkthrough */}
            <section className="gr-paper-section">
              <h2>How it works in grad (step by step)</h2>
              <p className="gr-paper-copy">{paper.whyGrad}</p>

              <ol className="gr-paper-steps">
                {paper.walkthrough.map((step, index) => (
                  <li key={step.title} className="gr-paper-step">
                    <div className="gr-paper-step-head">
                      <span className="gr-paper-step-num">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <strong>{step.title}</strong>
                      <code className="gr-paper-step-call">
                        {step.gradCall}
                      </code>
                    </div>
                    <p>{step.explanation}</p>
                  </li>
                ))}
              </ol>

              <div className="gr-paper-smoothness">
                <span className="gr-paper-smooth-badge">
                  Implementation smoothness · {paper.smoothness.rating}
                </span>
                <p>{paper.smoothness.verdict}</p>
              </div>

              <div className="gr-doc-chips">
                {paper.primitives.map((prim) => (
                  <Link
                    key={prim.label}
                    className="gr-paper-prim-link"
                    to={prim.href}
                  >
                    {prim.label} →
                  </Link>
                ))}
              </div>
            </section>

            {/* Complete Implementation / paper.yaml / Dry-run Preview */}
            <section className="gr-paper-section">
              <div className="gr-paper-code-head">
                <h2>Complete implementation</h2>
                <div className="gr-doc-seg" role="tablist">
                  <button
                    aria-selected={codeTab === "code"}
                    className="gr-doc-seg-btn"
                    data-active={codeTab === "code" ? "true" : undefined}
                    onClick={() => setCodeTab("code")}
                    role="tab"
                    type="button"
                  >
                    {paper.codeLabel}
                  </button>
                  <button
                    aria-selected={codeTab === "yaml"}
                    className="gr-doc-seg-btn"
                    data-active={codeTab === "yaml" ? "true" : undefined}
                    onClick={() => setCodeTab("yaml")}
                    role="tab"
                    type="button"
                  >
                    paper.yaml
                  </button>
                  <button
                    aria-selected={codeTab === "dryrun"}
                    className="gr-doc-seg-btn"
                    data-active={codeTab === "dryrun" ? "true" : undefined}
                    onClick={() => setCodeTab("dryrun")}
                    role="tab"
                    type="button"
                  >
                    --dry-run output
                  </button>
                </div>
              </div>

              <div className="gr-paper-code-shell">
                <button
                  className="gr-doc-copy gr-doc-copy--visible"
                  onClick={() =>
                    copy(
                      "source",
                      codeTab === "code"
                        ? paper.code
                        : codeTab === "yaml"
                          ? paper.paperYaml
                          : paper.dryRunOutput,
                    )
                  }
                  type="button"
                >
                  {copiedKey === "source" ? "Copied" : "Copy"}
                </button>
                <pre>
                  <code>
                    {codeTab === "code"
                      ? paper.code
                      : codeTab === "yaml"
                        ? paper.paperYaml
                        : paper.dryRunOutput}
                  </code>
                </pre>
              </div>
            </section>

            {/* Practitioner Pitfalls */}
            <section className="gr-paper-section">
              <h2>Practitioner notes &amp; pitfalls</h2>
              <ul className="gr-paper-bullets">
                {paper.gotchas.map((tip) => (
                  <li key={tip}>{tip}</li>
                ))}
              </ul>
            </section>

            {/* Benchmarks & Reference Targets */}
            <section className="gr-paper-section">
              <h2>Reference targets &amp; template setup</h2>
              <p className="gr-paper-note">
                Dataset: <strong>{selectedDataset.label}</strong> (
                {selectedDataset.source} · {selectedDataset.examples}). Numbers
                below separate paper-reported reference claims from this
                template&apos;s default run configuration.
              </p>
              <div className="gr-doc-tablewrap">
                <table className="gr-paper-table">
                  <thead>
                    <tr>
                      <th>Benchmark</th>
                      <th>Paper-reported reference</th>
                      <th>Default template setup</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paper.benchmarks.map((row) => (
                      <tr key={row.benchmark}>
                        <td>
                          <strong>{row.benchmark}</strong>
                        </td>
                        <td>{row.paperReported}</td>
                        <td>{row.templateSetup}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Citation */}
            <section className="gr-paper-section">
              <div className="gr-paper-code-head">
                <h2>Citation</h2>
                <button
                  className="gr-papers-btn-ghost"
                  onClick={() => copy("bib", paper.bibtex)}
                  type="button"
                >
                  {copiedKey === "bib" ? "Copied BibTeX" : "Copy BibTeX"}
                </button>
              </div>
              <div className="gr-paper-code-shell">
                <pre>
                  <code>{paper.bibtex}</code>
                </pre>
              </div>
            </section>

            {/* Related Paper Reproductions */}
            <section className="gr-paper-section">
              <h2>Related paper reproductions</h2>
              <div className="gr-paper-more">
                {related.map((other) => (
                  <Link
                    key={other.slug}
                    className="gr-paper-more-link"
                    to={`/papers/${other.slug}/`}
                  >
                    <small>
                      {other.category} · {other.linesOfCode} lines
                    </small>
                    <strong>{other.title}</strong>
                  </Link>
                ))}
              </div>
            </section>
          </article>
        </Module>
      </Band>

      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
