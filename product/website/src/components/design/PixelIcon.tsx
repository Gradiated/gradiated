import type { CSSProperties, ReactElement } from "react";
import { PIXEL_ICONS } from "./pixel-icons.generated";

export type PixelIconName = keyof typeof PIXEL_ICONS;

/** Sized at whole pixels a square (--pixel) so the squares stay crisp. */
export const PixelIcon = ({
  className,
  label,
  name,
}: {
  className?: string;
  label?: string;
  name: PixelIconName;
}): ReactElement => {
  const { d, grid } = PIXEL_ICONS[name];

  return (
    <svg
      aria-hidden={label ? undefined : true}
      aria-label={label}
      className={className ? `gr-pixel-icon ${className}` : "gr-pixel-icon"}
      fill="currentColor"
      role={label ? "img" : undefined}
      shapeRendering="crispEdges"
      style={{ "--cells": grid } as CSSProperties}
      viewBox={`0 0 ${grid} ${grid}`}
    >
      <path d={d} />
    </svg>
  );
};
