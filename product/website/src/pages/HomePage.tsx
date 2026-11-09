import { CONSOLE_BASE_URL } from "../urls";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { CSSProperties, ReactElement, ReactNode } from "react";
import {
  Arrow,
  Band,
  Footer,
  HomeFlow,
  InferenceFlow,
  LoopSection,
  ModelMarquee,
  Module,
  Nav,
  Reveal,
  StoryRow,
  Substrate,
  ValueFold,
} from "../components/design";
import { libraryStories } from "../library-stories";
import "../styles/index.css";

/**
 * The homepage.
 *
 * The fold is the claim plus the two products it resolves into: a centred
 * statement, the two ways in, and the product tabs — inference open by
 * default with a base-URL code example, automated RL beside it. The tabs sit
 * on the hero's beam rather than a panel of their own, so the fold stays one
 * surface.
 *
 * Below: the model marquee (the catalogue as evidence), the value fold
 * streaming the proposition, the loop fold showing the machine, a one-line
 * "One more thing…" beat reusing the value fold's reveal, and the chip fold
 * landing it. All full-bleed and self-measuring, so they sit outside the
 * Band/Module pair. The news row keeps the Library's three latest pieces on
 * the same catalogue as the index and the nav.
 */

export const HomePage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      {/* RELAUNCH: the hero is the statement, left-aligned on the page
          ground, with the argument directly beneath it — no beams, no
          centred stage. */}
      <Module bleed className="gr-module--fold" index={0}>
        <div className="gr-fold-left">
          <h1 className="gr-display gr-home-title">
            <Reveal by="word">Drop your reliance on frontier models</Reveal>
          </h1>
          <div className="gr-home-actions">
            <a className="gr-button gr-button--main" href={CONSOLE_BASE_URL}>
              Get API Key <Arrow />
            </a>
            <Link className="gr-button gr-button--secondary" to="/docs/">
              View Docs <Arrow />
            </Link>
          </div>
        </div>
      </Module>
    </Band>

    {/* The second fold: the claim resolves into the two products, and the
        marquee closes the section — the catalogue as evidence. */}
    <Band>
      <Module className="gr-products-module" index={1}>
        <ProductsEntrance>
          <HomeProducts />
          <div
            className="gr-enter"
            style={{ "--enter-delay": "0.3s" } as CSSProperties}
          >
            <ModelMarquee />
          </div>
        </ProductsEntrance>
      </Module>
    </Band>

    <MachineFold />
    <ValueFold className="gr-value--display" sentences={["One more thing"]} />
    <HomeFlow />

    <Band>
      <Module index={2}>
        <div className="gr-news-head">
          <h2 className="gr-heading">Latest News</h2>
          <a className="gr-link" href="/notes/">
            Read More
            <Arrow />
          </a>
        </div>
        {/* The wrapper scopes one rule: these cards drop their standfirsts
            — see .gr-news in pages.css. */}
        <div className="gr-news">
          <StoryRow
            columns="repeat(3, var(--card-narrow))"
            stories={libraryStories.slice(0, 3)}
          />
        </div>
        {/* The closing card: one full-width invitation, the hero's two ways
            in restated now the page has made its case. */}
        <div className="gr-home-cta">
          <h2 className="gr-heading gr-home-cta-title">
            Get your own <br className="gr-home-cta-br" />
            models today
          </h2>
          <div className="gr-home-actions">
            <a className="gr-button gr-button--main" href={CONSOLE_BASE_URL}>
              Get API Key
              <Arrow />
            </a>
          </div>
        </div>
      </Module>
    </Band>

    <Band>
      <Footer index={3} />
    </Band>

    {/* Figma 509:645 — the fixed haze over the viewport's bottom edge;
        it sits out the hero and fades in past the first fold */}
  </Substrate>
);

/**
 * The machine fold, two ways: the inference machine (one endpoint, every
 * model) and the automated-RL loop, one mounted at a time behind a toggle.
 * Inference opens — it is the lead product; the RL machine keeps its whole
 * existing choreography untouched a click away.
 */
