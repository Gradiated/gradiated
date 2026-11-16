import { useMemo, useState } from "react";
import type { ReactElement } from "react";
import { articles } from "../articles";
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
import type { Story } from "../components/design";
import { SandCircuitArtwork } from "../components/design/SandCircuitArtwork";
import { ChipLayersArtwork } from "../components/sand-library/ChipLayersArtwork";
import { displayDate, libraryStories } from "../library-stories";
import "../styles/index.css";
import "../components/sand-library/sand-library.css";

const SAND_OVERVIEW_PATH =
  "/library/sand-to-thought/how-to-get-an-answer-out-of-sand/";

const journeys: Array<Story & { publishedAt: string }> = articles
  .filter((article) => article.collection === "sand-to-thought")
  .map((article) => ({
    date: displayDate(article.publishedAt),
    dateTime: article.status === "draft" ? undefined : article.publishedAt,
    href: article.path,
    illustration:
      article.path === SAND_OVERVIEW_PATH ? (
        <SandCircuitArtwork />
      ) : (
        <ChipLayersArtwork variant="chip" />
      ),
    kind: "note",
    lede: article.description,
    publishedAt: article.publishedAt,
    title: article.title,
  }));

const publishedAtByPath = new Map(
  articles.map((article) => [article.path, article.publishedAt]),
);

export const LibraryPage = (): ReactElement => {
  const [view, setView] = useState<"grid" | "list">("grid");
  const shown = useMemo(
    () =>
      [
        ...libraryStories
          .filter((story) => story.kind === "note")
          .map((story) => ({
            ...story,
            publishedAt: publishedAtByPath.get(story.href) ?? "",
          })),
        ...journeys,
      ].sort((a, b) => b.publishedAt.localeCompare(a.publishedAt)),
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
                  Library
                </Reveal>
              </div>

              <div className="gr-library-controls">
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
