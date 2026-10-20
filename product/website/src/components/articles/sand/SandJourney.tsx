import { memo, useMemo, useRef } from "react";
import type { ReactElement } from "react";
import { SectionFab } from "../../design";
import { SandCircuitArtwork } from "../../design/SandCircuitArtwork";
import article, {
  contents,
} from "../../../../content/articles/sand/script.md?sand-article";
import { SandStage } from "./SandStage";
import {
  useActiveChapter,
  useSandAnimation,
  useSandSubsections,
} from "./useSandJourney";
import "./journey.css";

// The animation mutates this markup, so contents updates must preserve its nodes.
const SandMarkup = memo(
  ({ className, html }: { className: string; html: string }) => (
    <div className={className} dangerouslySetInnerHTML={{ __html: html }} />
  ),
);

const introductionEnd = article.indexOf("</header>") + "</header>".length;
const introduction = article.slice(0, introductionEnd);
const body = article.slice(introductionEnd);
const chapters = [
  { id: "sand-introduction", label: "Introduction" },
  ...contents,
];

export const SandJourney = (): ReactElement => {
  const hostRef = useRef<HTMLElement>(null);
  const subsections = useSandSubsections(hostRef, chapters);
  const headings = useMemo(
    () =>
      chapters.flatMap((chapter) => [
        chapter,
        ...(subsections[chapter.id] ?? []).filter(
          ({ id }) => id !== chapter.id,
        ),
      ]),
    [subsections],
  );
  const activeSection = useActiveChapter(hostRef, headings);
  const active = chapters.find(
    ({ id }) =>
      id === activeSection ||
      subsections[id]?.some((section) => section.id === activeSection),
  )?.id;

  useSandAnimation(hostRef);

  return (
    <article className="sand-journey" ref={hostRef}>
      <div className="sand-layout">
        <aside className="sand-side gr-doc-side">
          <nav aria-label="Guide contents" className="gr-doc-nav">
            <div className="gr-doc-nav-group">
              <p className="gr-doc-nav-heading gr-label">Sand to Thought</p>
              {chapters.map(({ id, label }) => (
                <div className="sand-chapter" key={id}>
                  <a
                    aria-current={active === id ? "location" : undefined}
                    className="gr-doc-nav-link"
                    href={`#${id}`}
                  >
                    {label}
                  </a>
                  {active === id && subsections[id]?.length ? (
                    <ul
                      className="sand-subsections"
                      aria-label={`${label} sections`}
                    >
                      {subsections[id].map((section) => (
                        <li key={section.id}>
                          <a
                            aria-current={
                              activeSection === section.id
                                ? "location"
                                : undefined
                            }
                            className="sand-subsection-link"
                            href={`#${section.id}`}
                          >
                            {section.label}
                          </a>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ))}
            </div>
          </nav>
        </aside>
        <SectionFab label="Guide contents">
          {chapters.map(({ id, label }) => (
            <a
              aria-current={active === id ? "location" : undefined}
              className="gr-fab-link sand-guide-link"
              href={`#${id}`}
              key={id}
            >
              {label}
            </a>
          ))}
        </SectionFab>
        <div className="sand-main">
          <figure
            aria-label="Sand grains form a dune and rearrange into a logic circuit on hover or keyboard focus."
            className="sand-cover"
            tabIndex={0}
          >
            <SandCircuitArtwork />
          </figure>
          <SandMarkup className="sand-intro" html={introduction} />
          <div className="post">
            <div className="stage-col">
              <SandStage />
            </div>
            <SandMarkup className="prose" html={body} />
          </div>
        </div>
      </div>
    </article>
  );
};
