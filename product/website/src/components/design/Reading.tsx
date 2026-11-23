import { useEffect, useRef, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import type { StoryCover } from "./Story";
import { Arrow } from "./icons";
import { useRailBack } from "./RailShell";
import { SectionFab } from "./SectionFab";
import { WaferArtwork } from "./WaferArtwork";

/**
 * A page you read.
 *
 * Two columns, and they do different jobs. The right is the piece: title,
 * standfirst, prose, on one measure. The left is everything ABOUT the piece —
 * its cover, what it belongs to, who wrote it, and where you are in it.
 * Keeping the apparatus out of the reading column is what lets the prose keep
 * a single measure from the first line to the last.
 *
 * The section list is built from the prose's own headings after it renders,
 * rather than being passed in. The content is MDX in one case and JSX in the
 * other, so there is no shared shape to read a table of contents out of — but
 * both produce h2s in the DOM, and that is the same thing a reader is using to
 * navigate. It also means a piece cannot have a contents list that disagrees
 * with its own headings.
 */

type Section = { id: string; text: string };
type ReadingLink = { label: string; href: string };
type ReadingNote = { title: string; items: string[] };
const host = (href: string) => new URL(href).hostname.replace(/^www\./, "");

/** `Some Heading!` -> `some-heading`, for the anchor. */
const slug = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^\w]+/g, "-")
    .replace(/^-|-$/g, "");

export const Reading = ({
  author,
  authorTitle,
  byline,
  bylineDateTime,
  children,
  art,
  cover,
  lede,
  links = [],
  note,
  tags = [],
  title,
}: {
  author?: string;
  authorTitle?: string;
  byline?: string;
  bylineDateTime?: string;
  children: ReactNode;
  /** The tall crop of the piece's real artwork. Wins over `cover`. */
  art?: string;
  cover?: StoryCover;
  lede?: string;
  links?: ReadingLink[];
  note?: ReadingNote;
  /** What the piece belongs to — its collection, then its section. */
  tags?: string[];
  title: string;
}): ReactElement => {
  /* The rail draws "back"; the page draws nothing above its content. */
  useRailBack({ href: "/library/", label: "Library" });
  const proseRef = useRef<HTMLDivElement>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [active, setActive] = useState<string>();

  useEffect(() => {
    const prose = proseRef.current;
    if (!prose) return;

    const headings = [...prose.querySelectorAll("h2")];
    /* The heading owns its anchor. Authors write prose, not ids. */
    headings.forEach((heading) => {
      if (!heading.id) heading.id = slug(heading.textContent ?? "");
    });
    setSections(
      headings.map((heading) => ({
        id: heading.id,
        text: heading.textContent ?? "",
      })),
    );

    /* Which section the reader is IN, not which one is nearest the top: the
       band is the upper third of the viewport, so a heading counts as current
       from the moment it reaches the reading position until the next one
       does. */
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting);
        if (visible.length > 0) setActive(visible[0].target.id);
      },
      { rootMargin: "0px 0px -66% 0px", threshold: 0 },
    );
    headings.forEach((heading) => observer.observe(heading));
    return () => observer.disconnect();
  }, [children]);

  return (
    <article className="gr-read">
      <div className="gr-read-grid">
        <aside className="gr-read-side">
          <span
            aria-hidden
            className="gr-read-cover"
            style={art ? { backgroundImage: `url(${art})` } : undefined}
          >
            {!art && cover ? <WaferArtwork options={cover} /> : null}
          </span>

          {author ? (
            <p className="gr-read-author">
              {author}
              {authorTitle ? (
                <span className="gr-label gr-read-author-title">
                  {authorTitle}
                </span>
              ) : null}
            </p>
          ) : null}

          {/* Absent rather than empty when a piece has no headings — a
              contents list of one item tells the reader nothing. */}
          {sections.length > 1 ? (
            <nav aria-label="Sections" className="gr-read-sections">
              {sections.map((section) => (
                <a
                  aria-current={section.id === active ? "true" : undefined}
                  className="gr-read-section"
                  href={`#${section.id}`}
                  key={section.id}
                >
                  {section.text}
                </a>
              ))}
            </nav>
          ) : null}

          {links.length > 0 ? (
            <nav aria-label="Links" className="gr-read-links">
              <p className="gr-label gr-read-links-title">Links</p>
              {links.map((link) => (
                <a
                  className="gr-read-link"
                  href={link.href}
                  key={link.href}
                  rel="noreferrer"
                  target="_blank"
                >
                  <span className="gr-read-link-label">
                    {link.label}
                    <span aria-hidden className="gr-read-link-arrow">
                      ↗
                    </span>
                  </span>
                  <span className="gr-read-link-host">{host(link.href)}</span>
                </a>
              ))}
            </nav>
          ) : null}

          {note ? (
            <section
              aria-label={note.title}
              className="gr-read-links gr-read-note"
            >
              <p className="gr-label gr-read-links-title">{note.title}</p>
              <ul className="gr-read-note-items">
                {note.items.map((item) => (
                  <li key={item}>
                    {item
                      .split(/\*\*(.+?)\*\*/)
                      .map((part, index) =>
                        index % 2 === 1 ? (
                          <strong key={index}>{part}</strong>
                        ) : (
                          part
                        ),
                      )}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </aside>

        {/* The same headings as the aside's list, as a button on a phone —
            where that list is stacked above the prose and only repeats what
            the reader is about to scroll through. Hidden above the wide tier;
            see pages.css. */}
        {sections.length > 1 ? (
          <SectionFab label="Contents">
            {sections.map((section) => (
              <a
                className="gr-fab-link"
                href={`#${section.id}`}
                key={section.id}
              >
                {section.text}
              </a>
            ))}
          </SectionFab>
        ) : null}

        <div className="gr-read-body">
          {byline ? (
            <p className="gr-read-byline">
              {bylineDateTime ? (
                <time dateTime={bylineDateTime}>{byline}</time>
              ) : (
                byline
              )}
            </p>
          ) : null}
          <h1 className="gr-read-title">{title}</h1>
          {lede ? <p className="gr-read-lede">{lede}</p> : null}
          <div className="gr-prose" ref={proseRef}>
            {children}
          </div>
        </div>
      </div>
    </article>
  );
};
