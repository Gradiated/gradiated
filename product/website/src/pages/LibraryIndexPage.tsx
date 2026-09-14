import { useMemo, useState } from "react";
import type { ReactElement } from "react";
import { useSearchParams } from "react-router-dom";
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

const ALL: Story[] = libraryStories;

/** All first, and it is the default: `show` absent means the whole list. */
const FILTERS = [
  { label: "All", show: null },
  { label: "Notes", show: "notes" as const },
  { label: "Methods", show: "methods" as const },
];

export const LibraryIndexPage = ({
  initialFilter,
}: {
  initialFilter?: "methods" | "notes";
}): ReactElement => {
  /* The filter lives in the URL, not in component state, so a filtered view
     is a place that can be linked to — which is what the nav needs to send a
     reader to Notes or to Methods rather than to the whole index.

     THREE CHOICES, ONE ACTIVE. It used to be two toggles, where "off" meant
     the whole list: a reader who wanted everything back had to work out that
     un-pressing the filter they were in was the way to do it. "All" says it
     instead, and is the state the page opens in — an absent `show` is what it
     means, so the default URL stays clean. */
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<"grid" | "list">("grid");

  const requested = params.get("show") ?? initialFilter;
  const show =
    requested === "notes" || requested === "methods" ? requested : null;
  const kinds: Story["kind"][] =
    show === "notes" ? ["note"] : show === "methods" ? ["method"] : [];

  const shown = useMemo(
    () => (kinds.length === 0 ? ALL : ALL.filter((s) => kinds.includes(s.kind))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [show],
  );

  const [lead, ...rest] = shown;
  const rows = useMemo(() => rowsOf(rest), [rest]);

  /* `replace`, so filtering does not stack entries in the back button: a
     reader who tried both filters and pressed Back wants the page they came
     from, not the filter they tried two clicks ago.

     A choice rather than a toggle now — pressing the active one again does
     nothing, because "All" is how you get the whole list back. */
  const select = (next: "methods" | "notes" | null) => {
    setParams(next ? { show: next } : {}, { replace: true });
  };

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module className="gr-module--top" index={0}>
          <header className="gr-masthead">
            <div className="gr-masthead-line">
              <div>
                <p className="gr-label">Library</p>
                <Reveal as="h1" by="word" className="gr-masthead-title">
                  Notes &amp; Methods
                </Reveal>
              </div>

              <div className="gr-library-controls">
                {FILTERS.map((filter) => (
                  <button
                    aria-pressed={show === filter.show}
                    className="gr-library-filter"
                    key={filter.label}
                    onClick={() => select(filter.show)}
                    type="button"
                  >
                    {filter.label}
                  </button>
                ))}

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
