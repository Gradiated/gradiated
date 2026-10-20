import { CONSOLE_BASE_URL } from "../urls";
import { useRef, useState } from "react";
import { Cpu } from "lucide-react";
import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import {
  Arrow,
  Band,
  BottomHaze,
  Footer,
  HeroBeam,
  HeroBeamRaw,
  HomeFlow,
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

export const HomePage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <Module bleed className="gr-module--fold" index={0}>
        {/* Both beams, layered: the colour field breathes underneath and the
            glyph field is inked over it — the engine's language drawn on the
            hero's light. Same wrapper, same cone, so they register. */}
        <HeroBeam />
        <HeroBeamRaw />
        <HomeProductCarousel />
      </Module>
    </Band>

    <ModelMarquee />
    <ValueFold />
    <LoopSection />
    <ValueFold sentences={["One more thing…"]} />
    <HomeFlow />

    <Band>
      <Module index={1}>
        <div className="gr-news-head">
          <h2 className="gr-heading">Latest News</h2>
          <a className="gr-link" href="/library/">
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
      <Footer index={2} />
    </Band>

    {/* Figma 509:645 — the fixed haze over the viewport's bottom edge;
        it sits out the hero and fades in past the first fold */}
    <BottomHaze />
  </Substrate>
);

const products = [
  {
    id: "inference",
    name: "Open model inference",
    title: "Open models. One API.",
    description:
      "Bring your existing code, change your base URL, and start sending requests.",
    features: ["Usage-based pricing", "No infrastructure to manage"],
    action: "Get API Key",
    href: CONSOLE_BASE_URL,
  },
  {
    id: "post-training",
    name: "Automated RL",
    title: "Better at your workload.",
    description:
      "Automated reinforcement learning turns your production traces into a model trained for your workload.",
    features: [
      "Learn from real production traces",
      "Evaluations built around your tasks",
      "Served through the same API",
    ],
    action: "Contact us to set up",
    href: "https://cal.com/jsgradiated/30min",
  },
] as const;

const HomeProductCarousel = (): ReactElement => {
  const [activeIndex, setActiveIndex] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const product = products[activeIndex];
  const showProduct = (index: number, focusTab = false): void => {
    const nextIndex = (index + products.length) % products.length;
    setActiveIndex(nextIndex);
    if (focusTab) tabs.current[nextIndex]?.focus();
  };

  return (
    <div className="gr-home-products">
      <div className="gr-fold-centred gr-home-products-intro">
        <h1 className="gr-display gr-home-title">
          <span className="gr-hero-line">
            <Reveal by="word">The cheapest way to run</Reveal>
          </span>
          <span className="gr-hero-line">
            <Reveal by="word" from={5}>
              open-source models.
            </Reveal>
          </span>
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
      <div
        className="gr-product-tabs"
        role="tablist"
        aria-label="Explore our products"
      >
        {products.map((item, index) => {
          return (
            <button
              key={item.id}
              ref={(element) => {
                tabs.current[index] = element;
              }}
              type="button"
              role="tab"
              id={`product-tab-${item.id}`}
              aria-controls={`product-panel-${item.id}`}
              aria-selected={activeIndex === index}
              tabIndex={activeIndex === index ? 0 : -1}
              onClick={() => showProduct(index)}
              onKeyDown={(event) => {
                if (
                  !["ArrowLeft", "ArrowRight", "Home", "End"].includes(
                    event.key,
                  )
                )
                  return;
                event.preventDefault();
                showProduct(
                  event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? products.length - 1
                      : activeIndex + (event.key === "ArrowRight" ? 1 : -1),
                  true,
                );
              }}
              className={`gr-product-tab gr-product-tab--${item.id}`}
            >
              <span>{item.name}</span>
            </button>
          );
        })}
      </div>
      <div className="gr-product-stage">
        {products.map((item, index) => (
          <div
            key={item.id}
            id={`product-panel-${item.id}`}
            role="tabpanel"
            aria-labelledby={`product-tab-${item.id}`}
            tabIndex={0}
            hidden={activeIndex !== index}
            className={`gr-product-panel gr-product-panel--${item.id}`}
          >
            <div className="gr-product-visual">
              {item.id === "inference" ? (
                <div className="gr-inference-example">
                  <div className="gr-example-bar">
                    <span>your-app.py</span>
                    <span>Python / OpenAI SDK</span>
                  </div>
                  <pre>
                    <code>
                      <span className="gr-code-muted">from</span> openai{" "}
                      <span className="gr-code-muted">import</span> OpenAI
                      {"\n\n"}client = OpenAI({"\n"} api_key=
                      <span className="gr-code-string">
                        "YOUR_GRADIATED_KEY"
                      </span>
                      ,{"\n"}
                      <span className="gr-code-highlight">
                        {" "}
                        base_url="https://api.gradiated.com"
                      </span>
                      {"\n"})
                    </code>
                  </pre>
                  <div className="gr-example-footer">
                    <Cpu size={18} aria-hidden="true" />
                    <span>Your code. Open models. Gradiated underneath.</span>
                  </div>
                </div>
              ) : (
                <div className="gr-rl-example">
                  <span className="gr-example-caption">
                    YOUR WORKLOAD IS THE TRAINING DATA
                  </span>
                  {[
                    "Production traces",
                    "Evaluations + RL",
                    "Your post-trained model",
                  ].map((step, stepIndex) => (
                    <div className="gr-rl-step" key={step}>
                      <span>0{stepIndex + 1}</span>
                      {step}
                      <span aria-hidden="true">
                        {stepIndex === 2 ? "✓" : "↓"}
                      </span>
                    </div>
                  ))}
                  <span className="gr-rl-endpoint">
                    Same API. A model trained for your tasks.
                  </span>
                </div>
              )}
            </div>
            <div className="gr-product-copy">
              <h2 className="gr-heading">{item.title}</h2>
              <p>{item.description}</p>
              <ul>
                {item.features.map((feature) => (
                  <li key={feature}>{feature}</li>
                ))}
              </ul>
              <a className="gr-product-link" href={item.href}>
                {item.action}
                <Arrow />
              </a>
            </div>
          </div>
        ))}
      </div>
      <span className="gr-product-announcement" role="status">
        {product.name}
      </span>
    </div>
  );
};
