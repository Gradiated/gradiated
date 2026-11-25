import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { ReactElement, ReactNode } from "react";
import { Link } from "react-router-dom";
import { Arrow } from "./icons";
import { PixelIcon } from "./PixelIcon";
import { CONSOLE_BASE_URL } from "../../urls";
import { applyTheme, readStoredTheme, storeTheme } from "../../theme";
import type { ThemeId } from "../../theme";
import "../../styles/railshell.css";

/* The two-layer rail nav, as the site shell.
 *
 * LAYER 1, the base: a full-viewport ink surface. Its left edge carries
 * what is always visible — the vertical wordmark, the nav, the CTA. Its
 * body carries each panel section's reveal.
 *
 * LAYER 2, the content: the routed page, on a sheet floating above the
 * base. Hovering a panel-bearing nav item slides the sheet aside and
 * the base shows through. Narrow screens: the base collapses to a strip
 * on the LEFT — wordmark on top, a 2-bar menu below — and opening the
 * menu slides the sheet aside with the same gesture.
 *
 * Ported from the /home-experiment lab. The traps it carries: a reveal
 * taller than the viewport scrolls internally (stretching the base
 * shifts the nav under the cursor and oscillates); the sheet's
 * transitions live in ONE declaration; only panel items slide the
 * sheet.
 */

const BOOKING_URL = "https://cal.com/team/gradiated/chat-with-gradiated";

/* -- doc mode ---------------------------------------------------------------
   The rail's second state: a doc-style page (handbook, docs) registers
   its contents and the rail transforms — the wordmark slides out left,
   the glyph + a back arrow take the top, the page's TOC fills the body.
   One rail, two states; the page never draws its own sidebar. */

export type RailDocGroup = {
  heading?: string;
  items: readonly {
    href: string;
    label: string;
    /** An indented child of the item above it (a journey subsection). */
    sub?: boolean;
    /** A small square before the label: a person's photo, their initials,
     *  or an icon. The team's contents use it; it replaces the chip. */
    thumb?: { icon?: ReactNode; src?: string; text?: string };
  }[];
};

export type RailDocNav = {
  title: string;
  /** The current page's href, for the active state. */
  current?: string;
  groups: readonly RailDocGroup[];
  backHref?: string;
};

const RailDocContext = createContext<(nav: RailDocNav | null) => void>(
  () => {},
);

/* -- back control -----------------------------------------------------------
   A page that sits one level under an index (a note, a job listing)
   registers where "back" goes; the rail draws the arrow above the
   wordmark — on every device — and the page draws nothing above its
   content, so every page's content starts at the same height. */

export type RailBack = { href: string; label: string };

const RailBackContext = createContext<(back: RailBack | null) => void>(
  () => {},
);

export const useRailBack = (back: RailBack): void => {
  const register = useContext(RailBackContext);
  useEffect(() => {
    register(back);
    return () => register(null);
  }, [register, back.href, back.label]);
};

/** Register the page's contents with the rail for as long as the page
 *  is mounted. Pass module-level `groups` (or memoize) — identity
 *  churn re-renders the rail. */
