import type { ReactElement } from "react";
import {
  Band,
  Benchmark,
  Columns,
  CostStory,
  Features,
  Fold,
  Footer,
  Module,
  Nav,
  Showpiece,
  Substrate,
} from "../components/design";
import { Arrow } from "../components/design";
import "../styles/index.css";

const FEATURES = [
  {
    title: "Better",
    body: "Fine tuning changes the weights, so the model learns your task, formats and edge cases instead of being reminded in every prompt.",
  },
  {
    title: "Faster",
    body: "A smaller model has fewer weights to read and less work to do for every token. Fine tuning lets that smaller model stay useful on a narrow job.",
  },
  {
    title: "Cheaper",
    body: "Using a smaller model cuts the compute behind every request. The saving repeats on every token, not just during training.",
  },
];

export const TrainingPage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <Module bleed className="gr-module--fold" index={0}>
        <Fold
          title={["Make the", "model yours."]}
          lede="Switch the base URL to kick off auto fine tuning. We train on your traffic and ship new weights. Better results. Faster responses. 50–80% lower cost."
        >
          <CostStory />
        </Fold>
      </Module>

      <Module index={1}>
        <Features
          action={{ href: "/docs/quickstart/", label: "Get started" }}
          items={FEATURES}
        />
      </Module>

      <Module index={2}>
        <Columns count={2}>
          <div>
            <h2 className="gr-section-title">Question every result.</h2>
            <p
              className="gr-body gr-muted"
              style={{ marginBlockStart: "1rem" }}
            >
              Every run compares the new model with the baseline you use in
              production. See what improved, what regressed and what stayed the
              same—along with the judge model, evaluation rubric, scores and
              confidence. Drill down from the summary to the prompts, responses
              and trace data behind individual results. Decide if the new
              weights earn their place in production.
            </p>
            <a
              className="gr-button gr-button--main"
              href="/docs/quickstart/"
              style={{ marginBlockStart: "1.5rem" }}
            >
              Start training
              <Arrow />
            </a>
          </div>
          <div>
            <Benchmark />
          </div>
        </Columns>
      </Module>
    </Band>

    <Band>
      <Footer index={3} />
    </Band>
  </Substrate>
);