const MachineFold = (): ReactElement => {
  const [mode, setMode] = useState<"inference" | "rl">("inference");
  /* The two machines are very different heights, so a bare swap jumps the
     page; after the switch the fold pins itself back to the top of view. */
  const sectionRef = useRef<HTMLElement>(null);
  const show = (next: "inference" | "rl") => {
    setMode(next);
    requestAnimationFrame(() => {
      sectionRef.current?.scrollIntoView({
        behavior: "instant",
        block: "start",
      });
    });
  };
  const toggle = (
    <div className="gr-machine-toggle">
      <button
        aria-pressed={mode === "inference"}
        className="gr-machine-btn"
        onClick={() => show("inference")}
        type="button"
      >
        Inference
      </button>
      <button
        aria-pressed={mode === "rl"}
        className="gr-machine-btn"
        onClick={() => show("rl")}
        type="button"
      >
        Automated RL
      </button>
    </div>
  );
  return (
    <section className="gr-machine" ref={sectionRef}>
      {mode === "inference" ? (
        <InferenceFlow header={toggle} />
      ) : (
        <LoopSection header={toggle} />
      )}
    </section>
  );
};

const products = [
  {
    id: "inference",
    title: "Proxy your Model Inference",
    description:
      "Bring your existing code, change your base URL, and start sending requests to the latest frontier or open models.",
    features: [
      "Usage-based pricing",
      "No infrastructure to manage",
      "Plug n Play",
    ],
    action: "Get API Key",
    href: CONSOLE_BASE_URL,
  },
  {
    id: "post-training",
    title: "Automated RL",
    description:
      "We'll improve and run your benchmarks, move you to open source and run automated reinforcement learning to turn your production traces into a model trained for your workload.",
    features: [
      "Learn from real production traces",
      "Evaluations built around your tasks",
      "Get your own model weights. Served through the same API",
    ],
    action: "Contact us to set up",
    href: "https://cal.com/jsgradiated/30min",
  },
] as const;

/**
 * Prose that streams in: every word wrapped, released on a per-word
 * transition delay once the block nears the viewport's centre — the value
 * fold's sharpen-from-blur, at paragraph scale. Reduced motion renders it
 * standing.
 */
type StreamPart = { emphasis?: boolean; href?: string; text: string };

const StreamedProse = ({
  className,
  paragraphs,
}: {
  className?: string;
  paragraphs: ReadonlyArray<{
    className?: string;
    parts?: readonly StreamPart[];
    text?: string;
  }>;
}): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const seen = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        host.classList.add("gr-stream--on");
        seen.disconnect();
      },
      { rootMargin: "-20% 0px -20% 0px", threshold: 0 },
    );
    seen.observe(host);
    return () => seen.disconnect();
  }, []);
  let word = 0;
  const words = (text: string) =>
    text
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((token, ti) => (
        <span
          className="gr-stream-word"
          key={ti}
          style={{ "--w-delay": `${(word++ * 8) / 1000}s` } as CSSProperties}
        >
          {token}{" "}
        </span>
      ));
  return (
    <div className={className} ref={hostRef}>
      {paragraphs.map((paragraph, pi) => (
        <p className={paragraph.className} key={pi}>
          {(paragraph.parts ?? [{ text: paragraph.text ?? "" }]).map(
            (part, qi) =>
              part.href ? (
                <a className="gr-link" href={part.href} key={qi}>
                  {words(part.text)}
                </a>
              ) : part.emphasis ? (
                <em key={qi}>{words(part.text)}</em>
              ) : (
                <span key={qi}>{words(part.text)}</span>
              ),
          )}
        </p>
      ))}
    </div>
  );
};

/**
 * Releases the fold's entrance once it scrolls into view: the cards and
 * the marquee rise, settle and sharpen — the page's one entrance gesture
 * (gr-enter), gated here the way the loop fold gates its own.
 */
const ProductsEntrance = ({
  children,
}: {
  children: ReactNode;
}): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const seen = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        host.classList.add("gr-products-entrance--seen");
        seen.disconnect();
      },
      { threshold: 0.18 },
    );
    seen.observe(host);
    return () => seen.disconnect();
  }, []);
  return (
    <div className="gr-products-entrance" ref={hostRef}>
      {children}
    </div>
  );
};

/**
 * The two products, side by side. A tabbed version came first, but with two
 * items the tab row was chrome without a decision — both fit on the fold,
 * and each already carries its own visual, titled above it.
 */
