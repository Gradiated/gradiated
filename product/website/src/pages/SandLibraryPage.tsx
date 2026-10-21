import type { ReactElement } from "react";
import { articles } from "../articles";
import {
  Arrow,
  Band,
  Footer,
  Module,
  Nav,
  Substrate,
} from "../components/design";
import { SandCircuitArtwork } from "../components/design/SandCircuitArtwork";
import { ChipLayersArtwork } from "../components/sand-library/ChipLayersArtwork";
import "../styles/index.css";
import "../components/sand-library/sand-library.css";

export const SandLibraryPage = (): ReactElement => {
  const overview = articles.find(
    (article) => article.path === "/sand-to-thought/",
  );
  const deepDives = articles.filter(
    (article) =>
      article.collection === "sand-to-thought" && article !== overview,
  );

  return (
    <Substrate>
      <Nav />
      <main className="sand-library">
        <Band>
          <Module className="gr-module--top" index={0}>
            <header className="gr-masthead">
              <p className="gr-label">Explore the semiconductor stack</p>
              <h1 className="gr-masthead-title">Sand to Thought</h1>
            </header>
            {overview && (
              <article className="sand-library-card sand-library-card--lead">
                <a
                  className="sand-library-link sand-cover"
                  href={overview.path}
                >
                  <div className="sand-library-art sand-library-art--overview">
                    <SandCircuitArtwork />
                  </div>
                  <div className="sand-library-copy">
                    <p className="gr-label">The complete journey</p>
                    <h2>{overview.title}</h2>
                    <p className="sand-library-description">
                      {overview.description}
                    </p>
                    <span className="sand-library-action">
                      Start exploring <Arrow />
                    </span>
                  </div>
                </a>
              </article>
            )}
            {deepDives.length > 0 && (
              <section
                className="sand-library-dives"
                aria-labelledby="sand-deep-dives"
              >
                <h2 id="sand-deep-dives" className="gr-label">
                  Deep dives
                </h2>
                <div className="sand-library-grid">
                  {deepDives.map((article) => (
                    <article className="sand-library-card" key={article.path}>
                      <a className="sand-library-link" href={article.path}>
                        <div className="sand-library-art sand-library-art--fabrication">
                          <ChipLayersArtwork />
                        </div>
                        <div className="sand-library-copy">
                          <p className="gr-label">
                            Fabrication
                            {article.status === "draft" ? " · Draft" : ""}
                          </p>
                          <h3>{article.title}</h3>
                          <p className="sand-library-description">
                            {article.description}
                          </p>
                          <span className="sand-library-action">
                            Explore the process <Arrow />
                          </span>
                        </div>
                      </a>
                    </article>
                  ))}
                </div>
              </section>
            )}
          </Module>
        </Band>
      </main>
      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
