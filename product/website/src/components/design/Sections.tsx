import {
  Children,
  type CSSProperties,
  type ReactElement,
  type ReactNode,
} from "react";
import { Arrow } from "./icons";
import { Reveal } from "./Reveal";

/**
 * Page-level compositions — the shapes the product pages are built from.
 *
 * These sit above Module/Columns and below a page. Every one of them appeared
 * in at least two of the four product designs, which is the bar for living
 * here rather than in the page that needed it: a centred hero, a showpiece
 * panel, a feature triplet, a row of cards.
 *
 * They take content and nothing else. No section decides its own spacing or
 * ground — that is the Module's job, exactly as it is for hand-written
 * sections, so these can be reordered and re-themed like anything else.
 */

/**
 * A title's lines, each with the delay index its first word starts on.
 *
 * The title is one sentence that happens to be set on several lines, so its
 * entrance is one run of words. Each line is a separate Reveal — the author
 * chose the breaks — and a Reveal counts from zero, so without the running
 * total "Make the / model yours." animated as two pairs in lockstep rather
 * than as four words in sequence.
 */
const heroLines = (title: string | string[]) => {
  const lines = Array.isArray(title) ? title : [title];
  let counted = 0;
  return lines.map((line) => {
    const from = counted;
    counted += line.split(/\s+/).filter(Boolean).length;
    return { from, line };
  });
};

/**
 * The centred fold: an optional eyebrow, a title, a standfirst, an optional
 * action.
 *
 * Two columns: the claim on the left, what it means on the right. A centred
 * stack made the title wrap to a narrow measure and pushed the standfirst
 * below it, so the eye travelled down through the same width twice; side by
 * side, the title can wrap to two lines at a size worth reading and the
 * standfirst starts where it stops.
 *
 * Aligned on FIRST BASELINES rather than at the top of each box. The title is
 * three times the standfirst's size, so aligning boxes leaves the two first
 * lines at visibly different heights — the baseline is the line a reader sees.
 */
export const PageHero = ({
  action,
  secondaryAction,
  beside = false,
  eyebrow,
  lede,
  media,
  title,
}: {
  /**
   * Puts the picture in its own column with the whole text block beside it,
   * rather than above a title-and-standfirst pair.
   *
   * For a hero whose picture is TALL: a wide object above the type is a band
   * across the page, but a tall one wastes the width beside it. It also lets
   * the standfirst run to several paragraphs without having to line up with
   * anything — the other layout pairs title and standfirst on a shared floor,
   * which only works while the two are close in height.
   */
  beside?: boolean;
  /** `tone` picks the button; defaults to the primary. */
  action?: { href: string; label: string; tone?: "main" | "secondary" };
  secondaryAction?: {
    href: string;
    label: string;
    tone?: "main" | "secondary";
  };
  eyebrow?: string;
  lede?: ReactNode;
  /** Sits above the eyebrow — the hardware page leads with its chip. */
  media?: ReactNode;
  /**
   * A string wraps to the measure. An ARRAY breaks where the author says.
   *
   * Three titles of different lengths cannot share one measure and all land on
   * two lines — "You set the pace. And the price." broke mid-sentence at the
   * width that wrapped the other two correctly. Where a headline breaks is a
   * writing decision, so it is made in the page rather than chased with a
   * max-width.
   */
  title: string | string[];
}): ReactElement => (
  <div className={`gr-page-hero${beside ? " gr-page-hero--beside" : ""}`}>
    {/* Spans both columns: it is the page's picture, not the title's. */}
    {media ? <div className="gr-page-hero-media">{media}</div> : null}

    <div className="gr-page-hero-claim">
      {eyebrow ? <p className="gr-label">{eyebrow}</p> : null}
      <h1 className="gr-hero">
        {heroLines(title).map(({ from, line }) => (
          <span className="gr-hero-line" key={line}>
            <Reveal by="word" from={from}>
              {line}
            </Reveal>
          </span>
        ))}
      </h1>
    </div>

    {/* The standfirst and the step that follows from it, together — a reader
        who is convinced by the copy should not have to look back across the
        page for what to do about it. */}
    <div className="gr-page-hero-say">
      {lede
        ? Children.toArray(lede).map((paragraph, index) => (
            <p className="gr-lede gr-muted gr-page-hero-lede" key={index}>
              {paragraph}
            </p>
          ))
        : null}
      {action ? (
        <a
          className={`gr-button gr-button--${action.tone ?? "main"}`}
          href={action.href}
        >
          {action.label}
          <Arrow />
        </a>
      ) : null}
      {secondaryAction ? (
        <div>
          <a
            className={`gr-button gr-button--${secondaryAction.tone ?? "main"}`}
            href={secondaryAction.href}
          >
            {secondaryAction.label}
            <Arrow />
          </a>
        </div>
      ) : null}
    </div>
  </div>
);

