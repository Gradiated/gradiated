import type { ReactElement } from "react";
import {
  Band,
  Columns,
  Features,
  Fold,
  Footer,
  Module,
  Nav,
  Substrate,
} from "../components/design";
import "../styles/index.css";

const PRINCIPLES = [
  {
    title: "One company.",
    body: "Gradiated is a brand owned by PostHog Inc. It carries the same builder-first approach into the infrastructure underneath AI products.",
  },
  {
    title: "A distinct focus.",
    body: "Inference rewards depth. Gradiated exists so one team can concentrate on models, serving systems, and hardware without diluting that work.",
  },
  {
    title: "A practical goal.",
    body: "Make open-model inference more affordable by improving the whole stack, from the API developers use to the systems and silicon that run it.",
  },
];

export const AboutPage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <Module bleed className="gr-module--fold" index={0}>
        <Fold
          lede={[
            "Gradiated began inside PostHog, from a question about what AI builders would need next: better access to efficient, dependable inference.",
            "PostHog created Gradiated as a focused brand for answering that question across software, systems, and hardware.",
          ]}
          title={["From PostHog.", "For inference."]}
        />
      </Module>

      <Module index={1} title="Team">
        <Columns count={3}>
          <div>
            <h3 className="gr-heading">James Hawkins</h3>
            <p className="gr-label gr-muted">
              Cofounder of Gradiated and PostHog
            </p>
            <p className="gr-body gr-muted">
              Co-built PostHog into a unicorn and a beloved developer brand.
              Strengths are product, brand and early go to market.
            </p>
          </div>
          <div>
            <h3 className="gr-heading">Josh Snyder</h3>
            <p className="gr-label gr-muted">Cofounder of Gradiated</p>
            <p className="gr-body gr-muted">
              Led AI engineering at PostHog. Specialized in the mathematics of
              graph neural networks, with a master&apos;s degree from Cambridge.
            </p>
          </div>
          <div>
            <h3 className="gr-heading">Dr Aidan McConnell</h3>
            <p className="gr-label gr-muted">Technical Staff</p>
            <p className="gr-body gr-muted">
              PhD in quantum computing and semiconductors.
            </p>
          </div>
        </Columns>
      </Module>

      <Module index={2} title="The relationship">
        <Features items={PRINCIPLES} />
      </Module>
    </Band>

    <Band>
      <Footer index={3} />
    </Band>
  </Substrate>
);
