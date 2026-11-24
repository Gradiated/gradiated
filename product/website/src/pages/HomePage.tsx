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
            <a className="gr-button gr-button--main" href="#model-roadmap">
              Explore the model roadmap
            </a>
            <Link className="gr-button gr-button--secondary" to="/training/">
              Train a model for your product
            </Link>
          </div>
        </div>
      </Module>
    </Band>

    <ModelRoadmap />

    <Band>
      <Module index={2}>
        <section
          className="gr-lab-training"
          aria-labelledby="lab-training-title"
        >
          <h2 className="gr-heading" id="lab-training-title">
            Your product deserves its own model.
          </h2>
          <div>
            <p>
              Give us a workflow you want to move off a frontier model. We use
              your production traces and codebase to build evals, then
              post-train an open model for the work your product actually does.
              You own the weights.
            </p>
            <Link className="gr-button gr-button--main" to="/training/">
              Explore custom training
            </Link>
          </div>
        </section>

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
      </Module>
    </Band>

    <Band>
      <Footer index={3} />
    </Band>
  </Substrate>
);