/**
 * The first fold: a statement and the thing it is about, in one viewport.
 *
 * The showpiece sits INSIDE the fold and is cropped by it, rather than
 * following it as a section of its own. That is the whole composition: the
 * page's claim and its evidence arrive together, and the evidence is
 * unmistakably larger than the screen.
 *
 * The fade at the foot is the fold's, not the showpiece's — it runs to the
 * page's own ground across the full width, so the crop reads as the viewport
 * ending rather than as a panel stopping. A showpiece inside a fold therefore
 * gives up its own fade; two would compound into a band.
 */
export const Fold = ({
  children,
  ...hero
}: {
  action?: { href: string; label: string; tone?: "main" | "secondary" };
  secondaryAction?: {
    href: string;
    label: string;
    tone?: "main" | "secondary";
  };
  children?: ReactNode;
  /** Passed through to PageHero. */
  beside?: boolean;
  eyebrow?: string;
  lede?: ReactNode;
  media?: ReactNode;
  /** Passed through to PageHero — an array breaks where the author says. */
  title: string | string[];
}): ReactElement => (
  <div className="gr-fold">
    <PageHero {...hero} />
    {children ? <div className="gr-fold-media">{children}</div> : null}
  </div>
);

/**
 * The one big thing on a page: a code sample, a screenshot, a diagram.
 *
 * It is cropped rather than scaled — the panel is a window onto something
 * larger, and the fade at its foot says so. Shrinking a screenshot until it
 * fits makes its type unreadable and its detail decorative; cropping keeps
 * both at full size and admits there is more.
 */
export const Showpiece = ({
  children,
  tone = "code",
}: {
  children: ReactNode;
  /** `code` keeps the panel's padding; `media` lets a screenshot bleed. */
  tone?: "code" | "media";
}): ReactElement => (
  /* No theme of its own. An earlier version pinned this to data-theme="dark"
     so its tabs would read on a near-black panel — but that made the surface
     a constant, and a constant dark panel on a light page is the 15:1 hole
     the code roles were just rebuilt to avoid. The panel takes the theme's
     code surface, which is the theme's module, so it is per-theme for free. */
  <div className={`gr-showpiece gr-showpiece--${tone}`}>
    <div className="gr-showpiece-inner">{children}</div>
  </div>
);

/**
 * A row of short claims, with the page's next step under it.
 *
 * The action belongs to the row rather than to a section of its own: the
 * claims are the argument and the button is what to do about it, and putting
 * a whole module between them would break that.
 */
export const Features = ({
  action,
  items,
}: {
  action?: { href: string; label: string };
  items: {
    body: string;
    evidence?: { href: string; label: string };
    title: string;
  }[];
}): ReactElement => (
  <>
    <div
      className="gr-cols gr-features"
      style={{ "--gr-cols": items.length } as CSSProperties}
    >
      {items.map((item) => (
        <div key={item.title}>
          <h3 className="gr-heading">{item.title}</h3>
          <p className="gr-body gr-muted">
            {item.body}
            {item.evidence ? (
              <>
                {" "}
                <a
                  className="gr-link"
                  href={item.evidence.href}
                  rel="noreferrer"
                  target="_blank"
                >
                  {item.evidence.label}
                </a>
              </>
            ) : null}
          </p>
        </div>
      ))}
    </div>
    {action ? (
      <div className="gr-features-action">
        <a className="gr-button gr-button--main" href={action.href}>
          {action.label}
          <Arrow />
        </a>
      </div>
    ) : null}
  </>
);

