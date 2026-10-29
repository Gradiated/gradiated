import { useMemo, useState } from "react";
import type { ReactElement } from "react";
import {
  Band,
  Footer,
  Module,
  GridIcon,
  ListIcon,
  Nav,
  Reveal,
  StoryList,
  StoryRow,
  Substrate,
} from "../components/design";
import type { Story } from "../components/design";
import "../styles/index.css";

import { libraryStories } from "../library-stories";

/* The rhythm of the page: a narrow-and-wide pair, then an even pair, then a
   row of three, repeating for as long as there are pieces. Rows are a cycle
   rather than a fixed list so the page keeps its shape as the Library grows,
   instead of the layout running out at the eighth piece. */
const ROWS = [
  { columns: "var(--card-narrow) minmax(0, 1fr)", size: 2 },
  { columns: "minmax(0, 1fr) minmax(0, 1fr)", size: 2 },
  { columns: "repeat(3, var(--card-narrow))", size: 3 },
];

const rowsOf = (stories: Story[]) => {
  const rows: { columns: string; stories: Story[] }[] = [];
  let rest = stories;
  for (let i = 0; rest.length > 0; i += 1) {
    const { columns, size } = ROWS[i % ROWS.length];
    rows.push({ columns, stories: rest.slice(0, size) });
    rest = rest.slice(size);
  }
  return rows;
};

export const NotesIndexPage = (): ReactElement => {
  const [view, setView] = useState<"grid" | "list">("grid");

  const shown = useMemo(
    () => libraryStories.filter((story) => story.kind === "note"),
    [],
  );

  const [lead, ...rest] = shown;
  const rows = useMemo(() => rowsOf(rest), [rest]);

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
                {/* Shows the view it will switch TO, which is what a single
                    toggle button has to do to be readable at a glance. */}
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
            <>
              {lead ? <StoryRow columns="1fr" lead stories={[lead]} /> : null}
              {rows.map((row) => (
                <StoryRow key={row.stories[0]?.href} {...row} />
              ))}
            </>
          )}
        </Module>
      </Band>

      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
