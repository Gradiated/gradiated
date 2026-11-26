import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/* A colourful 3D double helix, turning slowly: two strands of glossy beads
   with base-pair rungs between them. Drawn on a canvas in perspective:
   each bead is placed on its strand's spiral, projected, and painted back
   to front, smaller and dimmer as it recedes. The colour runs along the
   helix's length (violet through magenta and orange to teal), the two
   strands offset so each rung joins two hues.

   It only runs while on screen and holds one frame for reduced motion. */

const PAIRS = 30;
const TURN = 0.42; /* radians of twist per base pair */
const TILT = -0.22; /* the axis leans a little, for depth */

const hueAt = (u: number) =>
  265 + u * 230; /* violet → magenta → orange → teal */

export const DnaHelix = (): ReactElement => {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let visible = false;
    let width = 0;
    let height = 0;

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = element.clientWidth;
      height = element.clientHeight;
      element.width = Math.round(width * ratio);
      element.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const draw = (time: number) => {
      const spin = time / 2600;
      const radius = width * 0.2;
      const bead = width * 0.055;
      const step = (height * 0.86) / (PAIRS - 1);
      const top = height * 0.07;
      const focal = width * 3;
      const cos = Math.cos(TILT);
      const sin = Math.sin(TILT);

      type Dot = { x: number; y: number; z: number; hue: number };
      const project = (px: number, py: number, pz: number) => {
        /* Lean the axis: rotate about z, then perspective. */
        const x = px * cos - py * sin;
        const y = px * sin + py * cos;
        const scale = focal / (focal - pz);
        return {
          x: width / 2 + x * scale,
          y: height / 2 + y * scale,
          s: scale,
        };
      };

      const dots: (Dot & { r: number })[] = [];
      const rungs: { a: Dot; b: Dot }[] = [];
      for (let n = 0; n < PAIRS; n += 1) {
        const u = n / (PAIRS - 1);
        const angle = n * TURN + spin;
        const y = top + n * step - height / 2;
        const ends = [0, Math.PI].map((offset, strand) => {
          const z = Math.sin(angle + offset) * radius;
          const p = project(Math.cos(angle + offset) * radius, y, z);
          return {
            x: p.x,
            y: p.y,
            z,
            r: bead * p.s,
            hue: hueAt(u) + strand * 40,
          };
        });
        dots.push(...ends);
        rungs.push({ a: ends[0], b: ends[1] });
      }

      context.clearRect(0, 0, width, height);

      /* Rungs first, each a two-hue line, dimmer when it lies further back. */
      for (const { a, b } of rungs) {
        const depth = (a.z + b.z) / (2 * radius); /* -1 back .. 1 front */
        const gradient = context.createLinearGradient(a.x, a.y, b.x, b.y);
        gradient.addColorStop(0, `hsl(${a.hue} 85% 62%)`);
        gradient.addColorStop(1, `hsl(${b.hue} 85% 62%)`);
        context.globalAlpha = 0.45 + (0.35 * (depth + 1)) / 2;
        context.strokeStyle = gradient;
        context.lineWidth = Math.max(1, bead * 0.38);
        context.lineCap = "round";
        context.beginPath();
        context.moveTo(a.x, a.y);
        context.lineTo(b.x, b.y);
        context.stroke();
      }

      /* Beads back to front, each a lit sphere. */
      dots.sort((p, q) => p.z - q.z);
      for (const dot of dots) {
        const near = (dot.z / radius + 1) / 2; /* 0 back .. 1 front */
        const light = 48 + near * 16;
        const sphere = context.createRadialGradient(
          dot.x - dot.r * 0.35,
          dot.y - dot.r * 0.4,
          dot.r * 0.1,
          dot.x,
          dot.y,
          dot.r,
        );
        sphere.addColorStop(0, `hsl(${dot.hue} 100% 92%)`);
        sphere.addColorStop(0.35, `hsl(${dot.hue} 90% ${light + 8}%)`);
        sphere.addColorStop(1, `hsl(${dot.hue + 20} 80% ${light - 22}%)`);
        context.globalAlpha = 0.55 + near * 0.45;
        context.fillStyle = sphere;
        context.beginPath();
        context.arc(dot.x, dot.y, dot.r, 0, Math.PI * 2);
        context.fill();
      }
      context.globalAlpha = 1;
    };

    const loop = (time: number) => {
      draw(time);
      frame = requestAnimationFrame(loop);
    };

    const sync = () => {
      cancelAnimationFrame(frame);
      if (still.matches || !visible) draw(4000);
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
    <canvas aria-hidden="true" className="gr-lab-dna-canvas" ref={canvas} />
  );
};
