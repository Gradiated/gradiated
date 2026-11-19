import {
  type CSSProperties,
  type ReactElement,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";
import { Module } from "./Module";

export type CollageLayer = {
  /** How far it trails the page as the hero scrolls away; 0 moves with it. */
  drift: number;
  file: string;
  /** Where it is laid down from: an offset of its own size, and a tilt. */
  from: { r: number; x: number; y: number };
  left: number;
  top: number;
  width: number;
};

/** Holds the collage back until every layer has loaded, so it is laid down
    in full rather than piece by piece as each download lands. */
const useLaidDown = () => {
  const ref = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"laid" | "waiting">();

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    setState("waiting");
    let done = false;
    const lay = () => {
      if (done) return;
      done = true;
      setState("laid");
    };
    // On a slow connection it goes ahead rather than leave the hero empty.
    const fallback = setTimeout(lay, 3000);
    Promise.all(
      [...node.querySelectorAll("img")].map((image) =>
        image.decode().catch(() => undefined),
      ),
    ).then(lay);

    return () => {
      done = true;
      clearTimeout(fallback);
    };
  }, []);

  return { ref, state };
};

/** Sets --drift on the hero to how many pixels of it have scrolled away. */
const useDrift = () => {
  const hero = useRef<HTMLDivElement>(null);
  const collage = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const target = hero.current;
    const box = collage.current;
    if (!target || !box) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let frame = 0;
    const update = () => {
      frame = 0;
      const { height, top } = box.getBoundingClientRect();
      const scrolled = Math.min(Math.max(-top, 0), height);
      target.style.setProperty("--drift", `${scrolled}px`);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };

    // The page scrolls inside the rail's sheet, not the window; capturing
    // hears whichever element it is.
    addEventListener("scroll", onScroll, { capture: true, passive: true });
    addEventListener("resize", onScroll, { passive: true });
    update();

    return () => {
      removeEventListener("scroll", onScroll, { capture: true });
      removeEventListener("resize", onScroll);
      cancelAnimationFrame(frame);
    };
  }, []);

  return { collage, hero };
};

type CollageHeroProps = {
  /** The collage's canvas, in the units the layers are placed in. Set the
      same ratio as --canvas on `className` for the hero's height. */
  canvas: { height: number; width: number };
  children: ReactNode;
  className: string;
  /** Back to front. */
  layers: readonly CollageLayer[];
  path: string;
};

/** A first fold that is a cut-paper collage: the copy on the left, the
    layers laid down one by one, then drifting apart as the page scrolls. */
export const CollageHero = ({
  canvas,
  children,
  className,
  layers,
  path,
}: CollageHeroProps): ReactElement => {
  const { collage, hero } = useDrift();
  const laid = useLaidDown();

  return (
    <Module bleed className={`gr-collage-hero ${className}`} index={0}>
      <div className="gr-collage-hero-frame" ref={hero}>
        <div className="gr-collage-hero-copy">{children}</div>

        <div
          aria-hidden="true"
          className="gr-collage"
          data-laid={laid.state}
          ref={(node) => {
            collage.current = node;
            laid.ref.current = node;
          }}
        >
          {layers.map(({ drift, file, from, left, top, width }, index) => (
            <img
              alt=""
              className="gr-collage-layer"
              decoding="async"
              fetchPriority={index === layers.length - 1 ? "high" : "auto"}
              key={file}
              src={`${path}/${file}`}
              style={
                {
                  "--from-r": `${from.r}deg`,
                  "--from-x": `${from.x}%`,
                  "--from-y": `${from.y}%`,
                  "--layer": index,
                  "--rate": drift,
                  left: `${(left / canvas.width) * 100}%`,
                  top: `${(top / canvas.height) * 100}%`,
                  width: `${(width / canvas.width) * 100}%`,
                } as CSSProperties
              }
            />
          ))}
        </div>
      </div>
    </Module>
  );
};
