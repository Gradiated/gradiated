import type { ReactElement } from "react";
import type { LucideIcon } from "lucide-react";

/**
 * The icon layer: Lucide geometry in the Gradiated voice.
 *
 * Lucide draws with round caps and joins; this system has no round corner
 * anywhere, so .gr-icon (base.css) re-strokes every glyph with butt caps
 * and miter joins, and weight comes from --icon-stroke rather than the
 * per-icon attribute — one dial for the whole set.
 *
 * Usage: import the glyph, hand it over.
 *
 *   import { ArrowUpRight } from "lucide-react";
 *   <Icon glyph={ArrowUpRight} />
 *
 * Icons size in em (--icon-size) so they track the type they sit beside;
 * pass `label` only when the icon carries meaning alone — unlabeled icons
 * are decorative and hidden from the tree.
 */
export const Icon = ({
  glyph: Glyph,
  label,
}: {
  glyph: LucideIcon;
  label?: string;
}): ReactElement => (
  <Glyph
    aria-hidden={label ? undefined : true}
    aria-label={label}
    className="gr-icon"
    role={label ? "img" : undefined}
  />
);
