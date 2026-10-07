import { WaitlistButton, WaitlistDrawer } from "../WaitlistButton";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactElement } from "react";
import { library } from "./library";
import { models } from "../../models";
import { ModelArt } from "./ModelArt";
import { WaferArtwork } from "./WaferArtwork";
import { Arrow } from "./icons";
import { LOGO_ASPECT, Logo } from "./Logo";
import { MetalMark } from "./MetalMark";

/**
 * Site navigation: a bar with a shared dropdown above `wide`, a full-screen
 * sheet below it.
 *
 * THE SHARED DROPDOWN. There is ONE panel, not one per item. It is full-bleed
 * — a band the width of the viewport — so the only thing that changes between
 * items is its HEIGHT, and the cards inside it are centred rather than hung
 * from the trigger. When the pointer moves between items the panel resizes to
 * the new item's content instead of closing and reopening; that continuity is
 * the whole effect. Mechanically: content height is measured on activation and
 * driven as an inline style that a CSS transition carries between states (see
 * nav.css). Opening from closed snaps the height into place and only fades — a
 * glide from a stale height reads as a bug.
 *
 * Being full-bleed is what removed the fiddliest part of this: the panel used
 * to be measured against its trigger and clamped to the bar's span so a
 * right-edge item could not push it off. A band has no such problem.
 *
 * THE LIBRARY PANEL ALSO LISTS THE WRITING. Cards say what the section is;
 * the list says what is actually in it, newest first, across both halves —
 * notes and handbook pieces. It comes from ./library, which reads the real
 * catalogue rather than restating it. The list is a sample, not an index —
 * three rows and a way through to all of it.
 *
 * PANELS ARE CARDS. Each entry is a media well with a label under it, so a
 * panel is a small gallery rather than a list of descriptions. The wells are
 * empty until real media exists; an entry with `image` set fills its own. The
 * panel's width is not configured — the cards are fixed-width grid columns, so
 * the content measures to whatever its card count needs and the morph reads
 * the difference. Product's four and Library's two size themselves.
 *
 * THE SHEET. Below `wide` there is no room for four items, two actions and a
 * panel, so navigation becomes a full-screen sheet with the same cards stacked
 * two to a row. It is the same NAV_ITEMS in a different shape — a second copy
 * of the site's structure would be a second thing to keep in sync.
 *
 * The sheet carries its own close control and the bar stows while it is open.
 * The bar scrolls with the page and has no surface of its own, so leaving it
 * there put the wordmark on top of whatever the sheet scrolled under it. Focus
 * moves to the close button on open and back to the trigger on close, so the
 * sheet does not strand a keyboard reader on a control that is gone.
 *
 * THE HIGHLIGHT sits on the CARDS, not on the bar. One light block travels
 * between them, the same idea as the segmented control — but the tabs can
 * position theirs arithmetically because their cells are equal, and a card's
 * box includes a label of whatever length, so this one is measured: the
 * hovered card's offset and width within the panel are published as custom
 * properties and CSS transitions carry the block between them.
 *
 * The bar's own items are text links and behave like every other link on the
 * site — a rule drawn under the label. A block there would make the bar a
 * second segmented control competing with the panel's.
 *
 * All motion uses the response family tokens; both shapes inherit the
 * system's radius and hairline borders.
 */

type PanelCard = {
  /** One line. If it needs two, the card is doing too much. */
  body: string;
  href: string;
  /** Fills the well. Empty until the real media exists. */
  image?: string;
  label: string;
  /** Basename in /brand/nav/. Expects .webm, .mp4 and -poster.jpg beside it. */
  video?: string;
};

type NavItem = {
  href: string;
  label: string;
  /** Items without a panel are plain links. */
  panel?: {
    cards: PanelCard[];
    /** A line of standfirst set beside the cards, before them. */
    intro?: string;
    /** Appends the model list beside the cards. */
    models?: boolean;
    /** Appends the writing list beside the cards. */
    writing?: boolean;
  };
};

