import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/**
 * The homepage flow: one object, scroll-scrubbed.
 *
 * A frosted panel rises out of the hero, fills the frame while its frost
 * resolves to reveal the post-training engine, re-frosts into a chip, and
 * lands — isometric, glowing — in the silicon section. The chip is the
 * throughline of the whole page and is only explicit at the end.
 *
 * Physics contract (from the grey-box prototype):
 * - Geometry follows scroll through a critically-damped chase, so the object
 *   has weight. The chase uses REAL elapsed time, never a clamped dt — the
 *   exponential is what keeps it frame-rate independent.
 * - Micro-life (the engine loop, the gradient's travel) runs on wall-clock
 *   time regardless of scroll, so the scene stays alive while the user reads.
 * - Copy beats are rests: geometry is parked wherever text is readable.
 *
 * The gradient here is the SAME gradient as the hero beam — the brand seats,
 * cycling — and it means the same thing at each appearance: where the energy
 * is. Frosted breathing in the panel, ignition at the post-training stage,
 * residual heat under the landed chip.
 */

/* ---- timeline ----
   Beats in scroll progress 0..1 across the runway. engineRest and
   siliconRest are the reading rests. */
const BEATS = {
  rise: [0.0, 0.16],
  clarify: [0.16, 0.32],
  engineRest: [0.32, 0.54],
  refrost: [0.54, 0.68],
  land: [0.68, 0.84],
  siliconRest: [0.84, 1.0],
} as const;

/** Runway height in viewport-heights; the scrub's total scroll distance. */
export const RUNWAY_VH = 700;

/** Time constant of the damped chase (seconds). The object's weight. */
const DAMPING_TAU = 0.14;

const FROST_BLUR_MAX = 26;
const FROST_VEIL_MAX = 0.72;
const ENGINE_CYCLE_S = 9;

/** The brand gradient's seats, in travel order — read from the live theme. */
const SEAT_TOKENS = [
  "--color-kiln-500",
  "--color-kiln-300",
  "--color-grove-600",
  "--color-aegean-500",
  "--color-taupe-400",
];

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const seg = (p: number, [a, b]: readonly [number, number]): number =>
  clamp01((p - a) / (b - a));
const easeIO = (t: number): number =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
const easeO = (t: number): number => 1 - Math.pow(1 - t, 3);
const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

type BlockState = {
  cx: number;
  cy: number;
  w: number;
  h: number;
  r: number;
  rx: number;
  rz: number;
};

type TimelineOut = {
  s: BlockState;
  frost: number;
  markAlpha: number;
  shadowAlpha: number;
  engineA: number;
  engineCopyA: number;
  siliconCopyA: number;
  glowMode: "block" | "engine" | "landing";
};

const keyStates = (
  W: number,
  H: number,
): Record<"peek" | "rise" | "full" | "chip" | "land", BlockState> => {
  const vm = Math.min(W, H);
  const inset = Math.max(24, vm * 0.03);
  const wide = W > 720;
  /* Anchored by its TOP edge so the peek height under the hero is stable
     across viewport sizes — pairs with .gr-flow's -34vh overlap. */
  const peekSize = Math.min(W * 0.46, 560);
  return {
    peek: { cx: W / 2, cy: H * 0.2 + peekSize / 2, w: peekSize, h: peekSize, r: 2, rx: 0, rz: 0 },
    rise: { cx: W / 2, cy: H * 0.52, w: vm * 0.64, h: vm * 0.64, r: 2, rx: 0, rz: 0 },
    full: { cx: W / 2, cy: H / 2, w: W - inset * 2, h: H - inset * 2, r: 6, rx: 0, rz: 0 },
    chip: { cx: W / 2, cy: H * 0.5, w: vm * 0.46, h: vm * 0.46, r: 4, rx: 0, rz: 0 },
    land: { cx: W * (wide ? 0.34 : 0.5), cy: H * (wide ? 0.52 : 0.38), w: vm * 0.42, h: vm * 0.42, r: 4, rx: 58, rz: 45 },
  };
};

