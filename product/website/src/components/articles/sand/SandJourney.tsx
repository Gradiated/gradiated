import { memo, useRef } from "react";
import type { ReactElement } from "react";
import { SectionFab } from "../../design";
import { SandCircuitArtwork } from "../../design/SandCircuitArtwork";
import article, {
  contents,
} from "../../../../content/articles/sand/script.md?sand-article";
import { SandStage } from "./SandStage";
import { useActiveChapter, useSandAnimation } from "./useSandJourney";
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
  const active = useActiveChapter(hostRef, chapters);

  useSandAnimation(hostRef);

  return (
    <article className="sand-journey" ref={hostRef}>
      <div className="sand-layout">
        <aside className="sand-side gr-doc-side">
          <nav aria-label="Guide contents" className="gr-doc-nav">
            <div className="gr-doc-nav-group">
              <p className="gr-doc-nav-heading gr-label">Sand to Thought</p>
              {chapters.map(({ id, label }) => (
                <a
                  aria-current={active === id ? "location" : undefined}
                  className="gr-doc-nav-link"
                  href={`#${id}`}
                  key={id}
                >
                  {label}
                </a>
              ))}
            </div>
          </nav>
        </aside>
        <SectionFab label="Guide contents">
          {chapters.map(({ id, label }) => (
            <a
              aria-current={active === id ? "location" : undefined}
              className="gr-fab-link"
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