/** A sample, not an index — the link under it goes to the whole thing.
 *  `library` is already newest-first. */
const LATEST = library.slice(0, 3);

const NAV_ITEMS: NavItem[] = [
  {
    href: "/inference/",
    label: "Product",
    panel: {
      /* Says what the company IS, beside what it sells. The panel is the one
         place a reader stops long enough to take a sentence in. */
      intro: "The research lab focused on inference.",
      models: true,
      cards: [
        {
          image: "/brand/nav/service-tiers.jpg",
          label: "Training",
          body: "Automatic fine-tuning from your traffic.",
          href: "/training/",
        },
        {
          image: "/brand/nav/api.jpg",
          label: "Inference",
          body: "Open-model inference, pay based on your latency requirement.",
          href: "/inference/",
        },
      ],
    },
  },
  /* Promoted out of the Product panel to a destination of its own. No panel
     yet — one card is not a gallery, and the shared panel only earns its
     complexity where there is a set to move between. */
  { href: "/hardware/", label: "Hardware" },
  {
    href: "/library/",
    label: "Library",
    panel: {
      writing: true,
      cards: [
        {
          video: "frontier-notes",
          label: "Notes",
          body: "Frontier notes on inference, systems and hardware.",
          /* The Library filtered to one half, not a separate page — the
             filter is in the URL so it can be linked to. */
          href: "/library/?show=notes",
        },
        {
          image: "/brand/nav/handbook.jpg",
          label: "Methods",
          body: "How we operate, and why.",
          /* Was /library/handbook/brand/, which main deleted along with
             HandbookPage — a dead link in the nav. The handbook is Method now. */
          href: "/library/?show=methods",
        },
      ],
    },
  },
  { href: "/careers/", label: "Careers" },
  { href: "/docs/", label: "Docs" },
];

/** Where "Book a call" goes. One constant, because the bar and the drawer
 *  both offer it and a booking link in two places is a booking link that can
 *  disagree with itself. */
const BOOKING_URL = "https://cal.com/jsgradiated/30min";

/** Grace period before the panel closes, so the pointer can travel into it. */
const CLOSE_DELAY_MS = 120;

/** How long the drawer takes to leave. Keep in step with --dur-base, which is
 *  what the slide itself is timed to. A timer rather than an animationend
 *  listener: under prefers-reduced-motion there is no animation to end, and
 *  the drawer would stay mounted for ever waiting for the event. */
const SHEET_OUT_MS = 240;

/** The latest pieces, and the way to the rest of them.
 *
 *  The same list in the panel and the drawer, like Card below — the two were
 *  the same markup written twice until the drawer needed it as well, which is
 *  how a list ends up with different dates in two places. */
/** The models with pages, beside the Product cards — marks in a grid, the
 *  way the Library panel carries its writing. Same list in the panel and the
 *  sheet, same reason as WritingList. */
const ModelsList = ({
  onEnter,
}: {
  /** Feeds the panel's one travelling highlight, like the cards do. */
  onEnter?: (node: HTMLElement) => void;
}): ReactElement => (
  <div className="gr-nav-models">
    <p className="gr-label gr-nav-models-title">Models</p>
    <ul>
      {models.map((model) => (
        <li key={model.slug}>
          <a
            className="gr-nav-model"
            href={`/models/${model.slug}/`}
            onPointerEnter={(event) => onEnter?.(event.currentTarget)}
          >
            <span aria-hidden className="gr-nav-model-mark">
              <ModelArt
                icon={model.icon}
                name={model.name}
                slug={model.slug}
                small
              />
            </span>
            <span className="gr-nav-model-name">
              {model.name}
              <Arrow />
            </span>
          </a>
        </li>
      ))}
    </ul>
  </div>
);

