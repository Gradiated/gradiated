import { CONSOLE_BASE_URL } from "../urls";
import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import {
  Arrow,
  Band,
  Footer,
  HeroBeamRaw,
  HomeFlow,
  LoopSection,
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
 * One fold: a single centred statement, its standfirst, and two ways in.
 *
 * Centred, unlike every product hero. Those pair a claim with its evidence and
 * set the two side by side; this one has no evidence to place, so the sentence
 * sits in the middle of the screen and the measure shapes it.
 *
 * The second section is the news row: the Library's three latest pieces in
 * the same three-card grid the hardware page uses, fed from the same
 * catalogue as the Library index and the nav's list — one source, so none of
 * them can disagree. It was briefly a swipable carousel with a circular rim;
 * a static grid reads better and has nothing to explain. The beam overhangs
 * the fold and dissolves through this section, which ties the two together.
 *
 * What was here before: the legacy hero, the old ServiceTierSection and a
 * single Thesis card. The tier explorer has been superseded by TierExplorer on
 * the inference page, and the card by the Library — both were also running on
 * the legacy palette, whose variables no longer exist.
 */

export const HomePage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <Module bleed className="gr-module--fold" index={0}>
        {/* RAW-STYLE EXPLORATION: the colour beam, asciified into the
            engine's glyph language. Swap back to <HeroBeam /> to restore. */}
        <HeroBeamRaw />
        <div className="gr-fold-centred">
          {/* `from` carries the word stagger across the two fixed lines — each
              Reveal counts from zero on its own, which would otherwise animate
              them in lockstep. */}
          <h1 className="gr-display gr-home-title">
            <span className="gr-hero-line">
              <Reveal by="word" from={0}>
                Fast and cheap inference
              </Reveal>{" "}
            </span>
            <span className="gr-hero-line">
              <Reveal by="word" from={4}>
                post-trained on your workload.
              </Reveal>
            </span>
          </h1>
          <div className="gr-home-actions">
            <a className="gr-button gr-button--main" href={CONSOLE_BASE_URL}>
              Get API Key
              <Arrow />
            </a>
            <Link className="gr-button gr-button--secondary" to="/docs/">
              View Docs
              <Arrow />
            </Link>
          </div>
        </div>
      </Module>
    </Band>

    {/* new-homepage-layout: the value proposition streams in on its own
        fold, the loop fold shows the machine as a live diagram, and the
        chip fold lands it. All full-bleed and self-measuring, so they sit
        outside the Band/Module pair. */}
    <ValueFold />
    <LoopSection />
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
      </Module>
    </Band>

    <Band>
      <Footer index={2} />
    </Band>
  </Substrate>
);
