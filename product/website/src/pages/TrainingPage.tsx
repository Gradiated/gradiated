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
          lede="Post-training is in private beta. Join the waitlist to train models on your workload for better results, faster responses, and lower cost."
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
              and trace data behind individual results. Decide if the new
              weights earn their place in production.
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
