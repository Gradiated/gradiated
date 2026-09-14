import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactElement, ReactNode } from "react";

/**
 * Band, Module and Columns — the layout half of the design system.
 *
 * The contract between them: spacing lives in the band and the module chrome,
 * NEVER in module content. A module carries no outer margin, and content
 * declares columns, not widths. This is what makes sections reorderable and
 * swappable by moving JSX alone.
 *
 * Every `index` prop is the module's position in the entrance stagger — keep
 * it equal to the module's visual order from the top of the page.
 */

type BandProps = {
  children: ReactNode;
};

/**
 * The band a module sits in. Holds the module's width and centring so the
 * module itself carries no outer margin — that is what makes modules
 * reorderable without touching their contents.
 */
export const Band = ({ children }: BandProps): ReactElement => (
  <div className="gr-band">{children}</div>
);

type ModuleProps = {
  /**
   * A full-bleed module spans the whole viewport instead of the band. Its
   * content still sits on the band grid — only the surface bleeds, so the
   * type keeps a single alignment across bled and banded sections.
   */
  bleed?: boolean;
  children: ReactNode;
  /** Extra class on the module, for page-specific hooks like clipping. */
  className?: string;
  /**
   * "viewport" pins the module to the first fold: exactly the region the
   * entrance reveals, so the opened cell and the module are the same surface.
   */
  height?: "viewport";
  /** Anchor target, so a section can be linked and tracked. */
  id?: string;
  /**
   * A surface set from themes.css — "taupe-2", "olive-3". Rebinds the colour
   * roles for this section only; everything inside follows.
   */
  theme?: string;
  /** Position in the entrance stagger. Only meaningful for modules in the
   *  first fold — see `reveal`. */
  index?: number;
  /**
   * How the module arrives.
   *
   * "entrance" joins the one-time opening, staggered by `index`. Right for
   * anything in the first fold, and wrong for everything else: a module below
   * the fold that animates on load has spent its reveal before the reader has
   * scrolled to it, and arrives already finished.
   *
   * "scroll" (the default for index > 0) holds until the module is actually
   * approaching the viewport.
   */
  reveal?: "entrance" | "scroll";
  title?: string;
};

/**
 * One swappable section. Every module is the same shape: a title row, then
 * content on the column grid. Spacing lives here, not in what it contains.
 */
export const Module = ({
  bleed = false,
  children,
  className,
  height,
  id,
  index = 0,
  reveal,
  theme,
  title,
}: ModuleProps): ReactElement => {
  const mode = reveal ?? (index === 0 ? "entrance" : "scroll");
  const ref = useRef<HTMLElement>(null);
  const [seen, setSeen] = useState(mode !== "scroll");

  useEffect(() => {
    if (mode !== "scroll") return;
    const node = ref.current;
    if (!node) return;

    /* Once only. A module that re-hides when it leaves the viewport turns
       scrolling back up into a second performance, which reads as the page
       forgetting it has already been seen. */
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        setSeen(true);
        observer.disconnect();
      },
      // Starts a little before the module arrives, so the movement is under
      // way by the time it is properly in view rather than beginning there.
      { rootMargin: "0px 0px -12% 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [mode]);
  const inner = (
    <>
      {title !== undefined && (
        <div className="gr-module-title">
          <h2 className="gr-section-title">{title}</h2>
        </div>
      )}
      {children}
    </>
  );

  return (
    <section
      className={[
        "gr-module",
        bleed ? "gr-module--bleed" : "",
        height === "viewport" ? "gr-module--viewport" : "",
        mode === "scroll" ? "gr-module--reveal" : "",
        mode === "scroll" && seen ? "gr-module--seen" : "",
        className ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-theme={theme}
      id={id}
      ref={ref}
      style={{ "--gr-index": index } as CSSProperties}
    >
      {/* Always wrapped, bleed or not: the entrance blurs the module's CONTENT
          rather than the module itself, because a filter on the surface would
          smear its own box edges against the seam lines. The wrapper is that
          content's handle. Bleed additionally constrains its width. */}
      <div className="gr-module-inner">{inner}</div>
    </section>
  );
};

type ColumnsProps = {
  children: ReactNode;
  /** Must divide --module-u evenly at every tier: 2, 3, 4, or 6. */
  count?: 2 | 3 | 4 | 6;
};

/**
 * The column grid. Zero gap by design — every column boundary lands on a
 * lattice line, and separation comes from the inset inside each column.
 */
export const Columns = ({
  children,
  count = 2,
}: ColumnsProps): ReactElement => (
  <div className="gr-cols" style={{ "--gr-cols": count } as CSSProperties}>
    {children}
  </div>
);
