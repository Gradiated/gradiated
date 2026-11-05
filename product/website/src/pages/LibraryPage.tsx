import type { ReactElement } from "react";
import { articles } from "../articles";
import { Arrow, Band, Footer, Module, Substrate } from "../components/design";
import { SandCircuitArtwork } from "../components/design/SandCircuitArtwork";
import { ChipLayersArtwork } from "../components/sand-library/ChipLayersArtwork";
import "../styles/index.css";
import "../components/sand-library/sand-library.css";
import "./library-mag.css";

/* /library/ — the magazine.
 *
 * The multi-media front for everything the lab publishes: interactive
 * journeys, essays, films. Editorial register, deliberately apart from
 * the product pages: a masthead, series carrying SUPERTITLES, features
 * with real artwork, and a compact index of everything else.
 *
 * Series are collections. Sand to Thought opens the magazine with the
 * two fabrication journeys as its first listings.
 */

const monthYear = (iso: string): string =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });

const kind = (layout: string): string =>
  layout === "journey" ? "Interactive journey" : "Essay";

export const LibraryPage = (): ReactElement => {
  /* The Library carries the broad top-of-funnel work only. Product
     pieces live under Notes, operational writing under the Handbook —
     neither lists here. Today that means the Sand to Thought series. */
  const sandSeries = articles
    .filter((article) => article.collection === "sand-to-thought")
    .sort((a, b) => a.publishedAt.localeCompare(b.publishedAt));

  return (
    <Substrate>
      <main className="gr-mag">
        <Band>
          <Module className="gr-module--top" index={0}>
            <header className="gr-mag-masthead">
              <h1 className="gr-mag-title">Library</h1>
            </header>

            {/* -- the opening series ----------------------------------- */}
            <section aria-label="Sand to Thought" className="gr-mag-series">
              <div className="gr-mag-features">
              {sandSeries.map((article) => (
                <article className="gr-mag-feature" key={article.path}>
                  <a className="gr-mag-feature-link" href={article.path}>
                    <div className="gr-mag-feature-art">
                      {article.path === "/sand-to-thought/" ? (
                        <SandCircuitArtwork />
                      ) : (
                        <ChipLayersArtwork variant="chip" />
                      )}
                    </div>
                    <div className="gr-mag-feature-copy">
                      <p className="gr-mag-super">Sand to Thought</p>
                      <h3 className="gr-mag-feature-title">
                        {article.title} <Arrow />
                      </h3>
                      {article.description && (
                        <p className="gr-mag-feature-dek">
                          {article.description}
                        </p>
                      )}
                      <p className="gr-mag-meta">
                        {kind(article.layout)} ·{" "}
                        {monthYear(article.publishedAt)}
                      </p>
                    </div>
                  </a>
                </article>
              ))}
              </div>
            </section>

          </Module>
        </Band>
        <Band>
          <Footer index={1} />
        </Band>
      </main>
    </Substrate>
  );
};
