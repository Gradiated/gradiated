import { useEffect, useRef, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import { CodeBlock } from "./CodeBlock";
import { RadiusSwitcher } from "./RadiusSwitcher";

/**
 * The reference page's app shell: a two-pane screen that pins below the fold
 * and holds the viewport until every section has been read.
 *
 * The fold is a statement and scrolls normally. Everything after it is a tool,
 * so it behaves like one — the shell fills the viewport, the index stays put,
 * and the content pane moves rather than the page growing to the length of
 * every specimen stacked end to end.
 *
 * THE PIN. The shell is `position: sticky` inside a RUN element that is one
 * viewport tall plus the pane's own scrollable distance. Scrolling the page
 * therefore does two things in sequence with no seam between them: while the
 * run is passing, the shell stays put and the page's scroll offset is spent
 * driving the pane; once the pane is exhausted the run ends, the shell
 * unsticks, and the footer arrives normally.
 *
 * That is the reason the pane does not scroll itself (`overflow: hidden`).
 * A pane that also responded to the wheel would fight the page for the same
 * gesture — two scrollers, one input — and the two positions would drift
 * apart. There is exactly one scroller on this page, the window, and the
 * pane's position is a pure function of it. Everything that wants to move the
 * pane therefore moves the WINDOW: the index links, the exits, all of it.
 *
 * Scroll tracking still observes sections against the CONTENT PANE, not the
 * viewport, because the pane is what moves beneath a stationary window.
 *
 * This is chrome for /style/, not part of the system it documents.
 */

export type Section = { id: string; label: string };

/** A named run of sections. Two today: the primitives, then what is built from
 *  them — an order that only reads as an argument if the index states it. */
export type Group = { label: string; sections: Section[] };

export const Storybook = ({
  children,
  groups,
}: {
  children: ReactNode;
  groups: Group[];
}): ReactElement => {
  const sections = groups.flatMap((group) => group.sections);
  const runRef = useRef<HTMLDivElement>(null);
  const paneRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(sections[0]?.id ?? "");
  const [collapsed, setCollapsed] = useState(false);

  /* The pin. Two jobs, kept together because they share one measurement:
     publish the run's extra height, and spend the page's scroll on the pane.

     --book-run is the pane's scrollable distance, so the run is exactly long
     enough to read the pane through and not a pixel longer. It is remeasured
     whenever the pane's content or the viewport changes — the radius control,
     the theme tabs and a window resize all change that height. */
  useEffect(() => {
    const run = runRef.current;
    const pane = paneRef.current;
    if (!run || !pane) return;

    let distance = 0;
    let frame = 0;

    const measure = () => {
      distance = Math.max(0, pane.scrollHeight - pane.clientHeight);
      run.style.setProperty("--book-run", `${distance}px`);
      apply();
    };

    const apply = () => {
      frame = 0;
      // The run's top in document space. Read fresh rather than cached: the
      // fold above it is animated, and anything above the run moving would
      // otherwise leave the pane offset by the difference.
      const top = run.getBoundingClientRect().top + window.scrollY;
      const travelled = window.scrollY - top;
      pane.scrollTop = Math.min(Math.max(travelled, 0), distance);
    };

    // Coalesced to one write per frame. Scroll fires far faster than the
    // screen refreshes, and each handler here writes layout.
    const onScroll = () => {
      if (frame === 0) frame = requestAnimationFrame(apply);
    };

    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    const observer = new ResizeObserver(measure);
    observer.observe(pane);
    for (const child of pane.children) observer.observe(child);

    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    const pane = paneRef.current;
    if (!pane) return;
    const nodes = sections
      .map(({ id }) => document.getElementById(id))
      .filter((n): n is HTMLElement => n !== null);
    if (nodes.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible) setActive(visible.target.id);
      },
      { root: pane, rootMargin: "0px 0px -70% 0px" },
    );
    for (const node of nodes) observer.observe(node);
    return () => observer.disconnect();
    // groups, not the flattened list: the flatten is a new array every render.
  }, [groups]);

  /* Jumping to a section means moving the WINDOW to the point in the run where
     the pin would have scrolled that section into view — not calling
     scrollIntoView on the section, which would move a pane the window is not
     tracking and desync the two on the reader's very next wheel click. */
  const go = (id: string) => {
    const run = runRef.current;
    const pane = paneRef.current;
    const target = document.getElementById(id);
    if (!run || !pane || !target) return;
    const offset =
      pane.scrollTop +
      (target.getBoundingClientRect().top - pane.getBoundingClientRect().top);
    window.scrollTo({
      behavior: "smooth",
      top: run.getBoundingClientRect().top + window.scrollY + offset,
    });
  };

  return (
    <section
      aria-label="Design system reference"
      className="gr-book-run"
      ref={runRef}
    >
      <div className={`gr-book${collapsed ? " gr-book--collapsed" : ""}`}>
        <aside className="gr-book-aside">
          {/* The control leads, so it holds the same position whether or not
              the label is there to follow it — collapsing does not move it. */}
          <div className="gr-book-aside-head">
            <button
              aria-expanded={!collapsed}
              aria-label={collapsed ? "Expand index" : "Collapse index"}
              className="gr-book-collapse"
              onClick={() => setCollapsed((c) => !c)}
              type="button"
            >
              {collapsed ? "»" : "«"}
            </button>
            <span className="gr-label">Contents</span>
          </div>

          <nav aria-label="Sections" className="gr-book-index">
            {groups.map((group) => (
              <section className="gr-book-group" key={group.label}>
                <h2 className="gr-label gr-book-group-title">{group.label}</h2>
                <ol>
                  {group.sections.map((section) => (
                    <li key={section.id}>
                      <button
                        aria-current={active === section.id ? "true" : undefined}
                        className="gr-book-link"
                        onClick={() => go(section.id)}
                        type="button"
                      >
                        {section.label}
                      </button>
                    </li>
                  ))}
                </ol>
              </section>
            ))}
          </nav>

          <div className="gr-book-controls">
            <span className="gr-label">Radius</span>
            <RadiusSwitcher />
          </div>

          <div className="gr-book-exits">
            <button
              className="gr-book-link"
              onClick={() =>
                window.scrollTo({ behavior: "smooth", top: 0 })
              }
              type="button"
            >
              ↑ Top
            </button>
            <button
              className="gr-book-link"
              onClick={() =>
                window.scrollTo({
                  behavior: "smooth",
                  top: document.body.scrollHeight,
                })
              }
              type="button"
            >
              ↓ Footer
            </button>
          </div>
        </aside>

        <div className="gr-book-pane" ref={paneRef}>
          {children}
        </div>
      </div>
    </section>
  );
};

