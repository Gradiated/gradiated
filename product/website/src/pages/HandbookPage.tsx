import { Link } from "react-router-dom";
import type { CSSProperties, ReactElement } from "react";
import {
  Band,
  Footer,
  Module,
  Nav,
  SectionNavigation,
  SectionNavigationFab,
  Substrate,
  WaferArtwork,
} from "../components/design";
import type { SectionNavigationGroup } from "../components/design";
import { handbookComponents } from "../components/handbook";
import { handbookPages, handbookSections } from "../handbook";
import type { HandbookSlug } from "../handbook";
import { handbookArt, handbookCovers } from "../handbook-visuals";
import "../styles/index.css";

const navigation: SectionNavigationGroup[] = handbookSections.map((section) => ({
  heading: section.label,
  items: section.pages.map((page) => ({
    href: `/handbook/${page.slug}/`,
    label: page.pageTitle,
  })),
}));

const HandbookSectionArtwork = ({
  slug,
}: {
  slug: HandbookSlug;
}): ReactElement => {
  const art = handbookArt[slug];

  return (
    <span aria-hidden className="gr-story-well gr-story-cover">
      {art ? (
        <span
          className="gr-story-art"
          style={
            {
              "--art-tall": `url(${art.tall})`,
              "--art-wide": `url(${art.wide ?? art.tall})`,
            } as CSSProperties
          }
        />
      ) : (
        <WaferArtwork options={handbookCovers[slug]} />
      )}
    </span>
  );
};

const HandbookIndex = (): ReactElement => (
  <>
    <header className="gr-masthead">
      <h1 className="gr-masthead-title">Handbook</h1>
    </header>

    <div className="gr-handbook-index">
      {handbookSections.map((section) => (
        <section
          className="gr-handbook-index-group gr-story"
          key={section.label}
        >
          <div className="gr-handbook-index-visual">
            <HandbookSectionArtwork slug={section.artSlug} />
            <h2 className="gr-label">{section.label}</h2>
          </div>
          <ul>
            {section.pages.map((page) => (
              <li key={page.slug}>
                <Link to={`/handbook/${page.slug}/`}>{page.pageTitle}</Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  </>
);

export const HandbookPage = ({
  slug,
}: {
  slug?: HandbookSlug;
}): ReactElement => {
  const page = slug
    ? handbookPages.find((candidate) => candidate.slug === slug)
    : undefined;
  const Content = page?.Content;
  const current = page ? `/handbook/${page.slug}/` : "";

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module className="gr-module--top" index={0}>
          {page && Content ? (
            <div className="gr-doc gr-handbook">
              <aside className="gr-doc-side">
                <SectionNavigation
                  ariaLabel="Handbook"
                  current={current}
                  groups={navigation}
                />
              </aside>

              <SectionNavigationFab
                current={current}
                groups={navigation}
                label="Handbook"
              />

              <article className="gr-doc-main gr-prose">
                <h1>{page.title}</h1>
                <Content components={handbookComponents} />
              </article>
            </div>
          ) : (
            <HandbookIndex />
          )}
        </Module>
      </Band>

      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