const HomeProducts = (): ReactElement => (
  <div className="gr-home-products">
    {/* The prelude: why open models, why teams bounce off them, and what
        Gradiated does differently — the argument the two cards resolve.
        The words stream in with the value fold's sharpen-from-blur. */}
    <StreamedProse
      className="gr-products-prelude"
      paragraphs={[
        {
          parts: [
            {
              text: "Frontier model companies offer the path of least resistance for powering your product. As you scale, most companies want to improve their unit costs, whilst using AI ",
            },
            { emphasis: true, text: "more" },
            { text: " intensively." },
          ],
        },
        {
          text: "Yet why do most teams that try open weight models just end up switching back? Teams tend to switch their base models but don't optimize any of their other parameters, and post training is a new skillset and requires GPUs. This leads to performance regressions and the inevitable switch back.",
        },
        {
          text: "At Gradiated we proxy your current inference and collect your real production traces. We set up benchmarks or use your existing ones and test open models against them, show you before-and-afters, and tune your prompts, and the model itself to your preferences until we beat what you run now.",
        },
        {
          text: "We then continue the cycle and ensure an automated RL loop keeps your models getting better over time.",
        },
        {
          text: "Today, we do this by giving you a self-serve (!) forward deployed researcher. We make money on the inference if you move to your own model, and we aim to be the cheapest in the world at that too...",
        },
      ]}
    />

    <hr className="gr-products-rule" />

    <div className="gr-product-grid">
      {products.map((item) => (
        <article
          className="gr-product-card gr-enter"
          key={item.id}
          style={
            {
              "--enter-delay": `${0.1 + products.indexOf(item) * 0.15}s`,
            } as CSSProperties
          }
        >
          <header className="gr-product-head">
            <h2 className="gr-heading gr-product-title">{item.title}</h2>
            <p className="gr-product-desc">{item.description}</p>
          </header>
          <div className="gr-product-visual">
            {item.id === "inference" ? <InferenceExample /> : <RlExample />}
          </div>
          <div className="gr-product-copy">
            <ul>
              {item.features.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
            <a className="gr-link gr-product-link" href={item.href}>
              {item.action}
              <Arrow />
            </a>
          </div>
        </article>
      ))}
    </div>
  </div>
);

/* The SDK snippets the inference card types through. Tokenised rather than
   JSX so the typing can stop mid-token and the syntax ink still holds; the
   lesson of the card: the SDK is just formatting — whichever one the reader
   already has, the base URL is the line that stays. */
type CodeToken = { cls?: string; t: string };

/* Single-path language marks (Simple Icons, CC0), inlined so they take
   currentColor and follow the theme's ink. */
const LANG_ICONS = {
  py: (
    <svg aria-label="Python" role="img" viewBox="0 0 24 24">
      <path d="M14.25.18l.9.2.73.26.59.3.45.32.34.34.25.34.16.33.1.3.04.26.02.2-.01.13V8.5l-.05.63-.13.55-.21.46-.26.38-.3.31-.33.25-.35.19-.35.14-.33.1-.3.07-.26.04-.21.02H8.77l-.69.05-.59.14-.5.22-.41.27-.33.32-.27.35-.2.36-.15.37-.1.35-.07.32-.04.27-.02.21v3.06H3.17l-.21-.03-.28-.07-.32-.12-.35-.18-.36-.26-.36-.36-.35-.46-.32-.59-.28-.73-.21-.88-.14-1.05-.05-1.23.06-1.22.16-1.04.24-.87.32-.71.36-.57.4-.44.42-.33.42-.24.4-.16.36-.1.32-.05.24-.01h.16l.06.01h8.16v-.83H6.18l-.01-2.75-.02-.37.05-.34.11-.31.17-.28.25-.26.31-.23.38-.2.44-.18.51-.15.58-.12.64-.1.71-.06.77-.04.84-.02 1.27.05zm-6.3 1.98l-.23.33-.08.41.08.41.23.34.33.22.41.09.41-.09.33-.22.23-.34.08-.41-.08-.41-.23-.33-.33-.22-.41-.09-.41.09zm13.09 3.95l.28.06.32.12.35.18.36.27.36.35.35.47.32.59.28.73.21.88.14 1.04.05 1.23-.06 1.23-.16 1.04-.24.86-.32.71-.36.57-.4.45-.42.33-.42.24-.4.16-.36.09-.32.05-.24.02-.16-.01h-8.22v.82h5.84l.01 2.76.02.36-.05.34-.11.31-.17.29-.25.25-.31.24-.38.2-.44.17-.51.15-.58.13-.64.09-.71.07-.77.04-.84.01-1.27-.04-1.07-.14-.9-.2-.73-.25-.59-.3-.45-.33-.34-.34-.25-.34-.16-.33-.1-.3-.04-.25-.02-.2.01-.13v-5.34l.05-.64.13-.54.21-.46.26-.38.3-.32.33-.24.35-.2.35-.14.33-.1.3-.06.26-.04.21-.02.13-.01h5.84l.69-.05.59-.14.5-.21.41-.28.33-.32.27-.35.2-.36.15-.36.1-.35.07-.32.04-.28.02-.21V6.07h2.09l.14.01zm-6.47 14.25l-.23.33-.08.41.08.41.23.33.33.23.41.08.41-.08.33-.23.23-.33.08-.41-.08-.41-.23-.33-.33-.23-.41-.08-.41.08z" />
    </svg>
  ),
  ts: (
    <svg aria-label="TypeScript" role="img" viewBox="0 0 24 24">
      <path d="M1.125 0C.502 0 0 .502 0 1.125v21.75C0 23.498.502 24 1.125 24h21.75c.623 0 1.125-.502 1.125-1.125V1.125C24 .502 23.498 0 22.875 0zm17.363 9.75c.612 0 1.154.037 1.627.111a6.38 6.38 0 0 1 1.306.34v2.458a3.95 3.95 0 0 0-.643-.361 5.093 5.093 0 0 0-.717-.26 5.453 5.453 0 0 0-1.426-.2c-.3 0-.573.028-.819.086a2.1 2.1 0 0 0-.623.242c-.17.104-.3.229-.393.374a.888.888 0 0 0-.14.49c0 .196.053.373.156.529.104.156.252.304.443.444s.423.276.696.41c.273.135.582.274.926.416.47.197.892.407 1.266.628.374.222.695.473.963.753.268.279.472.598.614.957.142.359.214.776.214 1.253 0 .657-.125 1.21-.373 1.656a3.033 3.033 0 0 1-1.012 1.085 4.38 4.38 0 0 1-1.487.596c-.566.12-1.163.18-1.79.18a9.916 9.916 0 0 1-1.84-.164 5.544 5.544 0 0 1-1.512-.493v-2.63a5.033 5.033 0 0 0 3.237 1.2c.333 0 .624-.03.872-.09.249-.06.456-.144.623-.25.166-.108.29-.234.373-.38a1.023 1.023 0 0 0-.074-1.089 2.12 2.12 0 0 0-.537-.5 5.597 5.597 0 0 0-.807-.444 27.72 27.72 0 0 0-1.007-.436c-.918-.383-1.602-.852-2.053-1.405-.45-.553-.676-1.222-.676-2.005 0-.614.123-1.141.369-1.582.246-.441.58-.804 1.004-1.089a4.494 4.494 0 0 1 1.47-.629 7.536 7.536 0 0 1 1.77-.201zm-15.113.188h9.563v2.166H9.506v9.646H6.789v-9.646H3.375z" />
    </svg>
  ),
} as const;

const SNIPPETS: ReadonlyArray<{
  file: string;
  lang: keyof typeof LANG_ICONS;
  tokens: readonly CodeToken[];
}> = [
  {
    file: "your-app.py",
    lang: "py",
    tokens: [
      { cls: "gr-code-muted", t: "from" },
      { t: " openai " },
      { cls: "gr-code-muted", t: "import" },
      { t: " OpenAI\n\nclient = OpenAI(\n api_key=" },
      { cls: "gr-code-string", t: '"YOUR_GRADIATED_KEY"' },
      { t: ",\n" },
      { cls: "gr-code-highlight", t: ' base_url="https://api.gradiated.com"' },
      { t: "\n)" },
    ],
  },
  {
    file: "your-app.py",
    lang: "py",
    tokens: [
      { cls: "gr-code-muted", t: "from" },
      { t: " anthropic " },
      { cls: "gr-code-muted", t: "import" },
      { t: " Anthropic\n\nclient = Anthropic(\n api_key=" },
      { cls: "gr-code-string", t: '"YOUR_GRADIATED_KEY"' },
      { t: ",\n" },
      { cls: "gr-code-highlight", t: ' base_url="https://api.gradiated.com"' },
      { t: "\n)" },
    ],
  },
  {
    file: "your-app.ts",
    lang: "ts",
    tokens: [
      { cls: "gr-code-muted", t: "import" },
      { t: " { createOpenAI } " },
      { cls: "gr-code-muted", t: "from" },
      { t: " " },
      { cls: "gr-code-string", t: '"@ai-sdk/openai"' },
      { t: ";\n\n" },
      { cls: "gr-code-muted", t: "const" },
      { t: " gradiated = createOpenAI({\n apiKey: " },
      { cls: "gr-code-string", t: '"YOUR_GRADIATED_KEY"' },
      { t: ",\n" },
      { cls: "gr-code-highlight", t: ' baseURL: "https://api.gradiated.com"' },
      { t: "\n});" },
    ],
  },
];

const prefersReducedMotion = (): boolean =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Cycles 0..count-1 on an interval; holds at 0 under reduced motion. */
const useCycle = (count: number, ms: number): number => {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (prefersReducedMotion()) return;
    const id = window.setInterval(
      () => setIndex((current) => (current + 1) % count),
      ms,
    );
    return () => window.clearInterval(id);
  }, [count, ms]);
  return index;
};