export type CardItem = {
  /** Optional: a card with nowhere to go yet renders as a plain tile rather
   *  than a dead link. See `Cards`. */
  href?: string;
  image?: string;
  label: string;
  /** Shown under the label where a card carries a line of its own. */
  body?: string;
  /** A brand colour token for the well — "grove-500", "kiln-500". */
  tint?: string;
};

/**
 * A row of cards.
 *
 * `lift` is the models row: the cards sit on a baseline and the hovered one
 * rises out of it. Everything else is a plain grid — an article row has no
 * reason to move.
 */
export const Cards = ({
  columns,
  items,
  lift = false,
  overlay = false,
}: {
  /** Defaults to one column per card — a single row. */
  columns?: number;
  items: CardItem[];
  lift?: boolean;
  /** Sets the label inside the card rather than under it. */
  overlay?: boolean;
}): ReactElement => (
  <div
    className={`gr-cols gr-cards${lift ? " gr-cards--lift" : ""}${
      overlay ? " gr-cards--overlay" : ""
    }`}
    style={{ "--gr-cols": columns ?? items.length } as CSSProperties}
  >
    {items.map((item) => {
      const media = (
        <>
          <span
            className="gr-card-media"
            style={
              {
                ...(item.image
                  ? { backgroundImage: `url(${item.image})` }
                  : null),
                ...(item.tint
                  ? { backgroundColor: `var(--color-${item.tint})` }
                  : null),
              } as CSSProperties
            }
          />
          <span className="gr-card-label">{item.label}</span>
          {item.body ? (
            <span className="gr-body gr-muted">{item.body}</span>
          ) : null}
        </>
      );

      /* A DIV, not an anchor with no href. An <a> without href is still in
         the tab order on some engines and announces as a link that goes
         nowhere, which is worse than plainly not being one. */
      return item.href ? (
        <a className="gr-card" href={item.href} key={item.label}>
          {media}
        </a>
      ) : (
        <div className="gr-card gr-card--pending" key={item.label}>
          {media}
        </div>
      );
    })}
  </div>
);

/**
 * A row that travels: the models, moving continuously across the page.
 *
 * The run is rendered TWICE and the track translates by exactly half its
 * width, so the second copy is under the pointer at the moment the first
 * finishes and the loop has no seam. The duplicate is aria-hidden — it is the
 * same set of links, and a screen reader should hear each model once.
 *
 * Edges are faded with a mask rather than two gradient overlays. A mask needs
 * to know nothing about what is behind the row, so this keeps working on
 * every theme and over the wave field; overlays would have to be repainted
 * with the ground.
 *
 * It pauses on hover, which is what makes the cards usable: a link that is
 * moving is a link you have to chase.
 */
export const Marquee = ({ items }: { items: CardItem[] }): ReactElement => (
  <div className="gr-marquee">
    <div className="gr-marquee-track">
      {[0, 1].map((copy) => (
        <div aria-hidden={copy === 1} className="gr-marquee-run" key={copy}>
          {items.map((item) => (
            <a
              className="gr-card gr-marquee-card"
              href={item.href}
              key={item.label}
              tabIndex={copy === 1 ? -1 : undefined}
            >
              <span
                className="gr-card-media"
                style={
                  {
                    ...(item.image
                      ? { backgroundImage: `url(${item.image})` }
                      : null),
                    ...(item.tint
                      ? { backgroundColor: `var(--color-${item.tint})` }
                      : null),
                  } as CSSProperties
                }
              />
              <span className="gr-card-label">{item.label}</span>
            </a>
          ))}
        </div>
      ))}
    </div>
  </div>
);
