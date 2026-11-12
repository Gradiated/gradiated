import { useMemo, useState } from "react";
import type { ReactElement } from "react";
import {
  Band,
  Footer,
  GridIcon,
  ListIcon,
  Module,
  Nav,
  Reveal,
  StoryList,
  StoryRow,
  Substrate,
} from "../components/design";
import "../styles/index.css";

import { libraryStories } from "../library-stories";

/* RELAUNCH: a standard three-column card grid, with the grid / list
   toggle kept. The old rhythm system (lead feature, narrow/wide cycles)
   went with the editorial work moving to /library/. */

export const NotesIndexPage = (): ReactElement => {
  const [view, setView] = useState<"grid" | "list">("grid");
  const shown = useMemo(
    () => libraryStories.filter((story) => story.kind === "note"),
    [],
  );

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module className="gr-module--top" index={0}>
          <header className="gr-masthead">
            <div className="gr-masthead-line">
              <div>
                <Reveal as="h1" by="word" className="gr-masthead-title">
                  Notes
                </Reveal>
              </div>

              <div className="gr-library-controls">
                {/* Shows the view it will switch TO — what a single toggle
                    has to do to be readable at a glance. */}
                <button
                  aria-label={
                    view === "grid" ? "Show as a list" : "Show as a grid"
                  }
                  className="gr-library-view"
                  onClick={() => setView(view === "grid" ? "list" : "grid")}
                  type="button"
                >
                  {view === "grid" ? <ListIcon /> : <GridIcon />}
                </button>
              </div>
            </div>
          </header>

          {view === "list" ? (
            <StoryList stories={shown} />
          ) : (
            <StoryRow columns="repeat(3, var(--card-narrow))" stories={shown} />
          )}
        </Module>
      </Band>

      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
