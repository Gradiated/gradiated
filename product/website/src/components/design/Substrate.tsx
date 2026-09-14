import { useEffect, useLayoutEffect, useState } from "react";
import type { CSSProperties, ReactElement, ReactNode } from "react";
import { useLattice } from "./useLattice";
import type { Lattice } from "./useLattice";
import { applyTheme, readStoredTheme } from "../../theme";

/* useLayoutEffect warns when React renders on the server, where it cannot run.
   The static build renders every page there, so pick the one that is safe. */
const useIsomorphicLayoutEffect =
  typeof window === "undefined" ? useEffect : useLayoutEffect;

/**
 * When the lattice is removed. It must outlast the lines' RETRACTION, not just
 * the draw: unmounting while anything is still on screen is what made the
 * lines vanish mid-frame. The retraction ends at
 * --entrance-line-out-lead + --stagger-cap + --entrance-line-out = 3670ms, so
 * this clears it by 330ms. Raise it if any of those three grow.
 */
const ENTRANCE_MS = 4000;

/**
 * The entrance lattice: the grid the cell is pried out of.
 *
 * Lines are anchored to the CELL — vertical lines at ±(u/2 + k·u) from centre,
 * horizontal lines the same about the viewport's middle — so the cell is a
 * true cell with no line running through it. The opening shoves every line
 * outward by exactly the distance its own edge travels (--shift-x horizontally,
 * --ty vertically), so the bounding lines ride the opening's edges and
 * everything keeps its u-spacing as it exits. The opening is full-bleed: every
 * line leaves the viewport, which is why this lattice only exists while the
 * entrance is playing and can be removed afterwards with nothing popping.
 */
const OpeningLattice = ({
  lattice,
  viewportHeight,
}: {
  lattice: Lattice;
  viewportHeight: number;
}): ReactElement => {
  const { u, width } = lattice;
  const centreX = width / 2;
  const centreY = viewportHeight / 2;
  const columns = Math.ceil(width / 2 / u) + 2;
  const rows = Math.ceil(viewportHeight / 2 / u) + 2;

  // Both edges of the fold travel the same distance: the top edge to the
  // viewport top, the bottom edge to the viewport bottom.
  const travelY = Math.round(viewportHeight / 2 - u / 2);

  const lines: ReactElement[] = [];
  for (const sign of [-1, 1] as const) {
    for (let k = 0; k < columns; k += 1) {
      lines.push(
        <span
          className="gr-line-v"
          key={`v${sign}${k}`}
          style={
            {
              "--i": k,
              "--sign": sign,
              left: `${Math.round(centreX + sign * (u / 2 + k * u))}px`,
            } as CSSProperties
          }
        />,
      );
    }
    for (let k = 0; k < rows; k += 1) {
      lines.push(
        <span
          className="gr-line-h"
          key={`h${sign}${k}`}
          style={
            {
              "--i": k,
              "--sign": sign,
              "--ty": `${travelY}px`,
              top: `${Math.round(centreY + sign * (u / 2 + k * u))}px`,
            } as CSSProperties
          }
        />,
      );
    }
  }

  return (
    <div aria-hidden className="gr-lattice gr-lattice--open gr-lattice--entering">
      {lines}
    </div>
  );
};

/**
 * The resting lattice drawn as characters rather than hairlines.
 *
 * A glyph sits at every lattice intersection, so the grid reads as technical
 * drawing paper or a chip floorplan rather than as ruled lines.
 *
 * Structured as one element per COLUMN, each holding a newline-separated run
 * of glyphs with line-height pinned to the unit — so the characters land on
 * intersections by the text engine's own layout rather than by positioning
 * thousands of elements. A full page at 24px would otherwise be ~7,000 nodes.
 *
 * The reveal is a clip rather than the hairline version's scaleY, which would
 * squash the glyphs instead of uncovering them.
 *
 * Trade-off worth knowing: these are antialiased glyphs, so they will never be
 * as crisp as the 1px lines, and they shift subtly when the font loads.
 */
type SubstrateProps = {
  children: ReactNode;
};

/**
 * The wafer.
 *
 * The entrance pries one cell of the lattice open — vertical edges pulled
 * apart, then top and bottom — until what it housed fills the first fold,
 * full bleed. The opening displaces the grid rather than covering it, and
 * pushes every line out of the viewport; the resting grid belongs to scroll
 * instead, drawing itself in as the reader moves down the page.
 */
export const Substrate = ({ children }: SubstrateProps): ReactElement => {
  const { lattice, ref } = useLattice<HTMLDivElement>();
  const [entering, setEntering] = useState(true);
  const [viewportHeight, setViewportHeight] = useState(0);

  useEffect(() => {
    setViewportHeight(window.innerHeight);
  }, []);

  /* Put the reader's theme on this page's root.
   *
   * Here rather than in the footer's selector because the attribute has to sit
   * on .gr-root, and this is what renders it — a NEW one on every page. The
   * selector applied it once on its own mount, so the choice was lost the
   * moment a navigation replaced the root it had been written to.
   *
   * Before paint, so a reader on the dark theme does not get a frame of
   * limestone on each page. useLayoutEffect is client-only by nature; on the
   * server there is no root to write to and nothing to flash. */
  useIsomorphicLayoutEffect(() => {
    const root = ref.current;
    if (root) applyTheme(root, readStoredTheme());
  }, []);

  /* Mirror the theme's ground onto the document.
     
     The legacy stylesheet paints `body { background: var(--paper) }` — a fixed
     #e8e2d5 that knows nothing about themes. The substrate covers it on the
     page itself, so it is invisible until it is not: overscroll bounce, the
     area beyond a short page, and the browser's own UI all read the document's
     colour. On a dark theme that is a band of limestone at the top of a scroll.

     Written from the computed value rather than declared in CSS, because the
     theme's variables live on .gr-root and body is outside it. Restored on
     unmount so this never leaks onto a legacy page. */
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const previous = document.body.style.background;

    const apply = () => {
      document.body.style.background = getComputedStyle(root)
        .getPropertyValue("--color-substrate")
        .trim();
    };
    apply();

    const observer = new MutationObserver(apply);
    observer.observe(root, {
      attributeFilter: ["data-theme"],
      attributes: true,
    });

    return () => {
      observer.disconnect();
      document.body.style.background = previous;
    };
  }, [ref]);

  // The entrance plays once. Without this, any resize that changes the line
  // count would remount the lines and replay the whole animation.
  useEffect(() => {
    const timer = setTimeout(() => setEntering(false), ENTRANCE_MS);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="gr-root" ref={ref}>
      <div
        className={`gr-substrate${entering ? " gr-substrate--entering" : ""}`}
      >
        {entering && lattice.width > 0 && viewportHeight > 0 && (
          <OpeningLattice lattice={lattice} viewportHeight={viewportHeight} />
        )}
        <div className="gr-substrate-content">{children}</div>
      </div>
    </div>
  );
};
