import { useRef, useState } from "react";
import type { ReactElement } from "react";
import {
  Arrow,
  Band,
  Logo,
  CodeBlock,
  Columns,
  Footer,
  Module,
  Nav,
  Reveal,
  Part,
  Spec,
  Storybook,
  Substrate,
  Tabs,
  WaveField,
  ThemeGallery,
} from "../components/design";
import type { Group } from "../components/design";
import "../styles/index.css";

/** A ramp chip that hands over its hex on click. The literal lives in the
 * stylesheet, so the value is read off the painted chip itself — no second
 * copy of the palette to fall out of date. */
const ColourChip = ({
  prefix,
  step,
}: {
  prefix: string;
  step: string;
}): ReactElement => {
  const chipRef = useRef<HTMLSpanElement>(null);
  const [copied, setCopied] = useState(false);

  const copy = async (): Promise<void> => {
    const chip = chipRef.current;
    if (!chip) return;
    const parts = getComputedStyle(chip).backgroundColor.match(/[\d.]+/g);
    if (!parts) return;
    const hex =
      "#" +
      parts
        .slice(0, 3)
        .map((v) => Math.round(Number(v)).toString(16).padStart(2, "0"))
        .join("")
        .toUpperCase();
    try {
      await navigator.clipboard.writeText(hex);
    } catch {
      return; // clipboard blocked: no false "copied"
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };

  return (
    <li>
      <button
        aria-label={`Copy ${prefix}-${step} hex`}
        className="gr-chip-copy"
        onClick={copy}
        type="button"
      >
        <span
          aria-hidden
          className="gr-chip"
          ref={chipRef}
          style={{ background: `var(--color-${prefix}-${step})` }}
        />
        <span className="gr-chip-label">{copied ? "copied" : step}</span>
      </button>
    </li>
  );
};

/** The ramp: every colour literal in the system, by family. */
const families = [
  {
    name: "Neutral · Light",
    prefix: "light",
    steps: ["000", "100", "200", "300", "400"],
  },
  {
    name: "Neutral · Dark",
    prefix: "dark",
    steps: ["000", "050", "100", "200", "300", "400"],
  },
  { name: "Taupe", prefix: "taupe", steps: ["200", "300", "400", "500"] },
  { name: "Kiln", prefix: "kiln", steps: ["300", "500", "600", "700"] },
  {
    name: "Grove",
    prefix: "grove",
    steps: ["400", "500", "600", "700", "800"],
  },
  { name: "Plum", prefix: "plum", steps: ["400", "500", "700", "800"] },
  { name: "Aegean", prefix: "aegean", steps: ["400", "500", "600", "700"] },
];

/* One per theme, plus two the palette keeps without a taker. */
const gradients = [
  { token: "--gradient-terrace", name: "Terrace", themes: ["taupe"] },
  { token: "--gradient-ember", name: "Ember", themes: ["grove"] },
  { token: "--gradient-tide", name: "Tide", themes: ["light"] },
  { token: "--gradient-shallows", name: "Shallows", themes: ["dark"] },
  { token: "--gradient-dawn", name: "Dawn", themes: [] },
  { token: "--gradient-morning", name: "Morning", themes: [] },
];

/* The rail, in two runs.

   Primitives are what the system is made OF — the mark, the type, the colour,
   the columns, the motion. Components are what is made FROM them. Colour
   carries the gradients and the themes as parts rather than as siblings,
   because a gradient and a theme are not peers of the palette: they are the
   palette used two particular ways.

   Ordered by dependency, not alphabet: nothing here should need something
   listed below it in order to make sense. */
const GROUPS: Group[] = [
  {
    label: "Primitives",
    sections: [
      { id: "logo", label: "Logo" },
      { id: "typography", label: "Typography" },
      { id: "colour", label: "Colour" },
      { id: "columns", label: "Columns" },
    ],
  },
  {
    label: "Components",
    sections: [
      { id: "buttons", label: "Buttons" },
      { id: "links", label: "Text links" },
      { id: "tabs", label: "Tabs" },
      { id: "fields", label: "Fields" },
      { id: "table", label: "Table" },
      { id: "code", label: "Code" },
      { id: "badges", label: "Badges" },
      { id: "navigation", label: "Navigation" },
    ],
  },
];

const typefaces = [
  {
    label: "Titles",
    name: "Instrument Sans",
    family: "var(--font-title)",
    body: "Geometric structure with open letterforms. Gives headlines presence without heaviness; humanist touches keep it approachable.",
  },
  {
    label: "Body",
    name: "Barlow",
    family: "var(--font-body)",
    body: "A slightly narrow, low-contrast grotesk balancing warmth and clarity. Open apertures keep it readable at small sizes.",
  },
  {
    label: "Code",
    name: "JetBrains Mono",
    family: "var(--font-code)",
    body: "Tall x-height improves reading. Ligature support reduces eye strain, and consistent widths ensure precise alignment.",
  },
];

export const StylePage = (): ReactElement => (
  <Substrate>
    <Nav />

    {/* The fold: a statement, scrolling normally. */}
    <Band>
      <Module bleed height="viewport" index={0}>
        <WaveField />
        <Columns count={2}>
          <div>
            <Reveal as="h1" by="word" className="gr-hero">
              Everything is considered
            </Reveal>
          </div>
          <div>
            <Reveal as="p" by="line" className="gr-lede gr-hero-aside gr-muted">
              Socrates tested claims by questioning their assumptions. We apply
              the same standard to the brand. Every word, line, colour, and
              interaction should have a reason to exist.
            </Reveal>
          </div>
        </Columns>
      </Module>
    </Band>

    {/* Everything after the fold is a tool, so it behaves like one. */}
    <Storybook groups={GROUPS}>
      <Spec
        id="logo"
        title="Logo"
        notes="Inline SVG, painted with currentColor. Three crops from one file: mark, wordmark, full lockup."
        code={`<Logo />            {/* lockup */}\n<Logo mark />       {/* mark, square */}\n<Logo wordmark />   {/* wordmark, cropped */}`}
      >
        <div
          style={{
            alignItems: "flex-start",
            color: "var(--color-text)",
            display: "grid",
            gap: "calc(1.5 * var(--u))",
          }}
        >
          <div>
            <p className="gr-label">Lockup</p>
            <Logo height={32} />
          </div>
          <div>
            <p className="gr-label">Mark</p>
            <Logo height={40} mark />
          </div>
          <div>
            <p className="gr-label">Wordmark</p>
            <Logo height={26} wordmark />
          </div>
        </div>
      </Spec>

      <Spec
        id="typography"
        title="Typography"
        notes="Instrument Sans for titles, Barlow for body and caps, JetBrains Mono for code. Sizes are rem, so they follow the reader's text size."
        code={`<h1 className="gr-hero">…\n<h2 className="gr-section-title">…\n<h3 className="gr-heading">…\n<p className="gr-lede">…\n<p className="gr-body">…\n<p className="gr-label">…`}
      >
        <Columns count={3}>
          {typefaces.map((face) => (
            <div key={face.name}>
              <p className="gr-label">{face.label}</p>
              <p
                style={{
                  fontFamily: face.family,
                  fontSize: "21px",
                  marginBlock: "calc(0.5 * var(--u))",
                }}
              >
                {face.name}
              </p>
              <p className="gr-body gr-muted">{face.body}</p>
            </div>
          ))}
        </Columns>
      </Spec>

      <Spec
        id="colour"
        title="Colour"
        notes="The literals, the pairs built from them, and the themes that bind both to jobs. Components reference themes, never the values below."
      >
        <Part
          title="Ramp"
          notes="Every colour literal, by family. Steps follow Tailwind's 50-950 scale; gaps mean no colour was designed there."
          code={`var(--color-grove-600)   /* that colour on every theme */\nbg-grove-600             /* the same, as a utility */`}
        >
          <div className="gr-swatch-families">
            {families.map((family) => (
              <div key={family.name}>
                <p className="gr-label">{family.name}</p>
                <ul className="gr-chips">
                  {family.steps.map((step) => (
                    <ColourChip key={step} prefix={family.prefix} step={step} />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Part>

        <Part
          title="Gradients"
          notes="Two-stop pairs, declared with their angle. One per theme, plus any the palette holds without a taker."
          code={`background: var(--gradient-terrace);`}
        >
          <Columns count={3}>
            {gradients.map((gradient) => (
              <div key={gradient.token}>
                <div
                  aria-hidden
                  style={{
                    background: `var(${gradient.token})`,
                    height: "calc(6 * var(--u))",
                    marginBlockEnd: "calc(0.5 * var(--u))",
                  }}
                />
                <p className="gr-gradient-meta">
                  <span className="gr-label">{gradient.name}</span>
                  {/* Four of the six carry a theme; Terrace and Morning are
                      kept without one — a pairing is still a designed pairing
                      with nothing currently using it — and the badge says so
                      rather than sitting empty. Listed last for that reason. */}
                  <span className="gr-gradient-seen">
                    {gradient.themes.length > 0 ? "as seen in" : "unassigned"}
                  </span>
                  {gradient.themes.map((theme) => (
                    <span className="gr-badge" key={theme}>
                      {theme}
                    </span>
                  ))}
                </p>
              </div>
            ))}
          </Columns>
        </Part>

        <Part
          title="Themes"
          notes="A ground, its surface, a rule, an ink pair, buttons and a gradient. Put data-theme on the root for the page or on a Module for one section."
          code={`<div className="gr-root" data-theme="grove-1">   {/* the page */}\n<Module theme="grove-1">                        {/* one section */}`}
        >
          <ThemeGallery />
        </Part>
      </Spec>

      <Spec
        id="columns"
        title="Columns"
        notes="Flush to the band, one gutter measure at any count. The unit is derived to fit, so alignment holds at every width."
        code={`<Columns count={3}>…</Columns>\n\n--u          <= 24px, snapped to whole pixels\n--module-u   48 / 36 / 16 by tier\n--module-w   --module-u x --u`}
      >
        <div className="gr-rows">
          {([2, 3, 4] as const).map((count) => (
            <div key={count}>
              <p className="gr-label">{count} column</p>
              <Columns count={count}>
                {Array.from({ length: count }, (_, i) => (
                  <div
                    aria-hidden
                    key={i}
                    style={{
                      background: "var(--color-rule)",
                      height: "calc(2 * var(--u))",
                    }}
                  />
                ))}
              </Columns>
            </div>
          ))}
        </div>
      </Spec>

      <Spec
        id="buttons"
        title="Buttons"
        notes="Main and secondary follow the theme. Ghost is transparent until hover, where it resolves to secondary."
        code={`<a className="gr-button gr-button--main">Get API key</a>\n<a className="gr-button gr-button--secondary">View docs<Arrow /></a>\n<a className="gr-button gr-button--ghost">Book a call</a>`}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--u)" }}>
          <a className="gr-button gr-button--main" href="#buttons">
            Get API key
          </a>
          <a className="gr-button gr-button--secondary" href="#buttons">
            View docs
            <Arrow />
          </a>
          <a className="gr-button gr-button--ghost" href="#buttons">
            Book a call
          </a>
        </div>
      </Spec>

      <Spec
        id="links"
        title="Text links"
        notes="A rule draws across as the chevron extends into an arrow. Pass an Arrow child only when the link is a single onward action."
        code={`<a className="gr-link" href="/docs">\n  Read the docs\n  <Arrow />\n</a>`}
      >
        <div
          style={{ display: "grid", gap: "var(--u)", justifyItems: "start" }}
        >
          <a className="gr-link" href="#links">
            this is a new link
            <Arrow />
          </a>
          <a className="gr-link" href="#links">
            Read the documentation
            <Arrow />
          </a>
        </div>
      </Spec>

      <Spec
        id="tabs"
        title="Tabs"
        notes="One track, one indicator that travels. Cells are equal width; arrow keys move between them."
        code={`<Tabs\n  label="Plan"\n  options={["Overview", "Pricing", "Limits"]}\n/>`}
      >
        <Tabs label="Plan" options={["Overview", "Pricing", "Limits"]} />
      </Spec>

      <Spec
        id="fields"
        title="Fields"
        notes="Invalid state uses a heavier border and a message, never colour alone. Every field has a visible focus ring."
        code={`<label className="gr-field">\n  <span className="gr-label">API key name</span>\n  <input className="gr-input" placeholder="production" />\n  <span className="gr-field-hint">Shown in your dashboard.</span>\n</label>`}
      >
        <div
          style={{
            display: "grid",
            gap: "var(--u)",
            maxWidth: "calc(18 * var(--u))",
          }}
        >
          <label className="gr-field">
            <span className="gr-label">API key name</span>
            <input
              className="gr-input"
              defaultValue=""
              placeholder="production"
            />
            <span className="gr-field-hint">Shown in your dashboard.</span>
          </label>
          <label className="gr-field">
            <span className="gr-label">Rate limit</span>
            <input aria-invalid className="gr-input" defaultValue="-1" />
            <span className="gr-field-error">Must be a positive number.</span>
          </label>
          <label className="gr-field">
            <span className="gr-label">Notes</span>
            <textarea className="gr-textarea" placeholder="Optional" />
          </label>
        </div>
      </Spec>

      <Spec
        id="table"
        title="Table"
        notes="Bounded box, tinted header, mono figures with their unit. Row names sit a step heavier than the data."
        code={`<div className="gr-table-wrap">\n  <table className="gr-table">\n    <thead><tr><th>Model</th><th>Input</th></tr></thead>\n    <tbody>\n      <tr>\n        <td><span className="gr-cell-name">GLM 5.2</span></td>\n        <td data-numeric>$0.14<span className="gr-cell-unit">/ 1M</span></td>\n      </tr>\n    </tbody>\n  </table>\n</div>`}
      >
        <div className="gr-table-wrap">
          <table className="gr-table">
            <colgroup>
              <col style={{ width: "30%" }} />
              <col style={{ width: "18%" }} />
              <col style={{ width: "20%" }} />
              <col style={{ width: "18%" }} />
              <col style={{ width: "14%" }} />
            </colgroup>
            <thead>
              <tr>
                <th scope="col">Model</th>
                <th scope="col">Input</th>
                <th scope="col">Cached input</th>
                <th scope="col">Output</th>
                <th scope="col">Context</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["GLM 5.2", "$0.14", "$0.03", "$0.42", "128K"],
                ["Kimi K2", "$0.19", "$0.05", "$0.58", "200K"],
                ["Qwen3 Coder", "$0.31", "$0.08", "$0.94", "256K"],
              ].map((row) => (
                <tr key={row[0]}>
                  <td>
                    <span className="gr-cell-name">{row[0]}</span>
                  </td>
                  {row.slice(1, 4).map((value, i) => (
                    <td data-numeric key={i}>
                      {value}
                      <span className="gr-cell-unit">/ 1M</span>
                    </td>
                  ))}
                  <td data-numeric>{row[4]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Spec>

      <Spec
        id="code"
        title="Code"
        notes="Dark on every theme. Copy control appears on hover and confirms in place."
        code={`<pre className="gr-codeblock"><code>…</code></pre>\n<code className="gr-code-inline">POST /v1/runs</code>`}
      >
        <CodeBlock
          code={`// create a run\nconst run = await client.runs.create({\n  model: "glm-5.2",\n  budget: 2.50,\n});`}
        />
        <p
          className="gr-body gr-muted"
          style={{ marginBlockStart: "var(--u)" }}
        >
          Inline, it reads as{" "}
          <code className="gr-code-inline">POST /v1/runs</code> within a
          sentence.
        </p>
      </Spec>

      <Spec
        id="badges"
        title="Badges"
        notes="Outlined, never filled, so a badge cannot be mistaken for a button."
        code={`<span className="gr-badge">Beta</span>\n<span className="gr-badge gr-badge--emphasis">Flex tier</span>`}
      >
        <div style={{ display: "flex", gap: "calc(0.5 * var(--u))" }}>
          <span className="gr-badge">Beta</span>
          <span className="gr-badge">Deprecated</span>
          <span className="gr-badge gr-badge--emphasis">Flex tier</span>
        </div>
      </Spec>

      <Spec
        id="navigation"
        title="Navigation"
        notes="One shared panel that glides and resizes between items. Below wide it becomes a full-screen sheet."
        code={`<Nav />`}
      >
        <p className="gr-body gr-muted">
          Live at the top of this page — hover Product or Library.
        </p>
      </Spec>
    </Storybook>

    <Band>
      <Footer index={1} />
    </Band>
  </Substrate>
);
