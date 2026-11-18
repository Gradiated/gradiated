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
  Substrate,
} from "../components/design";
import { Arrow } from "../components/design";
import { WaitlistButton } from "../components/WaitlistButton";
import "../styles/index.css";

const FEATURES = [
  {
    title: "Better",
    body: "Train on your task, formats and edge cases, then measure whether the model improves on the results that matter to your product.",
  },
  {
    title: "Faster",
    body: "A smaller model has less work to do for every token. Use it for the tasks where evaluations show it can deliver the quality you need.",
  },
  {
    title: "Cheaper",
    body: "Using a smaller model cuts the compute behind every request. At enough volume, those inference savings can justify the cost of training.",
  },
];

export const TrainingPage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <Module bleed className="gr-module--fold" index={0}>
        <Fold
          title={["Make the", "model yours."]}
          lede="Post-training is in private beta. When your workload calls for a bespoke model, train on your production tasks to improve the results that matter to your product."
        >
          <CostStory />
        </Fold>
      </Module>

      <Module index={1}>
        <Features items={FEATURES} />
        <div className="gr-features-action">
          <WaitlistButton className="gr-button gr-button--main">
            Join post-training waitlist
            <Arrow />
          </WaitlistButton>
        </div>
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
              and trace data behind individual results. Decide which tasks the
              new model is ready to take on.
            </p>
            <div style={{ marginBlockStart: "1.5rem" }}>
              <WaitlistButton className="gr-button gr-button--main">
                Join post-training waitlist
                <Arrow />
              </WaitlistButton>
            </div>
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
