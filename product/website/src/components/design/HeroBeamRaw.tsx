import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/**
 * RAW-STYLE EXPLORATION: the hero beam, asciified.
 *
 * The same field as HeroBeam — a cone with its point at the right edge and
 * its mouth off the left, energy flowing through it — but rendered in the
 * engine's language instead of colour: a grid of glyphs (dots, dashes,
 * o's, x's, chips) whose species is chosen by the field's intensity at
 * that cell. Ink on the page ground, nothing else.
 *
 * Canvas2D rather than a shader: a few thousand glyph cells at 30fps is
 * nothing, and glyphs are easier to draw crisply with paths than in GLSL.
 */

const CELL = 14; // CSS px per glyph cell
const FPS = 30;

export const HeroBeamRaw = (): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

    let ink = "#2F2D29";
    const rootEl =
      (canvas.closest(".gr-root") as HTMLElement) ?? document.documentElement;
    const readInk = (): void => {
      ink =
        getComputedStyle(rootEl).getPropertyValue("--color-text").trim() ||
        "#2F2D29";
    };
    readInk();
    const themed = new MutationObserver(readInk);
    themed.observe(rootEl, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    let W = 0;
    let H = 0;
    let apexY = 0.5;
    const resize = new ResizeObserver(() => {
      const box = host.getBoundingClientRect();
      W = box.width;
      H = box.height;
      const dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      /* the point sits on the FOLD's centre; the buffer runs 55vh past it
         (see .gr-beam in pages.css) */
      const fold = H - 0.55 * innerHeight;
      apexY = H > 0 ? (fold * 0.5) / H : 0.5;
    });
    resize.observe(host);

    /* cheap value noise, two octaves — the falloffs erase anything finer */
    const hash = (x: number, y: number): number => {
      const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
      return s - Math.floor(s);
    };
    const noise = (x: number, y: number): number => {
      const ix = Math.floor(x);
      const iy = Math.floor(y);
      const fx = x - ix;
      const fy = y - iy;
      const ux = fx * fx * (3 - 2 * fx);
      const uy = fy * fy * (3 - 2 * fy);
      const a = hash(ix, iy);
      const b = hash(ix + 1, iy);
      const c = hash(ix, iy + 1);
      const d = hash(ix + 1, iy + 1);
      return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy;
    };
    const fbm = (x: number, y: number): number =>
      0.65 * noise(x, y) + 0.35 * noise(x * 2.02, y * 2.02);

    /* one glyph per cell, species by intensity */
    const glyph = (x: number, y: number, i: number): void => {
      ctx.globalAlpha = Math.min(1, i * 1.15) * 0.5;
      if (i < 0.16) {
        ctx.fillRect(x - 0.75, y - 0.75, 1.5, 1.5); // dot
      } else if (i < 0.3) {
        ctx.fillRect(x - 3, y - 0.75, 6, 1.5); // dash
      } else if (i < 0.45) {
        ctx.strokeRect(x - 2.5, y - 2.5, 5, 5); // o (open die)
      } else if (i < 0.62) {
        ctx.beginPath(); // x
        ctx.moveTo(x - 3, y - 3);
        ctx.lineTo(x + 3, y + 3);
        ctx.moveTo(x + 3, y - 3);
        ctx.lineTo(x - 3, y + 3);
        ctx.stroke();
      } else if (i < 0.8) {
        ctx.strokeRect(x - 3.5, y - 3.5, 7, 7); // chip outline
        ctx.fillRect(x - 1, y - 1, 2, 2);
      } else {
        ctx.fillRect(x - 2.5, y - 2.5, 5, 5); // filled chip
      }
    };

    let raf = 0;
    let last = 0;
    let running = true;
    const seen = new IntersectionObserver(([e]) => {
      running = e.isIntersecting;
    });
    seen.observe(host);

    const frame = (now: number): void => {
      raf = requestAnimationFrame(frame);
      if (!running || W < 4) return;
      if (now - last < 1000 / FPS) return;
      last = now;
      const t = reduced ? 0 : now / 1000;

      ctx.clearRect(0, 0, W, H);
      ctx.strokeStyle = ink;
      ctx.fillStyle = ink;
      ctx.lineWidth = 1;

      const aspect = W / H;
      for (let cy = CELL / 2; cy < H; cy += CELL) {
        for (let cx = CELL / 2; cx < W; cx += CELL) {
          const dx = cx / W - 1.01;
          const dy = (cy / H - apexY) / aspect;
          const along = Math.hypot(dx, dy);
          if (along < 0.02 || along > 1.2) continue;
          const theta = Math.atan2(dy, -dx);
          const ang = Math.exp(-Math.pow(theta / 0.5, 2) * 1.7);
          if (ang < 0.03) continue;
          const rise = Math.min(1, (along - 0.02) / 0.16);
          const fade = 1 - Math.min(1, Math.max(0, (along - 0.62) / 0.5));
          const flow = fbm(along * 5.2 - t * 0.55, theta * 3.6 + along * 1.4);
          const i = rise * fade * ang * (0.28 + 0.95 * flow);
          if (i < 0.05) continue;
          glyph(cx, cy, i);
        }
      }
      ctx.globalAlpha = 1;
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      resize.disconnect();
      seen.disconnect();
      themed.disconnect();
    };
  }, []);

  /* Same wrapper as HeroBeam, so placement, overhang and mask carry over;
     the --raw modifier multiplies the ink into the colour field below. */
  return (
    <div className="gr-beam gr-beam--raw" ref={hostRef}>
      <canvas className="gr-beam-canvas" ref={canvasRef} />
    </div>
  );
};