const mixState = (a: BlockState, b: BlockState, t: number): BlockState => ({
  cx: lerp(a.cx, b.cx, t),
  cy: lerp(a.cy, b.cy, t),
  w: lerp(a.w, b.w, t),
  h: lerp(a.h, b.h, t),
  r: lerp(a.r, b.r, t),
  rx: lerp(a.rx, b.rx, t),
  rz: lerp(a.rz, b.rz, t),
});

const evalTimeline = (g: number, W: number, H: number): TimelineOut => {
  const K = keyStates(W, H);
  const out: TimelineOut = {
    s: K.peek,
    frost: 1,
    markAlpha: 0,
    shadowAlpha: 0,
    engineA: 0,
    engineCopyA: 0,
    siliconCopyA: 0,
    glowMode: "block",
  };
  if (g < BEATS.rise[1]) {
    out.s = mixState(K.peek, K.rise, easeIO(seg(g, BEATS.rise)));
  } else if (g < BEATS.clarify[1]) {
    const t = easeIO(seg(g, BEATS.clarify));
    out.s = mixState(K.rise, K.full, t);
    out.frost = 1 - t;
    out.engineA = t;
  } else if (g < BEATS.engineRest[1]) {
    out.s = K.full;
    out.frost = 0;
    out.engineA = 1;
    out.glowMode = "engine";
    const t = seg(g, BEATS.engineRest);
    out.engineCopyA = Math.min(easeO(t * 3), 1 - clamp01((t - 0.82) / 0.18));
  } else if (g < BEATS.refrost[1]) {
    const t = easeIO(seg(g, BEATS.refrost));
    out.s = mixState(K.full, K.chip, t);
    out.frost = t;
    out.engineA = 1 - t;
    out.glowMode = t < 0.5 ? "engine" : "block";
  } else if (g < BEATS.land[1]) {
    const t = easeIO(seg(g, BEATS.land));
    out.s = mixState(K.chip, K.land, t);
    out.markAlpha = easeO(clamp01((t - 0.35) / 0.65));
    out.shadowAlpha = easeO(clamp01((t - 0.3) / 0.7)) * 0.55;
    out.glowMode = "landing";
  } else {
    out.s = K.land;
    out.markAlpha = 1;
    out.shadowAlpha = 0.55;
    out.glowMode = "landing";
    out.siliconCopyA = easeO(seg(g, BEATS.siliconRest) * 3);
  }
  return out;
};

/* ---- engine layout: four columns inside the full panel ---- */
type EngineLayout = { x: number; y: number; w: number; h: number; colW: number };

const engineLayout = (s: BlockState, wide: boolean): EngineLayout => {
  const pad = Math.min(s.w, s.h) * 0.12;
  const copyGutter = wide ? s.w * 0.32 : 0;
  const x = s.cx - s.w / 2 + pad + copyGutter;
  const y = s.cy - s.h / 2 + pad * 1.4;
  const w = s.w - pad * 2 - copyGutter;
  const h = s.h - pad * 2.4;
  return { x, y, w, h, colW: w / 4 };
};

const GRID = 5;
const FAIL = [1, 4, 7, 13, 18, 22];
const ENGINE_LABELS = ["RL ENV", "EVALS", "POST-TRAIN", "OUTPUT"];

