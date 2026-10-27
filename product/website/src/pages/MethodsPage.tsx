import type { ComponentType, ReactElement } from "react";
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
import OverviewContent from "../method/overview.mdx";
import "../styles/index.css";

const navigation: SectionNavigationGroup[] = methodSections.map(
  (section, index) => ({
    heading: section.label,
    items: [
      ...(index === 0 ? [{ href: "/methods/", label: "Overview" }] : []),
      ...section.pages.map((page) => ({
        href: `/methods/${page.slug}/`,
        label: page.pageTitle,
      })),
    ],
  }),
);

export const MethodsPage = ({ slug }: { slug?: MethodSlug }): ReactElement => {
  const page = slug
    ? methodPages.find((candidate) => candidate.slug === slug)
    : undefined;
  const Content: ComponentType<{ components?: Record<string, unknown> }> =
    page?.Content ?? OverviewContent;
  const current = page ? `/methods/${page.slug}/` : "/methods/";

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module className="gr-module--top" index={0}>
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
              <h1>{page?.title ?? "Methods"}</h1>
              <div className="gr-doc-lead">
                <p>
                  {page?.indexDescription ??
                    "How Gradiated works, makes decisions, and builds the company."}
                </p>
              </div>
              <Content components={methodComponents} />
            </article>
          </div>
        </Module>
      </Band>

      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