const WritingList = ({
  onEnter,
}: {
  /** Feeds the panel's one travelling highlight, like the cards do. */
  onEnter?: (node: HTMLElement) => void;
}): ReactElement => (
  <div className="gr-nav-writing">
    <p className="gr-label gr-nav-writing-title">Latest writing</p>
    <ul>
      {LATEST.map((note) => (
        <li key={note.href}>
          <a
            className="gr-nav-note"
            href={note.href}
            onPointerEnter={(event) => onEnter?.(event.currentTarget)}
          >
            <div
              aria-hidden
              className="gr-nav-note-thumb"
              style={{
                backgroundImage: note.art
                  ? `url(${note.art})`
                  : note.cover
                    ? undefined
                    : `var(${note.gradient})`,
                backgroundPosition: note.art
                  ? "50% 50%"
                  : `${note.coverAt} 50%`,
              }}
            >
              {!note.art && note.cover ? (
                <WaferArtwork options={note.cover} />
              ) : null}
            </div>
            <span className="gr-nav-note-text">
              <span className="gr-nav-note-name">
                <span className="gr-nav-note-name-text">{note.title}</span>
                <Arrow />
              </span>
              <time className="gr-nav-note-date" dateTime={note.dateTime}>
                {note.date}
              </time>
            </span>
          </a>
        </li>
      ))}
    </ul>

    <a className="gr-link gr-nav-writing-all" href="/library/">
      See all writing
      <Arrow />
    </a>
  </div>
);

/** One media well, a title and a line. The same card in the panel and the
 *  sheet, so the two shapes cannot drift. */
const Card = ({
  card,
  onEnter,
  showing = true,
}: {
  card: PanelCard;
  onEnter?: (node: HTMLElement) => void;
  /** Whether this card is actually on screen. The panel mounts every item's
   *  content for measurement, so mounted does not mean visible. */
  showing?: boolean;
}): ReactElement => {
  const videoRef = useRef<HTMLVideoElement>(null);

  /* The film plays ONCE from the top each time the card is revealed, and
     does not loop — it is a flourish for the moment the panel opens, not
     ambient wallpaper. It used to autoplay looping from mount, which meant
     it was running invisibly behind closed panels and mid-film whenever one
     opened. Freezes on its last frame; the next open rewinds it.

     Under reduced motion it does not play at all: the poster is the cover. */
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (!showing) {
      video.pause();
      return;
    }
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduced.matches) return;
    video.currentTime = 0;
    void video.play().catch(() => {});
  }, [showing]);

  return (
    <a
      className="gr-nav-card"
      href={card.href}
      onPointerEnter={(event) => onEnter?.(event.currentTarget)}
    >
      <span
        className={`gr-nav-card-media${card.video ? " gr-nav-card-media--film" : ""}`}
      >
        {card.video ? (
          <video
            muted
            playsInline
            poster={`/brand/nav/${card.video}-poster.jpg`}
            preload="metadata"
            ref={videoRef}
          >
            <source src={`/brand/nav/${card.video}.webm`} type="video/webm" />
            <source src={`/brand/nav/${card.video}.mp4`} type="video/mp4" />
          </video>
        ) : card.image ? (
          <img alt="" src={card.image} />
        ) : null}
      </span>
      <span className="gr-nav-card-title">
        {card.label}
        <Arrow />
      </span>
      <span className="gr-nav-card-body">{card.body}</span>
    </a>
  );
};

