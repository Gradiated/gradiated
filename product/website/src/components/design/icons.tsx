import type { ReactElement } from "react";
import { PixelIcon } from "./PixelIcon";

/**
 * The chevron-to-arrow affordance, drawn in squares like the pixel icons.
 *
 * At rest it is a chevron; on hover a shaft grows out of the chevron's back,
 * a square at a time, and it becomes an arrow. Styling and the hover
 * transition live in base.css (`.gr-arrow`), so any `.gr-button` can carry
 * one.
 */
export const Arrow = (): ReactElement => (
  <svg
    aria-hidden
    className="gr-arrow"
    fill="currentColor"
    shapeRendering="crispEdges"
    viewBox="0 0 7 5"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path className="gr-arrow-shaft" d="M0 2h5v1h-5z" />
    <path
      className="gr-arrow-head"
      d="M3 0h1v1h-1zM4 1h1v1h-1zM5 2h1v1h-1zM4 3h1v1h-1zM3 4h1v1h-1z"
    />
  </svg>
);

/** The view switch's two marks: rows, and a field of cells. */
export const ListIcon = (): ReactElement => <PixelIcon name="list" />;

export const GridIcon = (): ReactElement => <PixelIcon name="squares-four" />;

export const ContentsIcon = (): ReactElement => (
  <PixelIcon name="list-bullets" />
);

export const SoundOnIcon = (): ReactElement => (
  <PixelIcon name="speaker-high" />
);

export const SoundOffIcon = (): ReactElement => (
  <PixelIcon name="speaker-slash" />
);