/**
 * One documented thing, in reading order: what it is, what it looks like, how
 * to use it.
 *
 * The description sits under the title rather than after the specimen, because
 * it is the thing that tells you whether to keep reading. Placed below, it only
 * ever gets read by someone who already worked out what they were looking at.
 */
export const Spec = ({
  children,
  code,
  id,
  notes,
  title,
}: {
  children: ReactNode;
  code?: string;
  id: string;
  notes?: ReactNode;
  title: string;
}): ReactElement => (
  <article className="gr-spec" id={id}>
    <header className="gr-spec-head">
      <h2 className="gr-section-title">{title}</h2>
      {notes ? <p className="gr-spec-notes">{notes}</p> : null}
    </header>

    <div className="gr-spec-demo">{children}</div>

    {code ? <CodeBlock code={code} /> : null}
  </article>
);

/**
 * A subsection of a spec: same shape one level down.
 *
 * Colour is the reason this exists. The ramp, the gradients and the themes
 * are three views of one subject and belong under one heading, but each has
 * its own demo and its own line of code to copy — so they cannot simply be
 * concatenated into a single spec body.
 *
 * Headed by h3, under the spec's h2, so the nesting is real to a screen reader
 * and not only to the eye.
 */
export const Part = ({
  children,
  code,
  notes,
  title,
}: {
  children: ReactNode;
  code?: string;
  notes?: ReactNode;
  title: string;
}): ReactElement => (
  <section className="gr-part">
    <h3 className="gr-heading">{title}</h3>
    {notes ? <p className="gr-part-notes">{notes}</p> : null}

    <div className="gr-spec-demo">{children}</div>

    {code ? <CodeBlock code={code} /> : null}
  </section>
);
