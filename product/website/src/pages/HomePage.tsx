import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import {
  Arrow,
  Band,
  Footer,
  Module,
  Nav,
  StoryRow,
  Substrate,
} from "../components/design";
import { libraryStories } from "../library-stories";
import { CONSOLE_BASE_URL } from "../urls";
import { ModelRoadmap } from "./ModelRoadmap";
import "../styles/index.css";
import "./home-lab.css";

export const HomePage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <Module bleed className="gr-module--fold" index={0}>
        <div className="gr-fold-left gr-lab-hero">
          <h1 className="gr-display gr-home-title">Open source AI lab</h1>
          <p className="gr-lab-lede">
            We believe in an open source, distributed future for AI models,
            where developers control what they build and where it runs. We got
            tired of one API deciding what our products cost and how they
            behave. So we train models for everyday software work and release
            the weights so you can run them yourself.
          </p>
          <div className="gr-home-actions">
            <a className="gr-button gr-button--main" href={CONSOLE_BASE_URL}>
              Start Research <Arrow />
            </a>
            <Link className="gr-button gr-button--secondary" to="/docs/">
              View Docs <Arrow />
            </Link>
          </div>
        </div>
      </Module>
    </Band>

    <ModelRoadmap />

    <Band>
      <Module index={2}>
        <div className="gr-news-head">
          <h2 className="gr-heading">Latest from the lab</h2>
          <a className="gr-link" href="/notes/">
            Read the notes <Arrow />
          </a>
        </div>
        <div className="gr-news">
          <StoryRow
            columns="repeat(3, var(--card-narrow))"
            stories={libraryStories.slice(0, 3)}
          />
        </div>

        <section className="gr-home-cta" aria-labelledby="lab-training-title">
          <h2 className="gr-heading gr-home-cta-title" id="lab-training-title">
            Get your own model running
          </h2>
          <p className="gr-body gr-muted gr-lab-cta-copy">
            Swap your base url over to the one we provide you. We will collect
            production traces, build the evals, train your own model for your
            task, and serve it for you through the API. You own the weights.
          </p>
          <div className="gr-home-actions">
            <a className="gr-button gr-button--main" href={CONSOLE_BASE_URL}>
              Start Research <Arrow />
            </a>
          </div>
        </section>
      </Module>
    </Band>

    <Band>
      <Footer index={3} />
    </Band>
  </Substrate>
);