export const useRailDocNav = (nav: RailDocNav): void => {
  const register = useContext(RailDocContext);
  useEffect(() => {
    register(nav);
    return () => register(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [register, nav.title, nav.current, nav.groups]);
};

type Card = {
  title: string;
  blurb: string;
  href: string;
  image?: string;
  video?: string;
  zoom?: number;
  rate?: number;
  framed?: boolean;
  art?: string;
  ink?: string;
};

type Model = {
  name: string;
  color: string;
  href: string;
  icon?: string;
};

type Section = {
  id: string;
  label: string;
  href: string;
  /* Only panel-bearing items slide the sheet. */
  panel?: boolean;
  title?: string;
  cards?: readonly Card[];
  models?: readonly Model[];
};

const SECTIONS: readonly Section[] = [
  {
    id: "product",
    label: "Product",
    href: "/inference/",
    panel: true,
    title: "The research lab focused on inference.",
    cards: [
      {
        title: "Training",
        blurb: "Automatic fine-tuning from your traffic.",
        href: "/training/",
        image: "/brand/nav/training.webp",
      },
      {
        title: "Inference",
        blurb: "Open-model inference, pay based on your latency requirement.",
        href: "/inference/",
        image: "/brand/nav/inference.webp",
      },
    ],
    models: [
      {
        name: "DeepSeek V4.1 Flash",
        color: "#f4ce56",
        href: "/models/deepseek-v4-1-flash/",
        icon: "/assets/models/deepseek-color.svg",
      },
      {
        name: "GLM 5.3 Flash",
        color: "#8ed3f2",
        href: "/models/glm-5-3-flash/",
        icon: "/assets/models/zhipu-color.svg",
      },
      { name: "Kev 9B", color: "#a28fe9", href: "/models/kev-9b/" },
    ],
  },
  {
    id: "company",
    label: "Company",
    href: "/about/",
    panel: true,
    cards: [
      {
        title: "Careers",
        blurb: "Come make AI use less energy.",
        href: "/careers/",
        image: "/brand/nav/careers.webp",
      },
      {
        title: "Handbook",
        blurb: "How we operate, and why.",
        href: "/handbook/",
        image: "/brand/nav/handbook.webp",
      },
      {
        title: "About",
        blurb: "AI research lab in Cambridge, UK.",
        href: "/about/",
        image: "/brand/nav/about.webp",
      },
      {
        title: "Thesis",
        blurb: "Why we exist, and what we believe.",
        href: "/library/our-thesis/",
        image: "/brand/nav/thesis.webp",
      },
    ],
  },
  {
    id: "library",
    label: "Library",
    href: "/library/",
  },
  {
    id: "docs",
    label: "Docs",
    href: "/docs/",
  },
];

/* Light / dark, in the rail. Storage is read after mount (the stored
   value is unknowable on the server), and a choice lands on EVERY
   .gr-root — the shell's and the page's — the moment it is made. The
   shell owns the state: the rail and the phone strip each draw a
   toggle, and both must agree across a breakpoint change. */
const useRailTheme = (): [ThemeId, (next: ThemeId) => void] => {
  const [theme, setTheme] = useState<ThemeId>("taupe");
  useEffect(() => {
    /* Substrate applies the stored theme to the PAGE root on mount; the
       shell's root (sheet ground, overscroll) needs it too, or a dark
       page sits on a light sheet after navigation. */
    const stored = readStoredTheme();
    setTheme(stored);
    document
      .querySelectorAll<HTMLElement>(".gr-root")
      .forEach((root) => applyTheme(root, stored));
  }, []);
  const choose = useCallback((next: ThemeId) => {
    setTheme(next);
    storeTheme(next);
    document
      .querySelectorAll<HTMLElement>(".gr-root")
      .forEach((root) => applyTheme(root, next));
  }, []);
  return [theme, choose];
};

const STRIP_KEY = "gr-strip";

/* Phones: the strip can be put away so the page takes the full width.
   Remembered per device, and read after mount like the theme. */
const useStripHidden = (): [boolean, (hidden: boolean) => void] => {
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    try {
      setHidden(localStorage.getItem(STRIP_KEY) === "hidden");
    } catch {
      // Storage can be unavailable; the strip just starts shown.
    }
  }, []);

  const choose = useCallback((next: boolean) => {
    setHidden(next);
    try {
      if (next) localStorage.setItem(STRIP_KEY, "hidden");
      else localStorage.removeItem(STRIP_KEY);
    } catch {
      // Not remembered, but the choice still applies to this visit.
    }
  }, []);

  return [hidden, choose];
};

const RailThemeToggle = ({
  theme,
  onChoose,
}: {
  theme: ThemeId;
  onChoose: (next: ThemeId) => void;
}): ReactElement => {
  const dark = theme === "dark";
  /* One icon, showing the theme you would switch TO. */
  return (
    <button
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="gr-rail-theme"
      onClick={() => onChoose(dark ? "taupe" : "dark")}
      type="button"
    >
      <PixelIcon name={dark ? "sun" : "moon"} />
    </button>
  );
};

const tileLuminance = (hex: string): number => {
  const n = parseInt(hex.slice(1), 16);
  return (
    (0.2126 * ((n >> 16) & 255) +
      0.7152 * ((n >> 8) & 255) +
      0.0722 * (n & 255)) /
    255
  );
};

/* Model tiles carry a palette colour with the provider's mark struck
   WHITE — never its brand colour. A model of ours with no mark wears
   its initial in our face. (The texture pass joins with the shared
   package; the lab renders these over EnergyField stills.) */
