import { useEffect, useState } from "react";
import type { ReactElement, RefObject } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";

type Heading = { id: string; text: string; level: 2 | 3 };

const readHeadings = (root: HTMLElement): Heading[] =>
  Array.from(root.querySelectorAll<HTMLElement>("h2[id], h3[id]")).map(
    (element) => ({
      id: element.id,
      text: (element.textContent ?? "").replace(/#$/, "").trim(),
      level: element.tagName === "H2" ? 2 : 3,
    }),
  );

/* The headings on the page and which one the reader is in. */
const useHeadings = (
  article: RefObject<HTMLElement | null>,
  path: string,
): { headings: Heading[]; current: string | null } => {
  const [headings, setHeadings] = useState<Heading[]>([]);
  const [current, setCurrent] = useState<string | null>(null);

  useEffect(() => {
    const root = article.current;
    if (!root) return;

    setHeadings(readHeadings(root));
    const update = () => {
      const offset = 120;
      let active: string | null = null;
      for (const element of root.querySelectorAll<HTMLElement>(
        "h2[id], h3[id]",
      )) {
        if (element.getBoundingClientRect().top - offset <= 0) {
          active = element.id;
        } else break;
      }
      setCurrent(active);
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, [article, path]);

  return { headings, current };
};

const TocList = ({
  headings,
  current,
}: {
  headings: Heading[];
  current: string | null;
}): ReactElement => (
  <ol className="gr-doc-toc-list">
    {headings.map((heading) => (
      <li data-level={heading.level} key={heading.id}>
        <a
          aria-current={heading.id === current ? "location" : undefined}
          href={`#${heading.id}`}
        >
          {heading.text}
        </a>
      </li>
    ))}
  </ol>
);

/** "On this page": a sticky column on wide screens, a fold under the lede
    elsewhere. Both are filled in after hydration. */
export const DocsToc = ({
  article,
  path,
}: {
  article: RefObject<HTMLElement | null>;
  path: string;
}): ReactElement | null => {
  const { headings, current } = useHeadings(article, path);
  const [slot, setSlot] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const root = article.current;
    if (!root) return;

    const after =
      root.querySelector(".gr-doc-lead") ?? root.querySelector("h1");
    if (!after) return;

    const element = document.createElement("div");
    element.className = "gr-doc-toc-inline";
    after.after(element);
    setSlot(element);
    return () => {
      element.remove();
      setSlot(null);
    };
  }, [article, path]);

  if (headings.length < 3) return null;

  return (
    <>
      <nav aria-label="On this page" className="gr-doc-toc">
        <p className="gr-doc-toc-title">On this page</p>
        <TocList current={current} headings={headings} />
      </nav>
      {slot
        ? createPortal(
            <details className="gr-doc-toc-fold">
              <summary>On this page</summary>
              <TocList
                current={current}
                headings={headings.filter((heading) => heading.level === 2)}
              />
            </details>,
            slot,
          )
        : null}
    </>
  );
};

/** Previous and next, in the order of the docs navigation. */
export const DocsPager = ({
  article,
  previous,
  next: following,
}: {
  article: RefObject<HTMLElement | null>;
  previous?: { href: string; label: string };
  next?: { href: string; label: string };
}): ReactElement | null => {
  const [linked, setLinked] = useState<string[]>([]);

  /* A page's own "what next" block already names its next page; don't say
     it twice. */
  useEffect(() => {
    const links =
      article.current?.querySelectorAll<HTMLAnchorElement>(".gr-doc-next a");
    setLinked(Array.from(links ?? [], (link) => new URL(link.href).pathname));
  }, [article, following?.href]);

  const next =
    following && !linked.includes(following.href) ? following : undefined;
  if (!previous && !next) return null;

  return (
    <nav aria-label="Previous and next page" className="gr-doc-pager">
      {previous ? (
        <Link rel="prev" to={previous.href}>
          <small>Previous</small>
          <span>{previous.label}</span>
        </Link>
      ) : (
        <span />
      )}
      {next ? (
        <Link data-next="true" rel="next" to={next.href}>
          <small>Next</small>
          <span>{next.label}</span>
        </Link>
      ) : null}
    </nav>
  );
};
