import { useEffect, useState } from "react";
import type { ComponentType, ReactElement } from "react";
import { Band, Footer, Module, Nav, Substrate } from "../components/design";
import {
  AcceptableUseContent,
  DpaContent,
  PrivacyContent,
  SubprocessorsContent,
  TermsContent,
} from "../content";
import "../styles/index.css";

/**
 * The legal pages, in the design system.
 *
 * One layout for all five: they are the same kind of document, and the only
 * thing that differs is which prose goes in. They borrow the docs shell —
 * sticky contents beside a measured column — because a policy is read the way
 * reference is read, by looking for the one clause you came for rather than
 * from the top.
 *
 * `Status` is not here: it is an external link to status.gradiated.com, not a
 * page this site renders.
 */

export type LegalSlug =
  "acceptable-use" | "dpa" | "privacy" | "subprocessors-security" | "terms";

/* The full name IS the title. These pages used to lead with an abbreviation
   and put the real name in an eyebrow above it — two pieces of chrome saying
   the same thing, the smaller one carrying the meaning. One line, set large. */
export const LEGAL: Record<
  LegalSlug,
  { Content: ComponentType; title: string }
> = {
  "acceptable-use": {
    Content: AcceptableUseContent as ComponentType,
    title: "Acceptable Use Policy",
  },
  dpa: {
    Content: DpaContent as ComponentType,
    title: "Data Processing Addendum",
  },
  privacy: {
    Content: PrivacyContent as ComponentType,
    title: "Privacy Policy",
  },
  "subprocessors-security": {
    Content: SubprocessorsContent as ComponentType,
    title: "Subprocessors and security",
  },
  terms: { Content: TermsContent as ComponentType, title: "Terms of Service" },
};

/** `Your data` -> `your-data`, for the anchor. */
const anchor = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^\w]+/g, "-")
    .replace(/^-|-$/g, "");

export const LegalPage = ({ slug }: { slug: LegalSlug }): ReactElement => {
  const { Content, title } = LEGAL[slug];
  const [sections, setSections] = useState<{ id: string; text: string }[]>([]);
  const [active, setActive] = useState<string>();

  useEffect(() => {
    const main = document.querySelector(".gr-doc-main");
    if (!main) return;

    const headings = [...main.querySelectorAll("h2")];
    /* The heading owns its anchor — the prose is authored elsewhere and
       carries no ids of its own. */
    headings.forEach((h) => {
      if (!h.id) h.id = anchor(h.textContent ?? "");
    });
    setSections(headings.map((h) => ({ id: h.id, text: h.textContent ?? "" })));

    const observer = new IntersectionObserver(
      (entries) => {
        const seen = entries.filter((e) => e.isIntersecting);
        if (seen.length > 0) setActive(seen[0].target.id);
      },
      { rootMargin: "0px 0px -70% 0px", threshold: 0 },
    );
    headings.forEach((h) => observer.observe(h));
    return () => observer.disconnect();
  }, [slug]);

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module className="gr-module--top" index={0}>
          <header className="gr-masthead">
            <h1 className="gr-masthead-title gr-masthead-title--display">
              {title}
            </h1>
          </header>

          <div className="gr-doc">
            <aside className="gr-doc-side">
              {/* Absent rather than empty on a policy with no headings. */}
              {sections.length > 1 ? (
                <nav aria-label="Sections" className="gr-doc-nav">
                  {sections.map((section) => (
                    <a
                      aria-current={section.id === active ? "page" : undefined}
                      className="gr-doc-nav-link"
                      href={`#${section.id}`}
                      key={section.id}
                    >
                      {section.text}
                    </a>
                  ))}
                </nav>
              ) : null}
            </aside>

            <article className="gr-doc-main gr-prose">
              <Content />
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
