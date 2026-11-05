import type { ReactElement } from "react";
import { Navigate } from "react-router-dom";
import {
  Band,
  Footer,
  Module,
  Nav,
  SectionNavigation,
  SectionNavigationFab,
  Substrate,
} from "../components/design";
import type { SectionNavigationGroup } from "../components/design";
import { useRailDocNav } from "../components/design/RailShell";
import { handbookComponents } from "../components/handbook";
import { handbookPages, handbookSections } from "../handbook";
import type { HandbookSlug } from "../handbook";
import "../styles/index.css";

const navigation: SectionNavigationGroup[] = handbookSections.map(
  (section) => ({
    heading: section.label,
    items: section.pages.map((page) => ({
      href: `/handbook/${page.slug}/`,
      label: page.pageTitle,
    })),
  }),
);

const HandbookIndex = (): ReactElement => (
  <>
    <header className="gr-masthead">
      <h1 className="gr-masthead-title">Handbook</h1>
    </header>

    <SectionNavigation
      ariaLabel="Handbook topics"
      current=""
      groups={navigation}
    />
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

  /* The site rail carries the handbook's contents — doc mode is a
     state of the ONE nav, so the page draws no sidebar of its own. */
  useRailDocNav({ title: "Handbook", current, groups: navigation });

  /* /handbook/ opens on the first entry where the rail shows the
     contents (desktop); on a phone the rail is a strip, so the index
     page IS the contents and stays. */
  const wide =
    typeof window !== "undefined" &&
    window.matchMedia("(min-width: 60rem)").matches;
  if (!page && wide) {
    const first = handbookSections[0]?.pages[0];
    if (first) {
      return <Navigate replace to={`/handbook/${first.slug}/`} />;
    }
  }

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module className="gr-module--top" index={0}>
          {page && Content ? (
            <div className="gr-doc gr-handbook">
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
