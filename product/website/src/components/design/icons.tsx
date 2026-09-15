import type { ReactElement } from "react";

/**
 * The chevron-to-arrow affordance.
 *
 * At rest it is a chevron; on hover a shaft grows out of the chevron's back
 * and it becomes an arrow. The chevron head never moves or redraws — only the
 * shaft is revealed — so it reads as one mark extending rather than two icons
 * swapping. The shaft's path runs head-to-tail so the dash reveal travels
 * outward from the head, which is the direction the growth should feel.
 *
 * Styling and the hover transition live in base.css (`.gr-arrow`), so any
 * `.gr-button` can carry one. Paints with `currentColor`, and sized in `em`
 * so it tracks whatever type it sits beside.
 */
export const Arrow = (): ReactElement => (
  <svg
    aria-hidden
    className="gr-arrow"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 12 12"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path className="gr-arrow-shaft" d="M9 6H2" />
    <path className="gr-arrow-head" d="M5.5 2.5L9 6L5.5 9.5" />
  </svg>
);

/**
 * The view switch's two marks: rows, and a field of cells.
 *
 * Drawn on the same 16-unit grid with the same stroke so the swap reads as one
 * control changing state rather than two unrelated icons. Both paint with
 * `currentColor` and take their size in `em`, like the arrow above.
 */
/**
 * The view switch's two marks: rows with their text, and a field of panels.
 *
 * Lucide's `layout-list` and `layout-dashboard`, redrawn on this system's
 * 16-unit grid at its 1.5 stroke — same geometry, scaled by two thirds, so
 * they carry the weight of every other icon here rather than Lucide's 24-unit
 * stroke 2.
 *
 * They say more than the plain rules and squares they replace. A list is not
 * only rows: it is a thumbnail with lines of text beside it, which is what the
 * library's list view actually is. And the card view is not a uniform grid but
 * panels of two heights, which is what its dyptichs and triptychs are.
 */
export const ListIcon = (): ReactElement => (
  <svg
    aria-hidden
    className="gr-icon"
    fill="none"
    stroke="currentColor"
    strokeLinecap="round"
    strokeLinejoin="round"
    strokeWidth="1.5"
    viewBox="0 0 16 16"
    xmlns="http://www.w3.org/2000/svg"
  >
    <rect height="4.67" rx="0.67" width="4.67" x="2" y="2" />
    <rect height="4.67" rx="0.67" width="4.67" x="2" y="9.33" />
    <path d="M9.33 2.67H14" />
    <path d="M9.33 6H14" />
    <path d="M9.33 10H14" />
    <path d="M9.33 13.33H14" />
  </svg>
);

export const GridIcon = (): ReactElement => (
  <svg
    aria-hidden
    className="gr-icon"
    fill="none"
    stroke="currentColor"
    strokeLinejoin="round"
    strokeWidth="1.5"
    viewBox="0 0 16 16"
    xmlns="http://www.w3.org/2000/svg"
  >
    <rect height="6" rx="0.67" width="4.67" x="2" y="2" />
    <rect height="3.33" rx="0.67" width="4.67" x="9.33" y="2" />
    <rect height="6" rx="0.67" width="4.67" x="9.33" y="8" />
    <rect height="3.33" rx="0.67" width="4.67" x="2" y="10.67" />
  </svg>
);

/**
 * Contents: three entries, each with its page mark.
 *
 * Lucide's `table-of-contents`, redrawn on this system's 16-unit grid at its
 * 1.5 stroke rather than imported at 24 and 2 — the same mark, but it matches
 * the weight of every other icon beside it instead of arriving a third
 * heavier. The dots are `h.01` segments: a zero-length line with a round cap
 * IS a dot, so they cannot fall out of step with the rules' stroke.
 *
 * Lines stop short of the dots on purpose, as in the original: an entry and
 * its page number are two things, and a rule running into the dot would read
 * as a leader line.
 */
export const ContentsIcon = (): ReactElement => (
  <svg
    aria-hidden
    className="gr-icon"
    fill="none"
    stroke="currentColor"
    strokeLinecap="round"
    strokeLinejoin="round"
    strokeWidth="1.5"
    viewBox="0 0 16 16"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path d="M2 3.5h8.5M2 8h8.5M2 12.5h8.5" />
    <path d="M13.5 3.5h.01M13.5 8h.01M13.5 12.5h.01" />
  </svg>
);

/**
 * Sound on, sound off.
 *
 * The speaker body is the SAME path in both, so only the right-hand side
 * changes when the state flips — the mark reads as one control gaining or
 * losing its waves rather than two icons trading places. Muted is drawn as a
 * cross rather than a slash through the whole glyph: a slash has to cross the
 * body, which at this size closes up the cone and leaves a smudge.
 */
const SPEAKER_BODY = "M3.5 6.25h2L8.5 3.5v9L5.5 9.75h-2z";

export const SoundOnIcon = (): ReactElement => (
  <svg
    aria-hidden
    className="gr-icon"
    fill="none"
    stroke="currentColor"
    strokeLinecap="round"
    strokeLinejoin="round"
    strokeWidth="1.5"
    viewBox="0 0 16 16"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path d={SPEAKER_BODY} />
    <path d="M11 5.75a3.2 3.2 0 0 1 0 4.5" />
    <path d="M12.75 4a5.6 5.6 0 0 1 0 8" />
  </svg>
);

export const SoundOffIcon = (): ReactElement => (
  <svg
    aria-hidden
    className="gr-icon"
    fill="none"
    stroke="currentColor"
    strokeLinecap="round"
    strokeLinejoin="round"
    strokeWidth="1.5"
    viewBox="0 0 16 16"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path d={SPEAKER_BODY} />
    <path d="M11 6.5l3 3M14 6.5l-3 3" />
  </svg>
);