const TYPE_MS = 16;
const HOLD_MS = 2600;

const InferenceExample = (): ReactElement => {
  const [index, setIndex] = useState(0);
  const [typed, setTyped] = useState(0);
  const snippet = SNIPPETS[index];
  const total = snippet.tokens.reduce((sum, token) => sum + token.t.length, 0);

  /* Type the current snippet in; under reduced motion it appears whole and
     the rotation stops on the first. */
  useEffect(() => {
    if (prefersReducedMotion()) {
      setTyped(total);
      return;
    }
    setTyped(0);
    const id = window.setInterval(
      () => setTyped((count) => (count >= total ? count : count + 1)),
      TYPE_MS,
    );
    return () => window.clearInterval(id);
  }, [index, total]);

  // Fully typed: hold, then the next SDK takes the keyboard.
  useEffect(() => {
    if (prefersReducedMotion() || typed < total) return;
    const id = window.setTimeout(
      () => setIndex((current) => (current + 1) % SNIPPETS.length),
      HOLD_MS,
    );
    return () => window.clearTimeout(id);
  }, [typed, total]);

  let remaining = typed;
  const typing = typed < total;
  return (
    <div className="gr-inference-example">
      <div className="gr-example-bar">
        <span aria-hidden className="gr-example-lang">
          {LANG_ICONS[snippet.lang]}
        </span>
        <span>{snippet.file}</span>
      </div>
      <pre key={index}>
        {/* The stage is sized by the FULL snippet (hidden), and the
            typed text paints over it — so the card never grows or
            shrinks while the keyboard works. */}
        <span className="gr-code-stage">
          <code aria-hidden className="gr-code-sizer">
            {snippet.tokens.map((token) => token.t).join("")}
          </code>
          <code>
            {snippet.tokens.map((token, tokenIndex) => {
              const text = token.t.slice(0, Math.max(0, remaining));
              remaining -= token.t.length;
              if (!text) return null;
              return token.cls ? (
                <span className={token.cls} key={tokenIndex}>
                  {text}
                </span>
              ) : (
                <span key={tokenIndex}>{text}</span>
              );
            })}
            <span
              aria-hidden
              className="gr-code-caret"
              data-typing={typing || undefined}
            />
          </code>
        </span>
      </pre>
    </div>
  );
};

const RL_STEPS = [
  "Production traces",
  "Evaluations + RL",
  "Own the weights to your own post-trained model",
];

/** A 3x3 field of square dies; `lit` of them are on. The matrix fills as
 *  the pipeline advances — the card's state, drawn in chips. */
const DotMatrix = ({ lit }: { lit: number }): ReactElement => (
  <span aria-hidden className="gr-rl-matrix">
    {Array.from({ length: 9 }, (_, dot) => (
      <span
        className={`gr-rl-dot${dot < lit ? " gr-rl-dot--lit" : ""}`}
        key={dot}
        style={{ "--dot-delay": `${dot * 70}ms` } as CSSProperties}
      />
    ))}
  </span>
);

const RlExample = (): ReactElement => {
  const active = useCycle(RL_STEPS.length, 1800);
  return (
    <div className="gr-rl-example">
      {RL_STEPS.map((step, stepIndex) => (
        <div
          className="gr-rl-step"
          data-active={stepIndex === active || undefined}
          key={step}
        >
          <DotMatrix lit={(stepIndex + 1) * 3} />
          {step}
        </div>
      ))}
    </div>
  );
};
