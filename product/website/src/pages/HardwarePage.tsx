import type { ReactElement } from "react";
import {
  Band,
  ChipStackRaw,
  Fold,
  Footer,
  Module,
  Nav,
  StoryRow,
  Substrate,
} from "../components/design";
import { storyAt } from "../library-stories";
import { articles } from "../articles";
import { SAND_TO_THOUGHT_URL } from "../urls";
import "../styles/index.css";

/* Three pieces from the Library, as the Library's own cards. Named by where
   they live, and everything shown about them comes from the catalogue — so
   this row cannot drift from the Library or point at something that moved.

   The same card, not a second one that looks like it: this row used to be
   built from `Cards`, which gave it an image well the Handbook page had no
   image for. */
const PIECES = [
  storyAt("/library/gemma-inference-engine/"),
  storyAt("/library/our-thesis/"),
  storyAt("/handbook/mission/"),
].filter((story): story is NonNullable<typeof story> => story !== undefined);

export const HardwarePage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <Module bleed className="gr-module--fold" index={0}>
        <Fold
          action={{ href: "/careers/", label: "Build with us" }}
          secondaryAction={
            articles.some((article) => article.collection === "sand-to-thought")
              ? {
                  href: SAND_TO_THOUGHT_URL,
                  label: "Sand to Thought",
                  tone: "ghost",
                }
              : undefined
          }
          beside
          lede={[
            "The chip design is based on your requirements. Our first chip is based on efficiency, not speed. It's designed for specific open source models, to suit ultra intense, long running cloud workloads at the lowest cost imaginable.",
            "We are hiring our founding silicon and hardware engineers. We'd love to talk to you if this is something you could build.",
          ]}
          media={<ChipStackRaw />}
          title={["Runs models.", "Not bills."]}
        />
      </Module>

      <Module index={1}>
        <StoryRow
          columns="repeat(3, var(--card-narrow))"
          stories={PIECES}
          uniform
        />
      </Module>
    </Band>

    <Band>
      <Footer index={2} />
    </Band>
  </Substrate>
);
