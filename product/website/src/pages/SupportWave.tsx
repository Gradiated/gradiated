import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/* Layered sine curves under one envelope; amplitude follows a speech-like rhythm. */

const CURVES = [
  { alpha: 0.95, amp: 1, freq: 3.2, speed: 1.9, width: 1.4 },
  { alpha: 0.5, amp: 0.72, freq: 4.6, speed: -2.6, width: 1 },
  { alpha: 0.32, amp: 0.5, freq: 2.3, speed: 1.3, width: 1 },
  { alpha: 0.2, amp: 0.36, freq: 6.1, speed: -3.4, width: 0.8 },
];

/* Speech-like loudness: a few incommensurate slow sines, kept in 0.25..1. */
const loudness = (t: number) => {
  const raw =
    0.55 +
    0.25 * Math.sin(t * 1.7) +
    0.15 * Math.sin(t * 3.1 + 1.3) +
    0.1 * Math.sin(t * 5.3 + 0.4);
  return Math.min(1, Math.max(0.25, raw));
};

export const SupportWave = (): ReactElement => {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let visible = false;
    /* The wave draws in once the card has landed. */
    let woke: number | null = null;
    let width = 0;
    let height = 0;

    const resize = () => {
      const ratio = window.devicePixelRatio || 1;
      width = element.clientWidth;
      height = element.clientHeight;
      element.width = Math.round(width * ratio);
      element.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const ease = (p: number) => 1 - Math.pow(1 - p, 3);
    const reveal = (time: number) => {
      if (still.matches) return 1;
      if (woke === null) return 0;
      return ease(Math.min(1, Math.max(0, (time - woke - 1100) / 1300)));
    };

    const draw = (time: number) => {
      const t = time / 1000;
      const mid = height / 2;
      const shown = reveal(time);
      const level = loudness(t) * mid * 0.9 * shown;
      const reach = width * shown;
      /* Line weights are authored for the design's 215px card. */
      const scale = width / 190;
      context.clearRect(0, 0, width, height);
      context.lineCap = "round";
      context.lineJoin = "round";

      for (const curve of CURVES) {
        context.beginPath();
        for (let x = 0; x <= reach; x += 1) {
          const u = (x / width) * 2 - 1; /* -1 .. 1 across the card */
          const envelope = Math.pow(4 / (4 + Math.pow(u * 2.2, 4)), 2);
          const y =
            mid +
            level *
              curve.amp *
              envelope *
              Math.sin(u * Math.PI * curve.freq - t * curve.speed);
          if (x === 0) context.moveTo(x, y);
          else context.lineTo(x, y);
        }
        context.strokeStyle = `rgb(20 6 40 / ${curve.alpha})`;
        context.lineWidth = curve.width * scale;
        context.stroke();
      }
    };

    const loop = (time: number) => {
      woke ??= time;
      draw(time);
      frame = requestAnimationFrame(loop);
    };

    const sync = () => {
      cancelAnimationFrame(frame);
      if (still.matches || !visible) draw(performance.now());
      else frame = requestAnimationFrame(loop);
    };

    resize();
    const sized = new ResizeObserver(() => {
      resize();
      sync();
    });
    sized.observe(element);
    const seen = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      sync();
    });
    seen.observe(element);
    still.addEventListener("change", sync);

    return () => {
      cancelAnimationFrame(frame);
      sized.disconnect();
      seen.disconnect();
      still.removeEventListener("change", sync);
    };
  }, []);

  return (
    <canvas aria-hidden="true" className="gr-lab-support-wave" ref={canvas} />
  );
};
