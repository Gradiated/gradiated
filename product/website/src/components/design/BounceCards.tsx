/**
 * Vendored from React Bits' BounceCards (reactbits.dev, MIT licence, David
 * Haz), ported to TypeScript for this codebase. A loose fan of cards that
 * pop in on springs; hovering one straightens it and pushes the rest aside.
 *
 * Changes from upstream: cards hold any content (`cards`) rather than only
 * images, may be oblong (`cardWidth` and `cardHeight`), report the hovered
 * card (`onHoverChange`), may pop in from part size with a fade
 * (`fromScale`), and the container may take any CSS width. The
 * spring physics are unchanged.
 */
import { useEffect, useRef } from "react";
import type { CSSProperties, ReactElement, ReactNode } from "react";
import "./BounceCards.css";

const PATTERN = [1, 0.5, -0.3, -1, 0.2, 0.75, -0.6, 0.35, -0.85, 0.1];

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

type Slot = { rotate: number; x: number; y: number };

const parseTransform = (value: string | undefined): Slot | null => {
  if (typeof value !== "string") return null;
  const rotate = value.match(/rotate\(\s*(-?[\d.]+)deg\s*\)/);
  const translate = value.match(
    /translate\(\s*(-?[\d.]+)px(?:\s*,\s*(-?[\d.]+)px)?\s*\)/,
  );

  return {
    rotate: rotate ? Number(rotate[1]) : 0,
    x: translate ? Number(translate[1]) : 0,
    y: translate && translate[2] ? Number(translate[2]) : 0,
  };
};

type Body = {
  born: number;
  rotate: number;
  scale: number;
  vr: number;
  vs: number;
  vx: number;
  vy: number;
  x: number;
  y: number;
};

export type BounceCardsProps = {
  animationDelay?: number;
  animationStagger?: number;
  arc?: number;
  borderColor?: string;
  borderWidth?: number;
  bounciness?: number;
  cardHeight?: number;
  /** Each card's content, from left to right. */
  cards: ReactNode[];
  cardWidth?: number;
  className?: string;
  containerHeight?: number | string;
  containerWidth?: number | string;
  enableHover?: boolean;
  /** The scale a card pops in from; above 0 it also fades in. */
  fromScale?: number;
  hoverScale?: number;
  onCardClick?: (index: number) => void;
  /** The hovered card's index, or -1 when none is. */
  onHoverChange?: (index: number) => void;
  pushDistance?: number;
  radius?: number;
  rotation?: number;
  shadow?: boolean;
  spread?: number;
  style?: CSSProperties;
  transformStyles?: string[];
};

