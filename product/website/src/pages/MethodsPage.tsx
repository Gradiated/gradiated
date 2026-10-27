import { Link } from "react-router-dom";
import type { ReactElement } from "react";
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
import { methodComponents } from "../components/method";
import { methodPages, methodSections } from "../method";
import type { MethodSlug } from "../method";
import "../styles/index.css";

const navigation: SectionNavigationGroup[] = methodSections.map((section) => ({
  heading: section.label,
  items: section.pages.map((page) => ({
    href: `/methods/${page.slug}/`,
    label: page.pageTitle,
  })),
}));

const MethodsIndex = (): ReactElement => (
  <>
    <header className="gr-masthead">
      <p className="gr-label">Methods</p>
      <h1 className="gr-masthead-title">Methods</h1>
    </header>

    <div className="gr-methods-index">
      {methodSections.map((section) => (
        <section className="gr-methods-index-group" key={section.label}>
          <h2 className="gr-label">{section.label}</h2>
          <ul>
            {section.pages.map((page) => (
              <li key={page.slug}>
                <Link to={`/methods/${page.slug}/`}>{page.pageTitle}</Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  </>
);

export const MethodsPage = ({ slug }: { slug?: MethodSlug }): ReactElement => {
  const page = slug
    ? methodPages.find((candidate) => candidate.slug === slug)
    : undefined;
  const Content = page?.Content;
  const current = page ? `/methods/${page.slug}/` : "";

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module className="gr-module--top" index={0}>
          {page && Content ? (
            <div className="gr-doc gr-methods">
              <aside className="gr-doc-side">
                <SectionNavigation
                  ariaLabel="Methods"
                  current={current}
                  groups={navigation}
                />
              </aside>

              <SectionNavigationFab
                current={current}
                groups={navigation}
                label="Methods"
              />

              <article className="gr-doc-main gr-prose">
                <h1>{page.title}</h1>
                <div className="gr-doc-lead">
                  <p>{page.indexDescription}</p>
                </div>
                <Content components={methodComponents} />
              </article>
            </div>
          ) : (
            <MethodsIndex />
          )}
        </Module>
      </Band>

      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