const ModelTile = ({ color, icon, name }: Model): ReactElement => (
  <span className="gr-rail-model-tile" style={{ background: color }}>
    {icon ? (
      <img alt="" src={icon} style={{ filter: "brightness(0) invert(1)" }} />
    ) : (
      <span
        className="gr-rail-model-initial"
        style={{
          color: tileLuminance(color) > 0.55 ? "#ffffff" : "#ffffff",
        }}
      >
        {name[0]}
      </span>
    )}
  </span>
);

const SectionReveal = ({ section }: { section: Section }): ReactElement => (
  <>
    {section.title && <h2 className="gr-rail-under-title">{section.title}</h2>}
    {section.cards && (
      <div className="gr-rail-under-cards">
        {section.cards.map((card) => (
          <a className="gr-rail-under-card" href={card.href} key={card.title}>
            <span
              className="gr-rail-under-art"
              data-framed={card.framed || undefined}
              style={
                (card.image || card.video) && !card.art
                  ? undefined
                  : { background: card.art, color: card.ink }
              }
            >
              {card.video ? (
                <video
                  autoPlay
                  loop
                  muted
                  playsInline
                  poster={`/brand/nav/${card.video}-poster.jpg`}
                  ref={(el) => {
                    if (el && card.rate) el.playbackRate = card.rate;
                  }}
                  style={{
                    transform: card.zoom ? `scale(${card.zoom})` : undefined,
                    mixBlendMode: card.art ? "screen" : undefined,
                  }}
                >
                  <source
                    src={`/brand/nav/${card.video}.webm`}
                    type="video/webm"
                  />
                  <source
                    src={`/brand/nav/${card.video}.mp4`}
                    type="video/mp4"
                  />
                </video>
              ) : (
                card.image && <img alt="" src={card.image} />
              )}
            </span>
            <span className="gr-rail-under-name">
              {card.title} <Arrow />
            </span>
            <span className="gr-rail-under-blurb">{card.blurb}</span>
          </a>
        ))}
      </div>
    )}
    {section.models && (
      <>
        <hr className="gr-rail-under-rule" />
        <a className="gr-rail-models-lede" href="/models/">
          Models <Arrow />
        </a>
        <div className="gr-rail-models">
          {section.models.map((model) => (
            <a className="gr-rail-model" href={model.href} key={model.name}>
              <ModelTile {...model} />
              <span className="gr-rail-model-name">
                {model.name} <Arrow />
              </span>
            </a>
          ))}
        </div>
      </>
    )}
  </>
);

