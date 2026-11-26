import { useEffect, useRef } from "react";
import type { CSSProperties, ReactElement, ReactNode, RefObject } from "react";
import { EvalChart, EvalHeatmap } from "./HeroEvals";
import { SupportWave } from "./SupportWave";

/* The homepage hero's collage, as designed in Figma ("New Home", node
   1234:202489): the lab's desk around the statement.

   Every piece is placed in the design's own coordinates — pixels on the
   1464px-wide sheet of the 1728px frame — and home-lab.css turns them into
   lengths with --px, so the composition scales with the sheet rather than
   being re-laid at each width. The interface pieces — the support call, the
   one-line switch, both eval cards and the tracking screen — are code; the
   objects (posters, the magazine, the chip, the stickers) are the design's
   own renders, at 2x, in /brand/home/.

   Decorative as a whole: hidden from assistive tech, not clickable, and
   still on hover, so the headline stays the page's first heading. */

type PieceProps = {
  children: ReactNode;
  className: string;
  /* The piece's top-left on the design's sheet, and its width, in design px. */
  h?: number;
  i: number;
  w: number;
  x: number;
  y: number;
};

const Piece = ({ children, className, h, i, w, x, y }: PieceProps) => (
  <div
    className={`gr-lab-piece ${className}`}
    style={
      {
        "--i": i,
        "--x": x,
        "--y": y,
        "--w": w,
        ...(h ? { "--h": h } : {}),
      } as CSSProperties
    }
  >
    {children}
  </div>
);

/* The tracking screen: the footage turned on its side to fill a portrait
   display, as in the design. Muted and looped; held on its first frame for
   anyone who asks for reduced motion. */
const TrackingVideo = ({
  className = "gr-lab-screen-video",
}: {
  className?: string;
}): ReactElement => {
  const video = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const element = video.current;
    if (!element) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => {
      /* Hidden in the stacked layout: don't fetch footage nobody sees. */
      if (still.matches || !element.offsetParent) element.pause();
      else void element.play().catch(() => undefined);
    };
    sync();
    still.addEventListener("change", sync);
    return () => still.removeEventListener("change", sync);
  }, []);

  return (
    <video
      aria-hidden="true"
      className={className}
      loop
      muted
      playsInline
      poster="/brand/home/tracking-poster.webp"
      preload="metadata"
      ref={video}
      src="/brand/home/tracking-loop.mp4"
    />
  );
};

/* An exported render: the image is the piece. */
const Render = ({ src }: { src: string }) => (
  <img alt="" decoding="async" src={`/brand/home/${src}.webp`} />
);

/* Parallax. Each piece has a --depth (home-lab.css); this feeds the collage
   three numbers and the CSS does the rest:
     --mx, --my  where the pointer is over the hero, -1..1, eased, with a slow
                 wander mixed in so the desk is never quite still;
     --sy        how far the page has scrolled, in px;
     --par       0..1, ramped up once the entrance has landed, so the
                 parallax never fights the float-in.
   One rAF loop, running only while the hero is on screen; nothing at all
   for reduced motion. */
const ENTRANCE_MS = 2600;

const useParallax = (collage: RefObject<HTMLDivElement | null>) => {
  useEffect(() => {
    const element = collage.current;
    if (!element) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      element.dataset.seen = "";
      return;
    }

    const target = { x: 0, y: 0 };
    const eased = { x: 0, y: 0, par: 0 };
    /* When the desk first came into view, and where the page was then. On
       the wide layout that is on load at the top; on phones the desk sits on
       the second screen and its entrance waits for it (data-seen, see
       home-lab.css). The parallax counts from that moment, so it starts at
       rest wherever the reader is. */
    let seenAt: number | null = null;
    let seenScroll = 0;
    let visible = false;
    let frame = 0;

    const point = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return;
      target.x = Math.max(
        -1,
        Math.min(1, (event.clientX / innerWidth) * 2 - 1),
      );
      target.y = Math.max(
        -1,
        Math.min(1, (event.clientY / innerHeight) * 2 - 1),
      );
    };
    const leave = () => {
      target.x = 0;
      target.y = 0;
    };

    const tick = (now: number) => {
      const t = now / 1000;
      const wander = {
        x: 0.18 * Math.sin(t * 0.31) + 0.07 * Math.sin(t * 0.83 + 1.7),
        y: 0.14 * Math.cos(t * 0.27 + 0.6) + 0.06 * Math.sin(t * 0.71),
      };
      eased.x += (target.x + wander.x - eased.x) * 0.06;
      eased.y += (target.y + wander.y - eased.y) * 0.06;
      const ramp =
        seenAt === null
          ? 0
          : Math.min(1, Math.max(0, (now - seenAt - ENTRANCE_MS) / 1200));
      eased.par += (ramp - eased.par) * 0.08;

      element.style.setProperty("--mx", eased.x.toFixed(4));
      element.style.setProperty("--my", eased.y.toFixed(4));
      element.style.setProperty("--sy", `${Math.round(scrollY - seenScroll)}`);
      element.style.setProperty("--par", eased.par.toFixed(4));
      frame = visible ? requestAnimationFrame(tick) : 0;
    };

    const seen = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
        if (visible && seenAt === null) {
          seenAt = performance.now();
          seenScroll = scrollY;
          element.dataset.seen = "";
        }
        if (visible && !frame) frame = requestAnimationFrame(tick);
      },
      { threshold: 0.12 },
    );
    seen.observe(element);
    addEventListener("pointermove", point, { passive: true });
    document.documentElement.addEventListener("pointerleave", leave);
    return () => {
      cancelAnimationFrame(frame);
      seen.disconnect();
      removeEventListener("pointermove", point);
      document.documentElement.removeEventListener("pointerleave", leave);
    };
  }, [collage]);
};