export const HomeFlow = (): ReactElement => {
  const runwayRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const blockRef = useRef<HTMLDivElement>(null);
  const shadowRef = useRef<HTMLDivElement>(null);
  const markRef = useRef<HTMLDivElement>(null);
  const engineCopyRef = useRef<HTMLDivElement>(null);
  const siliconCopyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const runway = runwayRef.current;
    const canvas = canvasRef.current;
    const block = blockRef.current;
    const shadowEl = shadowRef.current;
    const mark = markRef.current;
    const engineCopy = engineCopyRef.current;
    const siliconCopy = siliconCopyRef.current;
    if (!runway || !canvas || !block || !shadowEl || !mark || !engineCopy || !siliconCopy)
      return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* Theme colours, re-read when the theme flips (theme.ts sets data-theme
       on the root; the system scheme flips a media query). */
    let seats: string[] = [];
    let ink = "#2F2D29";
    let veil: [number, number, number] = [255, 255, 255];
    const readTheme = (): void => {
      const cs = getComputedStyle(document.documentElement);
      const at = (name: string, fall: string): string =>
        cs.getPropertyValue(name).trim() || fall;
      seats = SEAT_TOKENS.map((n, i) =>
        at(n, ["#be5e31", "#e9b748", "#5e6043", "#407486", "#c8c1b4"][i]),
      );
      ink = at("--color-text", "#2F2D29");
      const panel = at("--color-panel", "#ffffff");
      const m = /^#([0-9a-f]{6})$/i.exec(panel);
      if (m) {
        veil = [
          parseInt(m[1].slice(0, 2), 16),
          parseInt(m[1].slice(2, 4), 16),
          parseInt(m[1].slice(4, 6), 16),
        ];
      }
    };
    readTheme();
    const themeWatch = new MutationObserver(readTheme);
    themeWatch.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    const scheme = matchMedia("(prefers-color-scheme: dark)");
    scheme.addEventListener("change", readTheme);

    let W = 0;
    let H = 0;
    const resize = (): void => {
      W = window.innerWidth;
      H = window.innerHeight;
      const dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    addEventListener("resize", resize);

    const drawBlobs = (t: number, out: TimelineOut): void => {
      const { s, glowMode, frost } = out;
      const wide = W > 720;
      for (let i = 0; i < 4; i++) {
        let bx: number, by: number, rad: number, alpha: number;
        const drift = t * 0.18 + i * 1.7;
        if (glowMode === "engine") {
          if (i > 1) continue;
          const col = engineLayout(s, wide);
          bx = col.x + col.colW * 2.5 + Math.sin(drift) * col.colW * 0.18;
          by = col.y + col.h * (0.5 + Math.cos(drift * 1.3) * 0.14);
          rad = col.colW * 0.55;
          alpha = 0.5;
        } else if (glowMode === "landing") {
          bx = s.cx + Math.sin(drift) * s.w * 0.3;
          by = s.cy + s.h * 0.85 + Math.cos(drift * 0.8) * s.h * 0.08;
          rad = s.w * (0.85 + 0.15 * Math.sin(drift * 0.6));
          alpha = 0.6;
        } else {
          bx = s.cx + Math.sin(drift) * s.w * 0.22;
          by = s.cy + Math.cos(drift * 0.77) * s.h * 0.22;
          rad = s.w * 0.34;
          alpha = 0.65 * Math.max(frost, 0.2);
        }
        const c = seats[(i + Math.floor(t * 0.25)) % seats.length];
        const gr = ctx.createRadialGradient(bx, by, 0, bx, by, rad);
        gr.addColorStop(0, c + "cc");
        gr.addColorStop(1, c + "00");
        ctx.globalAlpha = alpha;
        ctx.fillStyle = gr;
        ctx.fillRect(bx - rad, by - rad, rad * 2, rad * 2);
      }
      ctx.globalAlpha = 1;
    };

    const drawEngine = (t: number, out: TimelineOut): void => {
      const { s, engineA } = out;
      if (engineA <= 0.01) return;
      const wide = W > 720;
      const L = engineLayout(s, wide);
      const T = (t % ENGINE_CYCLE_S) / ENGINE_CYCLE_S;
      ctx.save();
      ctx.strokeStyle = ink;
      ctx.fillStyle = ink;
      ctx.lineWidth = 1;
      ctx.font = "10px 'JetBrains Mono', ui-monospace, monospace";

      for (let c = 0; c < 4; c++) {
        const cx0 = L.x + c * L.colW + 6;
        const cw = L.colW - 12;
        ctx.globalAlpha = engineA * 0.35;
        ctx.strokeRect(cx0, L.y, cw, L.h);
        ctx.globalAlpha = engineA * 0.7;
        ctx.fillText(ENGINE_LABELS[c], cx0, L.y - 8);
      }

      const cell = Math.min((L.colW - 40) / GRID, (L.h - 60) / GRID);
      const bit = Math.max(4, cell * 0.42);
      const gridAt = (c: number, i: number): [number, number] => {
        const gx = L.x + c * L.colW + (L.colW - GRID * cell) / 2;
        const gy = L.y + (L.h - GRID * cell) / 2;
        return [
          gx + (i % GRID) * cell + cell / 2,
          gy + Math.floor(i / GRID) * cell + cell / 2,
        ];
      };
      const N = GRID * GRID;

      for (let i = 0; i < N; i++) {
        const stagger = ((i * 7919) % N) / N;
        let px: number,
          py: number,
          alpha = 1,
          hollow = false,
          size = bit;

        if (T < 0.28) {
          const tt = clamp01((T / 0.28 - stagger * 0.7) / 0.3);
          if (tt <= 0) continue;
          const [gx, gy] = gridAt(0, i);
          px = lerp(L.x - 40, gx, easeO(tt));
          py = lerp(L.y + L.h * stagger, gy, easeO(tt));
        } else if (T < 0.42) {
          const tt = easeIO(clamp01((T - 0.28) / 0.14));
          const [ax, ay] = gridAt(0, i);
          const [bx, by] = gridAt(1, i);
          px = lerp(ax, bx, tt);
          py = lerp(ay, by, tt);
        } else if (T < 0.58) {
          const [gx, gy] = gridAt(1, i);
          px = gx;
          py = gy;
          const scanY = L.y + ((T - 0.42) / 0.16) * L.h;
          if (FAIL.includes(i) && gy < scanY) {
            hollow = true;
            alpha = 0.35;
          }
        } else if (T < 0.78) {
          if (FAIL.includes(i)) {
            const tt = clamp01((T - 0.58) / 0.1);
            const [gx, gy] = gridAt(1, i);
            px = gx;
            py = gy + tt * 24;
            alpha = 0.35 * (1 - tt);
            hollow = true;
            if (alpha < 0.02) continue;
          } else {
            const tt = easeIO(clamp01((T - 0.58) / 0.2));
            const [ax, ay] = gridAt(1, i);
            const k = i % 9;
            const dx = L.x + 2.5 * L.colW + ((k % 3) - 1) * bit * 1.6;
            const dy = L.y + L.h / 2 + (Math.floor(k / 3) - 1) * bit * 1.6;
            px = lerp(ax, dx, tt);
            py = lerp(ay, dy, tt);
          }
        } else {
          if (FAIL.includes(i)) continue;
          const tt = easeIO(clamp01((T - 0.78) / 0.16));
          const k = i % 9;
          const dx = L.x + 2.5 * L.colW + ((k % 3) - 1) * bit * 1.6 * (1 - tt);
          const dy = L.y + L.h / 2 + (Math.floor(k / 3) - 1) * bit * 1.6 * (1 - tt);
          px = lerp(dx, L.x + 3.5 * L.colW, tt);
          py = lerp(dy, L.y + L.h / 2, tt);
          alpha = 1 - tt * 0.4;
          size = bit * (1 - tt * 0.4);
        }

        ctx.globalAlpha = engineA * alpha;
        if (hollow) ctx.strokeRect(px - size / 2, py - size / 2, size, size);
        else ctx.fillRect(px - size / 2, py - size / 2, size, size);
      }

      if (T >= 0.86) {
        const tt = clamp01((T - 0.86) / 0.1);
        const ox = L.x + 3.5 * L.colW;
        const oy = L.y + L.h / 2;
        const os = bit * 4;
        ctx.globalAlpha = engineA * tt;
        ctx.strokeRect(ox - os / 2, oy - os / 2, os, os);
        ctx.fillRect(ox - os / 4, oy - os / 4, os / 2, os / 2);
      }
      ctx.restore();
    };

    /* ---- the loop ---- */
    let targetP = 0;
    let g = reduced ? 1 : 0;
    let lastT = performance.now();
    let raf = 0;

    const readScroll = (): void => {
      const rect = runway.getBoundingClientRect();
      const span = rect.height - H;
      targetP = span > 0 ? clamp01(-rect.top / span) : 0;
    };

    const frame = (now: number): void => {
      const rawDt = (now - lastT) / 1000;
      lastT = now;
      const t = now / 1000;

      readScroll();
      if (!reduced) g += (targetP - g) * (1 - Math.exp(-rawDt / DAMPING_TAU));
      else g = 1;

      const out = evalTimeline(g, W, H);
      const { s } = out;

      ctx.clearRect(0, 0, W, H);
      drawBlobs(t, out);
      drawEngine(t, out);

      const place = (el: HTMLElement, extra: string): void => {
        el.style.width = `${s.w}px`;
        el.style.height = `${s.h}px`;
        el.style.transform =
          `translate(${s.cx - s.w / 2}px, ${s.cy - s.h / 2}px) ${extra} ` +
          `rotateX(${s.rx}deg) rotateZ(${s.rz}deg)`;
      };
      place(block, "");
      block.style.borderRadius = `${s.r}px`;
      const blur = (out.frost * FROST_BLUR_MAX).toFixed(1);
      block.style.backdropFilter = `blur(${blur}px)`;
      (block.style as CSSStyleDeclaration & { webkitBackdropFilter: string }).webkitBackdropFilter = `blur(${blur}px)`;
      block.style.background = `rgba(${veil[0]}, ${veil[1]}, ${veil[2]}, ${(out.frost * FROST_VEIL_MAX).toFixed(3)})`;
      block.style.borderColor = `rgba(${veil[0]}, ${veil[1]}, ${veil[2]}, ${(0.25 + out.frost * 0.35).toFixed(3)})`;
      mark.style.opacity = `${out.markAlpha}`;

      place(shadowEl, `translate(${s.w * 0.06}px, ${s.h * 0.14}px)`);
      shadowEl.style.opacity = `${out.shadowAlpha}`;

      engineCopy.style.opacity = `${out.engineCopyA}`;
      engineCopy.style.visibility = out.engineCopyA > 0.01 ? "visible" : "hidden";
      siliconCopy.style.opacity = `${out.siliconCopyA}`;
      siliconCopy.style.visibility = out.siliconCopyA > 0.01 ? "visible" : "hidden";

      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      removeEventListener("resize", resize);
      themeWatch.disconnect();
      scheme.removeEventListener("change", readTheme);
    };
  }, []);

  return (
    <div className="gr-flow" ref={runwayRef} style={{ height: `${RUNWAY_VH}vh` }}>
      <div className="gr-flow-stage">
        <canvas className="gr-flow-field" ref={canvasRef} />
        <div className="gr-flow-shadow" ref={shadowRef} />
        <div className="gr-flow-block" ref={blockRef}>
          <div className="gr-flow-mark" ref={markRef} />
        </div>

        <div className="gr-flow-copy gr-flow-copy--engine" ref={engineCopyRef}>
          <h2 className="gr-heading">Trained on your production traffic</h2>
          <p className="gr-muted">
            We rebuild your production traces as an RL environment, derive
            evals from what actually succeeded in production, and post-train an
            open model against them.
          </p>
          <p className="gr-muted">
            Post-training a model on your own workload is normally a staffing
            problem. Gradiated removes the need for that part. It&apos;s just
            an API endpoint, and your production traffic.
          </p>
        </div>

        <div className="gr-flow-copy gr-flow-copy--silicon" ref={siliconCopyRef}>
          <h2 className="gr-heading">All the way down to the silicon</h2>
          <p className="gr-muted">
            Waste in inference isn&apos;t in one place. Where possible, the
            workload should shape the silicon.
          </p>
          <p className="gr-muted">
            We design chips for specific model families and provide the weights
            we generate.
          </p>
        </div>
      </div>
    </div>
  );
};
