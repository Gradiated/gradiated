import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { CSSProperties, ReactElement, ReactNode } from "react";
import { ContentsIcon } from "./icons";

/**
 * The mobile form of a long page's section index: one button, bottom right.
 *
 * On a desktop the index is a sticky column beside the text, and it earns its
 * space by staying with you and showing every section at once. Stacked above
 * the content on a phone it is neither of those — a list of the headings you
 * are about to scroll past, costing a screen before the first sentence.
 *
 * So it becomes a button that stays put and opens the same list on demand.
 *
 * THE RING IS THE SCROLL POSITION. A button that floats over the page for the
 * whole article may as well say how much of it is left, and the ring costs
 * nothing to draw: it is the button's own edge. Progress is measured against
 * the document rather than the section list, because what a reader wants from
 * it is "how much of this is left", not "which heading is next" — the open
 * list already answers that.
 *
 * `pathLength="1"` is what keeps the arithmetic out of this: the circle's
 * length becomes 1 whatever its radius, so the dash offset IS the remaining
 * fraction and no circumference has to be computed or kept in step with the
 * CSS.
 *
 * PORTALLED OUT, and it has to be. Rendered where it is used, its nearest
 * ancestor is .gr-module-inner, which animates `filter` and `transform` — and
 * either of those makes an element a containing block for `position: fixed`
 * descendants. With the animation's fill mode holding `filter: blur(0)`
 * afterwards, that containing block is permanent, so the button was pinned to
 * the bottom of the MODULE rather than the viewport and came to rest beside
 * the apply button.
 *
 * It portals into .gr-substrate-content, which is where the Nav renders,
 * NOT to .gr-root. .gr-substrate has `isolation: isolate` and therefore is a
 * stacking context: anything portalled outside it paints above the whole
 * substrate whatever its z-index, so the button covered the nav's own drawer
 * no matter how low it was set. Sharing the nav's context is what lets
 * z-index decide between them — see .gr-fab in pages.css.
 */

export const SectionFab = ({
  /**
   * The list itself, supplied by the caller.
   *
   * The button does not build it, because what belongs in it differs: a
   * posting and an article want anchors to their own headings, while the docs
   * want ROUTER links to other pages — an <a href> there is a full document
   * navigation, which unmounts the app and replays every entrance. Give the
   * items the `gr-fab-link` class and they take the list's styling.
   */
  children,
  label = "Sections",
}: {
  children: ReactNode;
  label?: string;
}): ReactElement | null => {
  const [open, setOpen] = useState(false);
  const [read, setRead] = useState(0);
  const frame = useRef(0);

  /* Read on a frame, not on the event. Scroll fires far more often than the
     screen refreshes, and this writes state. */
  useEffect(() => {
    const measure = () => {
      frame.current = 0;
      const scrollable =
        document.documentElement.scrollHeight - window.innerHeight;
      setRead(scrollable > 0 ? Math.min(1, window.scrollY / scrollable) : 0);
    };
    const onScroll = () => {
      if (frame.current === 0) frame.current = requestAnimationFrame(measure);
    };

    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      if (frame.current !== 0) cancelAnimationFrame(frame.current);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  /* Out of the way once the footer arrives.
   *
   * The button sits in the bottom corner for the whole article, which is also
   * where the footer's own links end up — so at the foot of the page it stops
   * being a control and becomes something covering one. It leaves while the
   * footer is on screen and comes back when it is not.
   *
   * An observer on the footer rather than a scroll threshold: the footer's
   * height is whatever it is, and "is the footer visible" is the actual
   * question. */
  const [atFooter, setAtFooter] = useState(false);
  useEffect(() => {
    const footer = document.querySelector(".gr-footer");
    if (!footer) return;
    const observer = new IntersectionObserver(
      ([entry]) => setAtFooter(entry.isIntersecting),
      { threshold: 0 },
    );
    observer.observe(footer);
    return () => observer.disconnect();
  }, []);

  /* Nothing left open behind it — a list that fades out with the button would
     otherwise be waiting, still open, when the reader scrolls back up. */
  useEffect(() => {
    if (atFooter) setOpen(false);
  }, [atFooter]);

  /* Closes on its own once the reader has chosen. Escape as well, because an
     open list covers the text it is about. */
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  /* Portalled after mount, not during render: there is no document on the
     server, and rendering the button into the page first and moving it after
     would be a hydration mismatch. */
  const [host, setHost] = useState<HTMLElement | null>(null);
  useEffect(() => {
    setHost(
      document.querySelector<HTMLElement>(".gr-substrate-content") ??
        document.querySelector<HTMLElement>(".gr-root"),
    );
  }, []);

  if (!host) return null;

  return createPortal(
    <div
      className={`gr-fab${open ? " gr-fab--open" : ""}${
        atFooter ? " gr-fab--away" : ""
      }`}
      style={{ "--read": read } as CSSProperties}
    >
      {/* Above the button in the DOM so it opens upward without the list
          having to be positioned from the bottom of the viewport. */}
      {open ? (
        /* Closed from the list rather than from each item: the caller's links
           should not each have to remember to dismiss the thing they are
           inside, and a click anywhere in here means the reader has chosen. */
        <nav
          aria-label={label}
          className="gr-fab-list"
          onClick={() => setOpen(false)}
        >
          {children}
        </nav>
      ) : null}

      <button
        aria-expanded={open}
        aria-label={open ? `Close ${label.toLowerCase()}` : label}
        className="gr-fab-button"
        onClick={() => setOpen((was) => !was)}
        type="button"
      >
        <svg aria-hidden className="gr-fab-ring" viewBox="0 0 44 44">
          <circle className="gr-fab-ring-track" cx="22" cy="22" r="20" />
          <circle
            className="gr-fab-ring-read"
            cx="22"
            cy="22"
            pathLength="1"
            r="20"
          />
        </svg>
        <ContentsIcon />
      </button>
    </div>,
    host,
  );
};