/* The collage has no fixed rules about the statement: any lower piece that
   would run into its text simply drops below the buttons. The statement is
   centred in the first screen and its column moves with the window, so
   this is measured rather than guessed: each piece's layout box (offsets,
   which ignore the entrance and parallax transforms) is checked against
   the text column, and pieces that belong together drop together so their
   arrangement holds. The drop is --drop on the piece; the stage grows by
   --lab-extra to keep the desk inside it. Nothing to do in the stacked
   layout, where the desk sits below the text anyway. */
const GROUPS = [
  ["gr-lab-thesis-map", "gr-lab-thesis"],
  ["gr-lab-paper-map", "gr-lab-paper"],
  ["gr-lab-sticker-joules", "gr-lab-sticker-g"],
];
const CLEARANCE = 40; /* px between the buttons and a dropped piece */

const useTextClearance = (collage: RefObject<HTMLDivElement | null>) => {
  useEffect(() => {
    const element = collage.current;
    const stage = element?.parentElement;
    const hero = stage?.querySelector<HTMLElement>(".gr-lab-hero");
    const actions = hero?.querySelector(".gr-home-actions");
    const title = hero?.querySelector(".gr-home-title");
    if (!element || !stage || !hero || !actions || !title) return;

    const pieces = [...element.querySelectorAll<HTMLElement>(".gr-lab-piece")];
    const groupOf = (piece: HTMLElement) =>
      GROUPS.find((group) =>
        group.some((name) => piece.classList.contains(name)),
      )?.[0] ?? piece.className;

    const measure = () => {
      for (const piece of pieces) piece.style.removeProperty("--drop");
      stage.style.removeProperty("--lab-extra");
      if (getComputedStyle(stage).display === "flex") return;

      /* The text block, in the collage's coordinates. */
      const origin = element.getBoundingClientRect();
      const words = [
        title,
        ...hero.querySelectorAll(".gr-lab-lede, .gr-home-actions"),
      ].map((node) => node.getBoundingClientRect());
      const text = {
        left: Math.min(...words.map((r) => r.left)) - origin.left,
        right: Math.max(...words.map((r) => r.right)) - origin.left,
        top: title.getBoundingClientRect().top - origin.top,
        bottom: actions.getBoundingClientRect().bottom - origin.top,
      };

      const drops = new Map<string, number>();
      for (const piece of pieces) {
        if (piece.offsetParent === null) continue;
        const box = {
          left: piece.offsetLeft,
          right: piece.offsetLeft + piece.offsetWidth,
          top: piece.offsetTop,
          bottom: piece.offsetTop + piece.offsetHeight,
        };
        const across = box.left < text.right && box.right > text.left;
        const into = box.top < text.bottom + CLEARANCE && box.bottom > text.top;
        /* Only pieces that start below the headline's top: the ones above
           and beside it frame it. */
        if (!across || !into || box.top <= text.top) continue;
        const need = text.bottom + CLEARANCE - box.top;
        const group = groupOf(piece);
        drops.set(group, Math.max(drops.get(group) ?? 0, need));
      }

      let lowest = 0;
      for (const piece of pieces) {
        const drop = Math.ceil(drops.get(groupOf(piece)) ?? 0);
        if (drop) piece.style.setProperty("--drop", `${drop}px`);
        if (piece.offsetParent !== null)
          lowest = Math.max(
            lowest,
            piece.offsetTop + piece.offsetHeight + drop,
          );
      }
      const extra = Math.max(0, lowest + CLEARANCE - element.offsetHeight);
      if (extra)
        stage.style.setProperty("--lab-extra", `${Math.ceil(extra)}px`);
    };

    measure();
    const sized = new ResizeObserver(() => requestAnimationFrame(measure));
    sized.observe(stage);
    sized.observe(hero);
    void document.fonts?.ready.then(measure);
    return () => sized.disconnect();
  }, [collage]);
};

