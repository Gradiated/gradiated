import type { ReactElement } from "react";
import {
  Band,
  Footer,
  Module,
  Nav,
  Substrate,
} from "../components/design";
import "../styles/index.css";

/* The page's own structure, and the first thing a reader meets. Set at title
   size rather than as a rail: on a model page this list IS the content. */
const CONTENTS = [
  "Model overview",
  "Benchmarks",
  "Getting started",
  "Cost / TPS",
  "Similar models",
  "Architecture deepdive",
  "What it is good for",
];

const slug = (name: string) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export const ModelDetailPage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <Module bleed index={0}>
        <div className="gr-model-head">
          {/* PLACEHOLDER — each model wants its own mark. */}
          <div className="gr-model-mark">Model-4</div>
          <div>
            <h1 className="gr-section-title">Model name</h1>
            <p className="gr-lede gr-muted" style={{ marginBlockStart: "0.5rem" }}>
              We co-design hardware and software to provide the world&rsquo;s
              most affordable inference.
            </p>
            <ul className="gr-model-tags">
              {["Open weights", "128k context", "Flex tier"].map((tag) => (
                <li className="gr-badge" key={tag}>
                  {tag}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Module>

      <Module index={1}>
        <ul className="gr-model-contents">
          {CONTENTS.map((entry) => (
            <li key={entry}>
              <a href={`#${slug(entry)}`}>{entry}</a>
            </li>
          ))}
        </ul>
      </Module>
    </Band>

    <Band>
      <Footer index={2} />
    </Band>
  </Substrate>
);