export const BounceCards = ({
  animationDelay = 0.5,
  animationStagger = 0.06,
  arc = 0,
  borderColor = "#ffffff",
  borderWidth = 5,
  bounciness = 0.6,
  cardHeight = 200,
  cards,
  cardWidth = 200,
  className = "",
  containerHeight = 400,
  containerWidth = 400,
  enableHover = true,
  fromScale = 0,
  hoverScale = 1.06,
  onCardClick,
  onHoverChange,
  pushDistance = 160,
  radius = 25,
  rotation = 10,
  shadow = true,
  spread = 85,
  style,
  transformStyles,
}: BounceCardsProps): ReactElement => {
  const rootRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<Array<HTMLDivElement | null>>([]);
  const wakeRef = useRef<(() => void) | null>(null);
  const count = cards.length;
  const middle = (count - 1) / 2;
  const reach = Math.max(1, middle);
  const slots = cards.map((_, i): Slot => {
    const custom = transformStyles ? parseTransform(transformStyles[i]) : null;
    if (custom) return custom;

    const offset = i - middle;
    return {
      rotate: rotation * PATTERN[i % PATTERN.length],
      x: offset * spread,
      y: arc * (offset / reach) ** 2,
    };
  });
  const settings = {
    bounciness: clamp(bounciness, 0, 1),
    cardHeight: Math.max(10, cardHeight),
    cardWidth: Math.max(10, cardWidth),
    clickable: typeof onCardClick === "function",
    delay: Math.max(0, animationDelay),
    enableHover,
    fromScale: clamp(fromScale, 0, 0.99),
    hoverScale: clamp(hoverScale, 0.5, 2),
    pushDistance,
    slots,
    stagger: Math.max(0, animationStagger),
  };
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const clickRef = useRef(onCardClick);
  clickRef.current = onCardClick;
  const hoverRef = useRef(onHoverChange);
  hoverRef.current = onHoverChange;

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;

    const reduce =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const bodies: Body[] = [];
    const state = { hovered: -1, layer: -1, time: 0 };
    let raf = 0;
    let last = performance.now();
    let alive = true;

    const body = (i: number): Body => {
      if (!bodies[i]) {
        const slot = settingsRef.current.slots[i] ?? { rotate: 0, x: 0, y: 0 };
        bodies[i] = {
          born: state.time,
          rotate: slot.rotate,
          scale: reduce ? 1 : settingsRef.current.fromScale,
          vr: 0,
          vs: 0,
          vx: 0,
          vy: 0,
          x: slot.x,
          y: slot.y,
        };
      }

      return bodies[i];
    };

    const step = (
      value: number,
      velocity: number,
      target: number,
      stiffness: number,
      damping: number,
      dt: number,
    ): [number, number] => {
      const next =
        velocity + ((target - value) * stiffness - velocity * damping) * dt;
      return [value + next * dt, next];
    };

    const frame = (now: number) => {
      raf = 0;
      if (!alive) return;

      const s = settingsRef.current;
      const dt = Math.min(1 / 30, Math.max(1 / 240, (now - last) / 1000));
      last = now;
      state.time += dt;

      const hovered = s.enableHover ? state.hovered : -1;
      const popStiffness = 170;
      const popDamping =
        2 * (1 - 0.85 * s.bounciness) * Math.sqrt(popStiffness);
      const moveStiffness = 210;
      const moveDamping = 2 * (reduce ? 1 : 0.72) * Math.sqrt(moveStiffness);
      const substeps = Math.ceil(dt / (1 / 240));
      const h = dt / substeps;
      let moving = 0;

      for (let i = 0; i < s.slots.length; i++) {
        const el = cardRefs.current[i];
        if (!el) continue;

        const card = body(i);
        const slot = s.slots[i];
        const appeared =
          reduce || state.time - card.born >= s.delay + i * s.stagger;
        let targetX = slot.x;
        let targetY = slot.y;
        let targetRotate = slot.rotate;
        let targetScale = appeared ? 1 : s.fromScale;
        if (hovered >= 0 && appeared) {
          if (i === hovered) {
            targetY = slot.y - s.cardHeight * 0.04;
            targetRotate = 0;
            targetScale = s.hoverScale;
          } else {
            targetX = slot.x + Math.sign(i - hovered) * s.pushDistance;
          }
        }

        for (let k = 0; k < substeps; k++) {
          [card.x, card.vx] = step(
            card.x,
            card.vx,
            targetX,
            moveStiffness,
            moveDamping,
            h,
          );
          [card.y, card.vy] = step(
            card.y,
            card.vy,
            targetY,
            moveStiffness,
            moveDamping,
            h,
          );
          [card.rotate, card.vr] = step(
            card.rotate,
            card.vr,
            targetRotate,
            moveStiffness,
            moveDamping,
            h,
          );
          if (reduce) {
            card.scale = targetScale;
            card.vs = 0;
          } else {
            [card.scale, card.vs] = step(
              card.scale,
              card.vs,
              targetScale,
              popStiffness,
              popDamping,
              h,
            );
          }
        }

        moving +=
          Math.abs(card.vx) +
          Math.abs(card.vy) +
          Math.abs(card.vr) +
          Math.abs(card.vs) * 100 +
          Math.abs(targetX - card.x) +
          Math.abs(targetY - card.y) +
          Math.abs(targetRotate - card.rotate) +
          Math.abs(targetScale - card.scale) * 100 +
          (appeared ? 0 : 1);
        if (s.fromScale > 0) {
          el.style.opacity = String(
            clamp((card.scale - s.fromScale) / (1 - s.fromScale), 0, 1),
          );
        }
        el.style.transform = `translate(-50%, -50%) translate3d(${card.x.toFixed(2)}px, ${card.y.toFixed(2)}px, 0) rotate(${card.rotate.toFixed(3)}deg) scale(${Math.max(0, card.scale).toFixed(4)})`;
      }

      if (state.layer !== hovered) {
        state.layer = hovered;
        cardRefs.current.forEach((el, i) => {
          if (!el) return;
          el.style.zIndex =
            i === hovered ? String(s.slots.length + 1) : String(i + 1);
          el.toggleAttribute("data-active", i === hovered);
        });
      }

      if (moving > 0.02) raf = requestAnimationFrame(frame);
    };

    const wake = () => {
      if (raf || !alive) return;
      last = performance.now();
      raf = requestAnimationFrame(frame);
    };
    wakeRef.current = wake;

    const hover = (index: number) => {
      if (index === state.hovered) return;
      state.hovered = index;
      hoverRef.current?.(index);
      wake();
    };

    const pick = (event: PointerEvent | MouseEvent): number => {
      const s = settingsRef.current;
      const rect = root.getBoundingClientRect();
      const px = event.clientX - rect.left - rect.width / 2;
      const py = event.clientY - rect.top - rect.height / 2;
      let best = -1;
      let distance = Infinity;
      s.slots.forEach((slot, i) => {
        const gap = Math.abs(px - slot.x);
        if (gap < distance) {
          distance = gap;
          best = i;
        }
      });
      if (best < 0) return -1;

      const slot = s.slots[best];
      if (
        Math.abs(py - slot.y) > s.cardHeight / 2 + 12 ||
        distance > s.cardWidth / 2 + 12
      ) {
        return -1;
      }
      if (state.hovered >= 0 && state.hovered !== best) {
        const current = s.slots[state.hovered];
        if (current && Math.abs(px - current.x) - distance < 6) {
          return state.hovered;
        }
      }

      return best;
    };

    const onMove = (event: PointerEvent) => hover(pick(event));
    const onLeave = () => hover(-1);
    const onClick = (event: MouseEvent) => {
      const index = pick(event);
      if (index < 0) return;

      const card = bodies[index];
      if (card && !reduce) card.vs -= 2.2;
      wake();
      clickRef.current?.(index);
    };
    const onFocus = (event: FocusEvent) => {
      const index = cardRefs.current.indexOf(event.target as HTMLDivElement);
      if (index >= 0) hover(index);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Enter" && event.key !== " ") return;

      const index = cardRefs.current.indexOf(event.target as HTMLDivElement);
      if (index < 0 || !settingsRef.current.clickable) return;

      event.preventDefault();
      if (bodies[index] && !reduce) bodies[index].vs -= 2.2;
      wake();
      clickRef.current?.(index);
    };

    root.addEventListener("pointermove", onMove);
    root.addEventListener("pointerdown", onMove);
    root.addEventListener("pointerleave", onLeave);
    root.addEventListener("click", onClick);
    root.addEventListener("focusin", onFocus);
    root.addEventListener("focusout", onLeave);
    root.addEventListener("keydown", onKey);
    wake();

    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      wakeRef.current = null;
      root.removeEventListener("pointermove", onMove);
      root.removeEventListener("pointerdown", onMove);
      root.removeEventListener("pointerleave", onLeave);
      root.removeEventListener("click", onClick);
      root.removeEventListener("focusin", onFocus);
      root.removeEventListener("focusout", onLeave);
      root.removeEventListener("keydown", onKey);
    };
  }, []);

  useEffect(() => {
    wakeRef.current?.();
  });

  return (
    <div
      className={`bounce-cards${className ? ` ${className}` : ""}`}
      ref={rootRef}
      style={
        {
          "--bounce-cards-border": `${Math.max(0, borderWidth)}px`,
          "--bounce-cards-border-color": borderColor,
          "--bounce-cards-height": `${settings.cardHeight}px`,
          "--bounce-cards-radius": `${Math.max(0, radius)}px`,
          "--bounce-cards-shadow": shadow
            ? "0 1px 2px rgba(0, 0, 0, 0.12), 0 10px 28px -6px rgba(0, 0, 0, 0.32)"
            : "none",
          "--bounce-cards-shadow-active": shadow
            ? "0 2px 4px rgba(0, 0, 0, 0.14), 0 22px 44px -10px rgba(0, 0, 0, 0.42)"
            : "none",
          "--bounce-cards-width": `${settings.cardWidth}px`,
          height: containerHeight,
          width: containerWidth,
          ...style,
        } as CSSProperties
      }
    >
      {cards.map((card, i) => (
        <div
          className={`bounce-cards__card${settings.clickable ? " bounce-cards__card--clickable" : ""}`}
          key={i}
          ref={(el) => {
            cardRefs.current[i] = el;
          }}
          style={{ zIndex: i + 1 }}
          {...(settings.clickable
            ? { "aria-label": `Card ${i + 1}`, role: "button", tabIndex: 0 }
            : settings.enableHover
              ? // Focus brings a card forward, as hover does, so keyboard
                // readers can reach the text other cards cover.
                { tabIndex: 0 }
              : null)}
        >
          {card}
        </div>
      ))}
    </div>
  );
};
