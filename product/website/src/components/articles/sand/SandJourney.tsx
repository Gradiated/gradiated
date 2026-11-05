import { memo, useMemo, useRef } from "react";
import type { ReactElement } from "react";
import { SectionFab } from "../../design";
import { useRailDocNav } from "../../design/RailShell";
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

  /* The site rail carries the guide's contents — the journey is the
     doc mode's richest case: chapters with live subsections unfolding
     under the active one, tracked by the scroll spy. */
  const railGroups = useMemo(
    () => [
      {
        items: chapters.flatMap(({ id, label }) => [
          { href: `#${id}`, label },
          ...(active === id
            ? (subsections[id] ?? [])
                .filter((section) => section.id !== id)
                .map((section) => ({
                  href: `#${section.id}`,
                  label: section.label,
                  sub: true,
                }))
            : []),
        ]),
      },
    ],
    [active, subsections],
  );
  useRailDocNav({
    title: "Sand to Thought",
    current: `#${activeSection ?? active ?? ""}`,
    groups: railGroups,
    backHref: "/library/",
  });

  return (
    <article className="sand-journey" ref={hostRef}>
      <div className="sand-layout">
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
            aria-label="Sand grains form a dune, then gather into a neural network on hover or keyboard focus. Each layer’s sand rearranges in turn."
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