export const HeroCollage = (): ReactElement => {
  const collage = useRef<HTMLDivElement>(null);
  useParallax(collage);
  useTextClearance(collage);
  return <Desk collage={collage} />;
};

const Desk = ({
  collage,
}: {
  collage: RefObject<HTMLDivElement | null>;
}): ReactElement => (
  <div aria-hidden="true" className="gr-lab-collage" ref={collage}>
    {/* Stacking matches the design's render: later pieces sit on top. */}
    <Piece
      className="gr-lab-render gr-lab-thesis-map"
      i={9}
      w={252}
      x={870.5}
      y={1018}
    >
      <Render src="thesis-map" />
    </Piece>

    <Piece
      className="gr-lab-render gr-lab-thesis"
      i={10}
      w={213}
      x={821}
      y={1074}
    >
      <Render src="thesis" />
    </Piece>

    <Piece
      className="gr-lab-render gr-lab-edge gr-lab-paper-map"
      i={12}
      w={205}
      x={1259}
      y={916}
    >
      <Render src="paper-map" />
    </Piece>

    <Piece
      className="gr-lab-support"
      h={239}
      i={0}
      w={215}
      /* Tucked under the rail, as in the design, where the rail art runs
         14px wider than the real one: 19px of the card sits behind it. */
      x={-19}
      y={106}
    >
      <span className="gr-lab-support-head">
        <span className="gr-lab-support-name">support_call.wav</span>
        <span className="gr-lab-support-tag gr-code">Support</span>
      </span>
      <SupportWave />
      <span className="gr-lab-support-quote">
        “...so the refund should land by Friday is my best guess.”
      </span>
    </Piece>

    <Piece className="gr-lab-code" i={1} w={298} x={310} y={128}>
      <span className="gr-lab-code-lines gr-code">
        <span>client = OpenAI(</span>
        {/* Typed in on load: 36 characters, one step each. */}
        <span className="gr-lab-code-add">
          base_url="https://api.gradiated.com"
        </span>
        <span>)</span>
      </span>
    </Piece>

    <Piece
      className="gr-lab-render gr-lab-edge gr-lab-paper"
      i={13}
      w={130}
      x={1334}
      y={742}
    >
      <Render src="paper" />
    </Piece>

    <Piece
      className="gr-lab-render gr-lab-magazine"
      i={4}
      w={402}
      x={220}
      y={707}
    >
      <Render src="magazine" />
    </Piece>

    <Piece className="gr-lab-chart" i={2} w={326.7} x={117} y={447}>
      <EvalChart />
    </Piece>

    <Piece className="gr-lab-heatmap" i={3} w={278.3} x={327} y={334}>
      <EvalHeatmap />
    </Piece>

    <Piece className="gr-lab-screen" h={549} i={11} w={216} x={1361} y={68.5}>
      <TrackingVideo />
    </Piece>

    <Piece className="gr-lab-render gr-lab-chip" i={5} w={223} x={127} y={1070}>
      <Render src="chip" />
    </Piece>

    <Piece
      className="gr-lab-render gr-lab-sticker-joules"
      i={6}
      w={246}
      x={486}
      y={1093}
    >
      <Render src="sticker-joules" />
    </Piece>

    {/* On top of the Joules badge, as rendered in the design. */}
    <Piece
      className="gr-lab-render gr-lab-sticker-g"
      i={7}
      w={183}
      x={424}
      y={1228}
    >
      <Render src="sticker-g" />
    </Piece>
  </div>
);

/* Phones and small tablets: the tracking screen in the space to the right
   of the headline, running off the screen's edge so only its left part
   shows. It plays the same footage as the wide layout's screen; whichever
   is hidden stays paused. Hidden on the wide layout. */
export const HeadlineScreen = (): ReactElement => (
  <span aria-hidden="true" className="gr-lab-title-screen">
    <TrackingVideo className="gr-lab-title-video" />
  </span>
);