export const RailShell = ({
  children,
}: {
  children: ReactNode;
}): ReactElement => {
  const [peek, setPeek] = useState<string | null>(null);
  const [menu, setMenu] = useState(false);
  /* Product opens by default: the menu lands on the offer, not a list. */
  const [menuOpen, setMenuOpen] = useState<string | null>("product");
  /* The menu is always mounted (it is the base layer the sheet slides
     off), but its reveal carries the posters — those only load once the
     menu has actually been opened. */
  const [menuTouched, setMenuTouched] = useState(false);
  const [theme, chooseTheme] = useRailTheme();
  const [stripHidden, setStripHidden] = useStripHidden();
  const stripToggle = useRef<HTMLButtonElement>(null);
  const stripReveal = useRef<HTMLButtonElement>(null);
  const stripMoved = useRef(false);

  // Focus follows the control that just moved, but not on the first render.
  useEffect(() => {
    if (!stripMoved.current) return;

    (stripHidden ? stripReveal : stripToggle).current?.focus();
  }, [stripHidden]);

  const toggleStrip = (next: boolean) => {
    stripMoved.current = true;
    setStripHidden(next);
  };
  /* `doc` drives the rail's geometry (width, wordmark, nav). `shown`
     is what the doc chrome renders — it outlives `doc` by one exit
     animation, so leaving doc mode plays a choreography instead of a
     hard unmount. */
  const [doc, setDoc] = useState<RailDocNav | null>(null);
  const [shown, setShown] = useState<RailDocNav | null>(null);
  const [back, setBack] = useState<RailBack | null>(null);
  const [leaving, setLeaving] = useState(false);
  const exitTimer = useRef<number | undefined>(undefined);

  const registerDoc = useCallback((next: RailDocNav | null) => {
    window.clearTimeout(exitTimer.current);
    if (next) {
      setDoc(next);
      setShown(next);
      setLeaving(false);
      /* On a phone the menu opens on the page's contents. */
      setMenuOpen("doc");
      return;
    }
    setDoc(null);
    setLeaving(true);
    exitTimer.current = window.setTimeout(() => {
      setShown(null);
      setLeaving(false);
    }, 400);
  }, []);

  useEffect(() => () => window.clearTimeout(exitTimer.current), []);

  const active = SECTIONS.find((section) => section.id === peek) ?? null;

  return (
    <div
      className="gr-root gr-rail-root"
      data-doc={doc ? true : undefined}
      data-menu={menu || undefined}
      data-strip={stripHidden ? "hidden" : undefined}
      data-peek={peek ?? undefined}
    >
      {/* LAYER 1 — the base. Leaving it (entering the sheet) closes the
          peek; travelling nav -> cards keeps it open. */}
      <div className="gr-rail-base" onMouseLeave={() => setPeek(null)}>
        <aside className="gr-rail-rail">
          {/* Doc mode's back control: one link — the arrow AND the title. */}
          {shown && (
            <a
              className="gr-rail-dochead gr-rail-docback"
              data-leaving={leaving || undefined}
              href={shown.backHref ?? "/"}
            >
              <Arrow />
              <span className="gr-rail-doctitle">{shown.title}</span>
            </a>
          )}
          {back && !shown && (
            <a className="gr-rail-back" href={back.href}>
              <Arrow />
              <span>{back.label}</span>
            </a>
          )}
          <a className="gr-rail-wordmark" href="/">
            <img alt="Gradiated" src="/brand/wordmark-hx-white.svg" />
          </a>
          {shown && (
            <nav className="gr-rail-docnav" data-leaving={leaving || undefined}>
              {shown.groups.map((group, index) => (
                <div
                  className="gr-rail-docnav-group"
                  key={group.heading ?? index}
                >
                  {group.heading && (
                    <span className="gr-rail-docnav-title">
                      {group.heading}
                    </span>
                  )}
                  {group.items.map((item) =>
                    item.href.startsWith("#") ? (
                      /* In-page anchor — the journey pages navigate by
                         hash, not by route. */
                      <a
                        data-active={item.href === shown.current || undefined}
                        data-sub={item.sub || undefined}
                        href={item.href}
                        key={item.href}
                      >
                        {item.label}
                      </a>
                    ) : (
                      <Link
                        data-active={item.href === shown.current || undefined}
                        data-sub={item.sub || undefined}
                        data-thumb={item.thumb ? true : undefined}
                        key={item.href}
                        to={item.href}
                      >
                        {item.thumb ? (
                          <span aria-hidden="true" className="gr-rail-thumb">
                            {item.thumb.src ? (
                              <img alt="" src={item.thumb.src} />
                            ) : (
                              (item.thumb.icon ?? item.thumb.text)
                            )}
                          </span>
                        ) : null}
                        {item.label}
                      </Link>
                    ),
                  )}
                </div>
              ))}
            </nav>
          )}
          <nav className="gr-rail-nav">
            {SECTIONS.map((section) => (
              <a
                className="gr-rail-link"
                data-hot={section.id === peek || undefined}
                href={section.href}
                key={section.id}
                onFocus={() => setPeek(section.panel ? section.id : null)}
                onMouseEnter={() => setPeek(section.panel ? section.id : null)}
              >
                {section.label}
              </a>
            ))}
            <a className="gr-rail-link" href={CONSOLE_BASE_URL}>
              Log in
            </a>
          </nav>
          <RailThemeToggle onChoose={chooseTheme} theme={theme} />
          <a className="gr-rail-cta" href={BOOKING_URL}>
            Book a Call <Arrow />
          </a>
        </aside>

        <div
          aria-hidden={!active}
          className="gr-rail-under"
          key={peek ?? "none"}
        >
          {active && <SectionReveal section={active} />}
        </div>
      </div>

      {/* LAYER 2 — the routed page, on the sheet. */}
      <main className="gr-rail-sheet" inert={menu}>
        <RailDocContext.Provider value={registerDoc}>
          <RailBackContext.Provider value={setBack}>
            {children}
          </RailBackContext.Provider>
        </RailDocContext.Provider>
      </main>

      {/* Narrow screens: the base becomes a strip on the LEFT. */}
      <div className="gr-rail-strip" inert={stripHidden}>
        <div className="gr-rail-strip-top">
          {shown ? (
            <a
              aria-label={`Back to ${shown.title}`}
              className="gr-rail-strip-back"
              href={shown.backHref ?? "/"}
            >
              <Arrow />
            </a>
          ) : back ? (
            <a
              aria-label={`Back to ${back.label}`}
              className="gr-rail-strip-back"
              href={back.href}
            >
              <Arrow />
            </a>
          ) : null}
          <a aria-label="Gradiated" className="gr-rail-strip-mark" href="/">
            <img alt="" src="/brand/wordmark-hx-white.svg" />
          </a>
        </div>
        <div className="gr-rail-strip-bottom">
          <button
            aria-label="Hide the side bar"
            className="gr-rail-strip-hide"
            onClick={() => toggleStrip(true)}
            ref={stripToggle}
            type="button"
          >
            <PixelIcon name="sidebar-simple" />
          </button>
          <RailThemeToggle onChoose={chooseTheme} theme={theme} />
          <button
            aria-expanded={menu}
            aria-label={menu ? "Close menu" : "Open menu"}
            className="gr-rail-burger"
            onClick={() => {
              setMenuTouched(true);
              setMenu((open) => !open);
            }}
            type="button"
          >
            <span className="gr-rail-burger-bar" />
            <span className="gr-rail-burger-bar" />
          </button>
        </div>
      </div>
      {stripHidden && (
        <button
          aria-label="Show the side bar"
          className="gr-rail-strip-reveal"
          onClick={() => toggleStrip(false)}
          ref={stripReveal}
          type="button"
        >
          <PixelIcon name="caret-double-right" />
        </button>
      )}
      <div className="gr-rail-menu" inert={!menu}>
        <nav>
          {shown && (
            <div className="gr-rail-menu-item">
              <div className="gr-rail-menu-section">
                <button
                  aria-expanded={menuOpen === "doc"}
                  onClick={() =>
                    setMenuOpen((open) => (open === "doc" ? null : "doc"))
                  }
                  type="button"
                >
                  {shown.title} <Arrow />
                </button>
                {menuOpen === "doc" && (
                  <div className="gr-rail-menu-reveal gr-rail-menu-doc">
                    {shown.groups.map((group, index) => (
                      <div
                        className="gr-rail-menu-doc-group"
                        key={group.heading ?? index}
                      >
                        {group.heading && (
                          <span className="gr-rail-menu-doc-title">
                            {group.heading}
                          </span>
                        )}
                        {group.items.map((item) => (
                          <Link
                            data-active={
                              item.href === shown.current || undefined
                            }
                            data-sub={item.sub || undefined}
                            key={item.href}
                            onClick={() => setMenu(false)}
                            to={item.href}
                          >
                            {item.thumb ? (
                              <span
                                aria-hidden="true"
                                className="gr-rail-thumb"
                              >
                                {item.thumb.src ? (
                                  <img alt="" src={item.thumb.src} />
                                ) : (
                                  (item.thumb.icon ?? item.thumb.text)
                                )}
                              </span>
                            ) : null}
                            {item.label}
                          </Link>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
          {SECTIONS.map((section, index) => (
            <div className="gr-rail-menu-item" key={section.id}>
              {(index > 0 || shown) && <hr className="gr-rail-menu-rule" />}
              {section.panel ? (
                <div className="gr-rail-menu-section">
                  <button
                    aria-expanded={menuOpen === section.id}
                    onClick={() =>
                      setMenuOpen((open) =>
                        open === section.id ? null : section.id,
                      )
                    }
                    type="button"
                  >
                    {section.label} <Arrow />
                  </button>
                  {menuTouched && menuOpen === section.id && (
                    <div className="gr-rail-menu-reveal">
                      <SectionReveal section={section} />
                    </div>
                  )}
                </div>
              ) : (
                <a href={section.href} onClick={() => setMenu(false)}>
                  {section.label}
                </a>
              )}
            </div>
          ))}
          <div className="gr-rail-menu-item">
            <hr className="gr-rail-menu-rule" />
            <a href={CONSOLE_BASE_URL}>Log in</a>
          </div>
          <a className="gr-rail-menu-cta" href={BOOKING_URL}>
            Book a Call
          </a>
        </nav>
      </div>
    </div>
  );
};