export const Nav = (): ReactElement => {
  const [active, setActive] = useState<number | null>(null);
  /** The active content's height; the band supplies its own width. */
  const [height, setHeight] = useState<number | null>(null);
  /** True for the first frame of an open, to snap geometry instead of gliding. */
  const [snapping, setSnapping] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  /* The waitlist drawer's mount lives HERE, not in its trigger: the trigger
     sits inside the sheet, and the sheet unmounts on handoff — a drawer
     owned by that trigger would die with the menu that opened it. */
  const [waitlistOpen, setWaitlistOpen] = useState(false);
  /* Kept mounted through its exit. Unmounting on close is why the drawer used
     to vanish — there was nothing left on the page to animate out. */
  const [sheetClosing, setSheetClosing] = useState(false);
  /** The travelling highlight's box, in the panel content's own coordinates. */
  const [highlight, setHighlight] = useState<{
    height: number;
    left: number;
    top: number;
    width: number;
  } | null>(null);

  const rootRef = useRef<HTMLElement>(null);
  const itemRefs = useRef<(HTMLElement | null)[]>([]);
  const contentRefs = useRef<(HTMLDivElement | null)[]>([]);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const burgerRef = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);

  const cancelClose = useCallback(() => {
    if (closeTimer.current !== null) clearTimeout(closeTimer.current);
    closeTimer.current = null;
  }, []);

  /* Measured against the card's own PANEL, not the viewport, so the block's
     position is unaffected by the panel gliding under it mid-hover. */
  const highlightCard = useCallback((node: HTMLElement) => {
    /* The panel content, not the parent: the side lists' rows live inside
       their own column, and the block's coordinates are the panel's. */
    const content = node.closest(".gr-nav-panel-content");
    if (!content) return;
    const box = node.getBoundingClientRect();
    const frame = content.getBoundingClientRect();
    // The card's full box, which already carries its own padding — so the
    // block sits just clear of the well and the type, rather than being
    // stretched to the band's height.
    setHighlight({
      height: box.height,
      left: box.left - frame.left,
      top: box.top - frame.top,
      width: box.width,
    });
  }, []);

  const open = useCallback(
    (index: number) => {
      cancelClose();
      // A different item means a different panel, so the block has nothing to
      // travel from — it fades in where the next card is hovered.
      setHighlight(null);
      if (NAV_ITEMS[index]?.panel === undefined) {
        setActive(null);
        return;
      }
      setSnapping(!wasOpen.current);
      wasOpen.current = true;
      setActive(index);
    },
    [cancelClose],
  );

  const scheduleClose = useCallback(() => {
    cancelClose();
    closeTimer.current = setTimeout(() => {
      wasOpen.current = false;
      setActive(null);
      setHighlight(null);
    }, CLOSE_DELAY_MS);
  }, [cancelClose]);

  // Measure the active item's content. Only the height is needed — the band
  // is as wide as the viewport whichever item is open. The panel is a fixed
  // sibling of the bar rather than a child because the bar clips its own
  // overflow to morph the logo, which would clip this too.
  useEffect(() => {
    if (active === null) return;
    const content = contentRefs.current[active];
    if (!content) return;
    setHeight(content.offsetHeight);
  }, [active]);

  // The snap lasts exactly one frame: geometry lands without transition, then
  // transitions come back on so the next item change glides.
  useEffect(() => {
    if (!snapping) return;
    const frame = requestAnimationFrame(() =>
      requestAnimationFrame(() => setSnapping(false)),
    );
    return () => cancelAnimationFrame(frame);
  }, [snapping]);

  useEffect(() => cancelClose, [cancelClose]);

  /* Closing is a state, not an instant. The drawer stays mounted with the out
     animation running, and only leaves the tree once it has left the screen. */
  const closeSheet = useCallback(() => {
    setSheetOpen(false);
    setSheetClosing(true);
  }, []);

  useEffect(() => {
    if (!sheetClosing) return;
    const timer = setTimeout(() => setSheetClosing(false), SHEET_OUT_MS);
    return () => clearTimeout(timer);
  }, [sheetClosing]);

  /* The sheet covers the page, so the page behind it must not scroll under it.
     Restoring the previous value rather than clearing it, in case something
     else was already holding the lock. */
  /* Held for the exit as well as the stay: releasing the lock the moment the
     close begins lets the page jump behind a drawer that is still sliding. */
  useEffect(() => {
    if (!sheetOpen && !sheetClosing) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    /* No focus move on open: the burger IS the close control now, and it
       already has focus from the tap that opened the drawer. */
    return () => {
      document.body.style.overflow = previous;
      burgerRef.current?.focus();
    };
  }, [sheetOpen, sheetClosing]);

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key !== "Escape") return;
    wasOpen.current = false;
    setActive(null);
    closeSheet();
  };

  return (
    <>
      <nav
        aria-label="Site"
        className="gr-nav"
        onKeyDown={onKeyDown}
        onPointerEnter={cancelClose}
        onPointerLeave={scheduleClose}
        ref={rootRef}
      >
        {/* The lockup's aspect comes from the artwork, not from CSS. The bar
            clips this box to collapse the wordmark on scroll, so its expanded
            width has to be exactly the lockup's — and when the wordmark was
            replaced, the number restated in nav.css was still the old one and
            clipped the final letter. */}
        <a
          aria-label="Gradiated home"
          className="gr-nav-wordmark"
          href="/"
          style={{ "--logo-aspect": LOGO_ASPECT } as CSSProperties}
        >
          {/* the lockup, recomposed: the mark in liquid metal, the
              wordmark in ink as ever */}
          <MetalMark />
          <Logo wordmark />
        </a>

        <div className="gr-nav-links" role="list">
          {NAV_ITEMS.map((item, index) => (
            <a
              aria-expanded={item.panel ? active === index : undefined}
              aria-haspopup={item.panel ? "menu" : undefined}
              className={`gr-nav-link${active === index ? " gr-nav-link--active" : ""}`}
              href={item.href}
              key={item.label}
              onFocus={() => open(index)}
              onPointerEnter={() => open(index)}
              ref={(node) => {
                itemRefs.current[index] = node;
              }}
            >
              {item.label}
            </a>
          ))}
        </div>

        <div className="gr-nav-actions">
          {/* The booking page, not /careers/ — someone booking a call is a
              prospect, and sending them to the jobs list was a dead end. */}
          <a
            className="gr-link gr-nav-action"
            href={BOOKING_URL}
            rel="noreferrer"
          >
            Book a call
          </a>
          <WaitlistButton className="gr-link gr-nav-action">
            Request beta access
            <Arrow />
          </WaitlistButton>
        </div>
      </nav>

      {/* A SIBLING of the bar, not a child.
          Shown only below `wide` — see nav.css.

          One button for both directions, rather than a separate close control
          inside the drawer: two elements cannot morph into each other, and the
          two bars becoming a cross is the whole affordance.

          Outside the bar because the two need to stack independently. Inside
          it, keeping the cross above the drawer meant raising the whole bar —
          and the wordmark with it, which then had to be hidden to stop it
          painting over the drawer. On its own layer the wordmark simply stays
          where it is and lets the drawer cover it. */}
      <button
        aria-expanded={sheetOpen}
        aria-label={sheetOpen ? "Close menu" : "Open menu"}
        className="gr-nav-burger"
        onClick={() => (sheetOpen ? closeSheet() : setSheetOpen(true))}
        ref={burgerRef}
        type="button"
      >
        <span aria-hidden className="gr-burger">
          <span className="gr-burger-bar" />
          <span className="gr-burger-bar" />
        </span>
      </button>

      {/* The shared panel — a sibling of the bar, not a child: the bar clips
          its own overflow to morph the logo, which would clip this too.
          Always mounted so geometry can transition; closed is just opacity 0
          plus pointer-events none. Every item's content is mounted inside for
          measurement; the active one shows, neighbours sit one step toward
          their own side so switching reads as travel. */}
      <div
        aria-hidden={active === null}
        onPointerEnter={cancelClose}
        onPointerLeave={scheduleClose}
        className={[
          "gr-nav-panel",
          active !== null ? "gr-nav-panel--open" : "",
          snapping ? "gr-nav-panel--snap" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        style={height === null ? undefined : { height: `${height}px` }}
      >
        {NAV_ITEMS.map((item, index) =>
          item.panel ? (
            <div
              className={`gr-nav-panel-content${
                active === index ? " gr-nav-panel-content--active" : ""
              }`}
              key={item.label}
              ref={(node) => {
                contentRefs.current[index] = node;
              }}
              onPointerLeave={() => setHighlight(null)}
              style={
                {
                  "--hl-h": highlight ? `${highlight.height}px` : "0px",
                  "--hl-w": highlight ? `${highlight.width}px` : "0px",
                  "--hl-x": highlight ? `${highlight.left}px` : "0px",
                  "--hl-y": highlight ? `${highlight.top}px` : "0px",
                  "--slide": active !== null && index < active ? "-1" : "1",
                } as CSSProperties
              }
            >
              {item.panel.intro ? (
                <p className="gr-nav-intro">{item.panel.intro}</p>
              ) : null}

              {/* Behind the cards, so one is lit rather than boxed. */}
              <span
                aria-hidden
                className={`gr-nav-highlight${highlight ? " gr-nav-highlight--on" : ""}`}
              />
              {item.panel.cards.map((card) => (
                <Card
                  card={card}
                  key={card.label}
                  onEnter={highlightCard}
                  showing={active === index}
                />
              ))}

              {/* Spans the width two more cards would have taken, so a panel
                  with a list is the same width as one without — the morph
                  between Product and Library changes height, not span. */}
              {item.panel.models ? (
                <ModelsList onEnter={highlightCard} />
              ) : null}
              {item.panel.writing ? (
                <WritingList onEnter={highlightCard} />
              ) : null}
            </div>
          ) : null,
        )}
      </div>

      {/* The sheet. Mounted only while open — unlike the panel it has no
          geometry to transition, so there is nothing to keep alive. */}
      {sheetOpen || sheetClosing ? (
        <>
          {/* Tapping beside a drawer closes it. Without this the page's own
              links are still live next to an open drawer, so a miss navigates
              instead of dismissing. */}
          <button
            aria-hidden
            className={`gr-nav-scrim${sheetClosing ? " gr-nav-scrim--closing" : ""}`}
            onClick={closeSheet}
            tabIndex={-1}
            type="button"
          />

          <div
            aria-label="Site"
            className={`gr-nav-sheet${sheetClosing ? " gr-nav-sheet--closing" : ""}`}
            onKeyDown={onKeyDown}
            role="dialog"
          >
            <div className="gr-nav-sheet-inner">
              {NAV_ITEMS.filter((item) => item.panel).map((item) => (
                <section className="gr-nav-sheet-group" key={item.label}>
                  <h2 className="gr-nav-sheet-title">{item.label}</h2>
                  <div className="gr-nav-sheet-cards">
                    {item.panel?.cards.map((card) => (
                      <Card card={card} key={card.label} />
                    ))}
                  </div>
                  {/* Under the cards here, where the panel sets it beside
                      them: there is no second column in a drawer. */}
                  {item.panel?.models ? <ModelsList /> : null}
                  {item.panel?.writing ? <WritingList /> : null}
                </section>
              ))}

              {/* The panel-less items, side by side: they are single
                destinations, so they get a row rather than a gallery. */}
              <div className="gr-nav-sheet-plain">
                {NAV_ITEMS.filter((item) => !item.panel).map((item) => (
                  <a
                    className="gr-nav-sheet-plain-link"
                    href={item.href}
                    key={item.label}
                  >
                    {item.label}
                  </a>
                ))}
              </div>

              <div className="gr-nav-sheet-actions">
                <a
                  className="gr-button gr-button--secondary"
                  href={BOOKING_URL}
                  rel="noreferrer"
                >
                  Book a call
                </a>
                <button
                  className="gr-button gr-button--main"
                  type="button"
                  onClick={() => {
                    setWaitlistOpen(true);
                    closeSheet();
                  }}
                >
                  Request beta access
                </button>
              </div>
            </div>
          </div>
        </>
      ) : null}

      {waitlistOpen ? (
        <WaitlistDrawer
          handoff={{ openMenu: () => setSheetOpen(true) }}
          onExited={() => setWaitlistOpen(false)}
        />
      ) : null}
    </>
  );
};
