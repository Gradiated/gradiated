import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { Logo } from "./Logo";

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
 * Mostly monochrome, by rule: the pipeline plays in ink on the panel, and
 * the hero's gradient combo appears only around the chip in the dark
 * reveal (see GRADIENT RULE below). The wafer field behind the chip is a
 * fragment shader — silver dots with a holographic tint that blooms once,
 * when the lights-off ripple passes through.
 */

/* ---- timeline ----
   Beats in scroll progress 0..1 across the runway. engineRest and
   siliconRest are the reading rests. */
const BEATS = {
  rise: [0.0, 0.06],
  clarify: [0.06, 0.15],
  engineRest: [0.15, 0.46],
  refrost: [0.46, 0.58],
  /* frontal hold: the lights snap off the moment the square forms, the G
     lights up, and the sheen makes its pass while the chip is straight on */
  chipHold: [0.58, 0.7],
  land: [0.7, 0.85],
  siliconRest: [0.85, 1.0],
} as const;

/** Runway height in viewport-heights; the scrub's total scroll distance. */
export const RUNWAY_VH = 700;

/** Time constant of the damped chase (seconds). The object's weight. */
const DAMPING_TAU = 0.14;

/** RAW-STYLE EXPLORATION (25 Sep): one aesthetic for the whole page — the
    engine's ink technical-drawing language. True = flat monochrome dark
    stage (no metal, no flare, no gradient glow, no interference colour).
    Flip to false to restore the cinematic rendering. */
const RAW_STYLE = true;

const FROST_BLUR_MAX = 26;
const FROST_VEIL_MAX = 0.72;

/** One generation's full choreography length, in wall-clock seconds —
    the original hero's CYCLE, plus the tail of the die's exit. */
const GEN_LEN = 10.2;

/** A NEW generation launches this often. Shorter than GEN_LEN, so the
    stages pipeline: while one generation's die is forming its model, the
    next generation's traces are already landing in the RL environment —
    production traffic never stops coming in. */
const GEN_PERIOD = 6.5;

/* GRADIENT RULE (from the user, 24 Sep): the hero's seat combo appears in
   exactly two places — the hero beam itself, and the dynamic glow around
   the chip in the ISOMETRIC view. The frontal dark stage is lit by one
   source only: the sweep that crosses plate and wafers together. */
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
  /* landing beats: the plate is a solid DOM surface (it rotates in 3D,
     which the canvas panel cannot), so the canvas stops painting it */
  solid: boolean;
  /* the showstopper: lights hard-off from the moment the square forms */
  dark: boolean;
  /* progress of the sheen's single pass, during the frontal hold */
  sheenT: number;
  /* the gradient glow belongs to the isometric view only */
  glowA: number;
};

const keyStates = (
  W: number,
  H: number,
): Record<"peek" | "rise" | "full" | "chip" | "land", BlockState> => {
  const vm = Math.min(W, H);
  /* The expanded panel keeps a generous page border: the user is peering
     INTO a box sitting on the page, so the page must stay visible. */
  const inset = Math.max(36, vm * 0.055);
  const wide = W > 720;
  /* Anchored by its TOP edge so the peek height under the hero is stable
     across viewport sizes — pairs with .gr-flow's -34vh overlap. */
  const peekSize = Math.min(W * 0.46, 560);
  return {
    peek: { cx: W / 2, cy: H * 0.2 + peekSize / 2, w: peekSize, h: peekSize, r: 2, rx: 0, rz: 0 },
    rise: { cx: W / 2, cy: H * 0.52, w: vm * 0.64, h: vm * 0.64, r: 2, rx: 0, rz: 0 },
    full: { cx: W / 2, cy: H / 2, w: W - inset * 2, h: H - inset * 2, r: 6, rx: 0, rz: 0 },
    chip: { cx: W / 2, cy: H * 0.5, w: vm * 0.46, h: vm * 0.46, r: 12, rx: 0, rz: 0 },
    land: { cx: W * (wide ? 0.34 : 0.5), cy: H * (wide ? 0.52 : 0.38), w: vm * 0.42, h: vm * 0.42, r: 12, rx: 58, rz: 45 },
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
    solid: false,
    dark: false,
    sheenT: 0,
    glowA: 0,
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
    const t = seg(g, BEATS.engineRest);
    out.engineCopyA = Math.min(easeO(t * 3), 1 - clamp01((t - 0.82) / 0.18));
  } else if (g < BEATS.refrost[1]) {
    const t = easeIO(seg(g, BEATS.refrost));
    out.s = mixState(K.full, K.chip, t);
    out.frost = t;
    out.engineA = 1 - t;
  } else if (g < BEATS.chipHold[1]) {
    out.s = K.chip;
    out.solid = true;
    out.dark = true;
    out.markAlpha = 1;
    out.sheenT = seg(g, BEATS.chipHold);
  } else if (g < BEATS.land[1]) {
    const t = easeIO(seg(g, BEATS.land));
    out.s = mixState(K.chip, K.land, t);
    out.markAlpha = 1;
    out.shadowAlpha = easeO(clamp01((t - 0.3) / 0.7)) * 0.55;
    out.solid = true;
    out.dark = true;
    out.sheenT = 1;
    out.glowA = easeIO(t);
  } else {
    out.s = K.land;
    out.markAlpha = 1;
    out.shadowAlpha = 0.55;
    out.solid = true;
    out.dark = true;
    out.sheenT = 1;
    out.glowA = 1;
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

/* ---- engine data ----
   The original hero's pipeline, flattened: a seeded maze whose WALL cells
   are the chips (each chip is one captured trace), a BFS rollout through
   it, an eval grid ordered so the drop is straight, and the passers packed
   into the die. All positions are stored normalised (0..1 within their
   stage box) and mapped to pixels at draw time, so the layout can breathe
   with the viewport. Seeded so every visit renders the same environment. */
const ENGINE_LABELS = ["PRODUCTION TRAFFIC", "RL ENV", "EVALS", "POST-TRAIN"];

/** When each stage's frame materialises, in seconds since the engine's
    reveal — the layer-by-layer build-in. Frames persist once drawn. */
/* Each frame lands just BEFORE its first chips do: the maze starts filling
   at ~1.6, the eval drop starts at 3.6, the die packs from 6.15. */
const STAGE_APPEARS = [0.0, 1.2, 3.5, 5.9];

const MR = 31;
const MC = 15;

type Bit = {
  sx: number; sy: number; /* scatter in the traffic column */
  mx: number; my: number; /* maze wall cell */
  ex: number; ey: number; /* eval grid slot */
  du: number; dv: number; /* die offset, in bit-spacing units */
  delay: number;
  ta: number;  /* when this trace trickles into the traffic column,
                  as a fraction of the previous generation's period */
  pass: boolean;
  tv: number;   /* when the scan reaches this chip */
  k6: number;   /* when this chip leaves the die */
  dist: number; /* normalised distance from die centre (the ripple's phase) */
};

const ENGINE = ((): { bits: Bit[]; path: [number, number][]; DS: number } => {
  let seedState = 11;
  const rnd = (): number => {
    seedState = (seedState * 16807) % 2147483647;
    return (seedState - 1) / 2147483646;
  };

  /* Recursive-backtracker maze (iterative), plus a few opened loops so it
     reads as rooms rather than a puzzle. Entry top, exit bottom. */
  const maze: number[][] = Array.from({ length: MR }, () => Array(MC).fill(1));
  const stack: [number, number][] = [[1, 1]];
  maze[1][1] = 0;
  while (stack.length) {
    const [r, c] = stack[stack.length - 1];
    const dirs: [number, number][] = [[0, 2], [0, -2], [2, 0], [-2, 0]];
    for (let i = dirs.length - 1; i > 0; i--) {
      const j = Math.floor(rnd() * (i + 1));
      [dirs[i], dirs[j]] = [dirs[j], dirs[i]];
    }
    let moved = false;
    for (const [dr, dc] of dirs) {
      const nr = r + dr;
      const nc = c + dc;
      if (nr > 0 && nr < MR - 1 && nc > 0 && nc < MC - 1 && maze[nr][nc] === 1) {
        maze[r + dr / 2][c + dc / 2] = 0;
        maze[nr][nc] = 0;
        stack.push([nr, nc]);
        moved = true;
        break;
      }
    }
    if (!moved) stack.pop();
  }
  for (let k = 0; k < 10; k++) {
    const r = 1 + Math.floor(rnd() * (MR - 2));
    const c = 1 + Math.floor(rnd() * (MC - 2));
    if (
      maze[r][c] === 1 &&
      ((maze[r - 1][c] === 0 && maze[r + 1][c] === 0) ||
        (maze[r][c - 1] === 0 && maze[r][c + 1] === 0))
    )
      maze[r][c] = 0;
  }
  maze[0][1] = 0;
  maze[MR - 1][MC - 2] = 0;

  /* The rollout: BFS entry -> exit, normalised. */
  const key = (r: number, c: number): number => r * MC + c;
  const prev = new Map<number, [number, number] | null>([[key(0, 1), null]]);
  const q: [number, number][] = [[0, 1]];
  while (q.length) {
    const [r, c] = q.shift() as [number, number];
    if (r === MR - 1 && c === MC - 2) break;
    for (const [dr, dc] of [[0, 1], [1, 0], [0, -1], [-1, 0]]) {
      const nr = r + dr;
      const nc = c + dc;
      if (nr < 0 || nc < 0 || nr >= MR || nc >= MC || maze[nr][nc] || prev.has(key(nr, nc)))
        continue;
      prev.set(key(nr, nc), [r, c]);
      q.push([nr, nc]);
    }
  }
  const path: [number, number][] = [];
  let cur: [number, number] | null = [MR - 1, MC - 2];
  while (cur) {
    path.unshift([cur[1] / (MC - 1), cur[0] / (MR - 1)]);
    cur = prev.get(key(cur[0], cur[1])) ?? null;
  }

  /* Wall cells become the chips. */
  const walls: [number, number][] = [];
  for (let r = 0; r < MR; r++)
    for (let c = 0; c < MC; c++) if (maze[r][c]) walls.push([r, c]);
  const bits: Bit[] = walls.map(([r, c]) => ({
    mx: c / (MC - 1),
    my: r / (MR - 1),
    sx: 0.06 + rnd() * 0.88,
    sy: 0.06 + rnd() * 0.88,
    ex: 0,
    ey: 0,
    du: 0,
    dv: 0,
    delay: rnd() * 0.9,
    ta: rnd(),
    pass: rnd() < 0.78,
    tv: 0,
    k6: 0,
    dist: 0,
  }));

  /* Eval grid, ordered by maze position so the drop reads straight; the
     scan sweeps downward, so trigger times follow the row. */
  const EC = 9;
  const ER = Math.ceil(bits.length / EC);
  [...bits]
    .sort((a, b) => a.my - b.my || a.mx - b.mx)
    .forEach((b, rank) => {
      const cc = rank % EC;
      const rr = Math.floor(rank / EC);
      b.ex = cc / (EC - 1);
      b.ey = rr / Math.max(1, ER - 1);
      b.tv = 4.8 + b.ey * 1.0;
    });

  /* Passers pack into the die; the ripple and the exit stagger both run on
     distance from the die's centre. */
  const passers = bits.filter((b) => b.pass).sort((a, b) => a.ey - b.ey || a.ex - b.ex);
  const DS = Math.ceil(Math.sqrt(passers.length));
  let maxD = 0.0001;
  passers.forEach((b, rank) => {
    b.du = (rank % DS) - (DS - 1) / 2;
    b.dv = Math.floor(rank / DS) - (DS - 1) / 2;
    b.dist = Math.hypot(b.du, b.dv);
    maxD = Math.max(maxD, b.dist);
  });
  passers.forEach((b) => {
    b.dist /= maxD;
    /* near-uniform exit, so the formed square drops into the registry as
       one object rather than dissolving */
    b.k6 = 8.4 + 0.1 * b.dist;
  });

  return { bits, path, DS };
})();

const bez2 = (
  ax: number, ay: number, bx: number, by: number,
  cx: number, cy: number, dx: number, dy: number,
  u: number,
): [number, number] => {
  const v = 1 - u;
  const w0 = v * v * v;
  const w1 = 3 * v * v * u;
  const w2 = 3 * v * u * u;
  const w3 = u * u * u;
  return [
    ax * w0 + bx * w1 + cx * w2 + dx * w3,
    ay * w0 + by * w1 + cy * w2 + dy * w3,
  ];
};

export const HomeFlow = (): ReactElement => {
  const runwayRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const blockRef = useRef<HTMLDivElement>(null);
  const shadowRef = useRef<HTMLDivElement>(null);
  const markRef = useRef<HTMLDivElement>(null);
  const sheenRef = useRef<HTMLDivElement>(null);
  const topRef = useRef<HTMLDivElement>(null);
  const faceSRef = useRef<HTMLDivElement>(null);
  const faceERef = useRef<HTMLDivElement>(null);
  const glRef = useRef<HTMLCanvasElement>(null);
  const overRef = useRef<HTMLCanvasElement>(null);
  const engineCopyRef = useRef<HTMLDivElement>(null);
  const siliconCopyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const runway = runwayRef.current;
    const canvas = canvasRef.current;
    const block = blockRef.current;
    const shadowEl = shadowRef.current;
    const mark = markRef.current;
    const sheen = sheenRef.current;
    const top = topRef.current;
    const faceS = faceSRef.current;
    const faceE = faceERef.current;
    const glCanvas = glRef.current;
    const overCanvas = overRef.current;
    const engineCopy = engineCopyRef.current;
    const siliconCopy = siliconCopyRef.current;
    if (!runway || !canvas || !block || !shadowEl || !mark || !sheen || !top || !faceS || !faceE || !glCanvas || !overCanvas || !engineCopy || !siliconCopy)
      return;
    const ctx = canvas.getContext("2d");
    const ctx2 = overCanvas.getContext("2d");
    if (!ctx || !ctx2) return;

    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* Theme colours, re-read when the theme flips (theme.ts sets data-theme
       on the root; the system scheme flips a media query). */
    /* Tokens are scoped to .gr-root (see tokens.css), and the theme
       attribute lives there too — so that element, not documentElement, is
       what we read from, watch, and flip. */
    const rootEl = (canvas.closest(".gr-root") as HTMLElement) ?? document.documentElement;

    let ink = "#2F2D29";
    let veil: [number, number, number] = [255, 255, 255];
    let seats: string[] = [];
    let forcedDark = false;
    let prevTheme: string | undefined;
    let darkAt = 0;
    /* The flip is an EVENT, but the paint eases: arm a transition class
       just before the theme changes, disarm once the glide is over so
       normal interactions are never slowed. */
    let easeTimer = 0;
    const easeThemeFlip = (): void => {
      rootEl.classList.add("gr-theme-ease");
      clearTimeout(easeTimer);
      easeTimer = window.setTimeout(
        () => rootEl.classList.remove("gr-theme-ease"),
        550,
      );
    };
    const readTheme = (): void => {
      const cs = getComputedStyle(rootEl);
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
    themeWatch.observe(rootEl, {
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
      overCanvas.width = W * dpr;
      overCanvas.height = H * dpr;
      ctx2.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    addEventListener("resize", resize);

    /* The box itself, painted on the canvas so the engine can sit ON its
       surface while the page stays visible around it — the user is peering
       inside a box, not watching the page become one. The DOM element above
       supplies only the frost (backdrop blur + veil), and becomes the solid
       plate during the landing beats, where the canvas cannot follow the 3D
       rotation. */
    const drawPanel = (out: TimelineOut): void => {
      if (out.solid) return;
      const { s } = out;
      ctx.save();
      ctx.beginPath();
      ctx.roundRect(s.cx - s.w / 2, s.cy - s.h / 2, s.w, s.h, s.r);
      ctx.fillStyle = `rgb(${veil[0]}, ${veil[1]}, ${veil[2]})`;
      ctx.fill();
      ctx.restore();
    };

    /* The hero's gradient combo around the chip — isometric view only,
       tight and restrained, drawn over the wafer layer so it visibly
       shines onto the dots below. */
    const drawGlow = (t: number, out: TimelineOut): void => {
      if (RAW_STYLE || out.glowA <= 0.01) return;
      const { s } = out;
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      for (let i = 0; i < 4; i++) {
        const a = t * 0.26 + i * 1.57;
        const bx = s.cx + Math.cos(a) * s.w * 0.42;
        const by = s.cy + s.h * 0.12 + Math.sin(a) * s.h * 0.34;
        const rad = s.w * (0.36 + 0.05 * Math.sin(t * 0.8 + i * 2.1));
        const gr = ctx.createRadialGradient(bx, by, 0, bx, by, rad);
        gr.addColorStop(0, seats[i % seats.length] + "55");
        gr.addColorStop(1, seats[i % seats.length] + "00");
        ctx.globalAlpha = 0.32 * out.glowA;
        ctx.fillStyle = gr;
        ctx.fillRect(bx - rad, by - rad, rad * 2, rad * 2);
      }
      ctx.restore();
    };

    /* ---- the wafer field ----
       A dense field of tiny dots behind the chip, with a holographic
       (thin-film) sheen — a fragment shader, because the iridescence is a
       per-pixel palette keyed to radius and angle. When the lights go off
       a single ripple runs outward through it, once, then the field rests
       with only the slow holographic drift. */
    const glOK = (() => {
      const gl = glCanvas.getContext("webgl", { alpha: true, premultipliedAlpha: false });
      if (!gl) return null;
      const vsrc = "attribute vec2 aP; void main(){ gl_Position = vec4(aP, 0.0, 1.0); }";
      const fsrc = `
precision mediump float;
uniform vec2  uRes;    /* canvas size, device px */
uniform vec2  uC;      /* chip centre, device px */
uniform float uSize;   /* chip width, device px */
uniform float uCell;   /* wafer grid pitch, device px — sized so the dies
                          match the engine's data-bits exactly */
uniform float uRing;   /* the reveal: perimeter wavefront progress 0..1 */
uniform float uPulse;  /* the chip light's slow breath */
uniform float uOn;
/* rounded-rect distance, so the wave carries the chip's own geometry */
float sdBox(vec2 q, vec2 b, float r) {
  vec2 dq = abs(q) - b;
  return length(max(dq, vec2(0.0))) + min(max(dq.x, dq.y), 0.0) - r;
}
void main() {
  vec2 p = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y);
  vec2 d = p - uC;
  float cell = uCell;
  vec2 gpos = d / cell;
  vec2 id = floor(gpos + 0.5);
  vec2 lp = gpos - id;
  /* distance outward from the plate's edge, normalised */
  vec2 cc = (id * cell);
  float dr = sdBox(cc, vec2(uSize * 0.5), uSize * 0.02);
  float dn = dr / (uSize * 1.35);
  if (dn > 1.0) discard;
  /* square wafer chips, not dots */
  float q = max(abs(lp.x), abs(lp.y));
  float m = 1.0 - smoothstep(0.26, 0.30, q);
  if (m <= 0.0) discard;
  /* THE light is the chip. Its pool of light falls off from the plate
     edge; the reveal is a wavefront in the plate's geometry expanding
     outward, and the field only exists where light has reached. */
  float front = uRing * 1.25;
  float x = (dn - front) * 3.4;
  float band = exp(-x * x * 4.0);
  float wake = smoothstep(front, front - 0.3, dn);
  float pool = exp(-max(dn, 0.0) * 2.4) * uPulse;
  /* REAL thin-film interference on the wavefront. The film is a MATERIAL
     property: near-uniform thickness with only a slow drift across the
     wafer (never per-die), so the colour is spatially coherent -- smooth
     Newton-ring contours around the passing light, neighbours sharing
     hue. Per-die randomness touches brightness only (die reflectivity),
     never colour: colour is the light's doing, not the chip's. */
  float grain = fract(sin(dot(id, vec2(12.9898, 78.233))) * 43758.5453);
  float dfilm = 430.0 + 45.0 * sin(cc.x * 0.0011 + cc.y * 0.0007);  /* nm */
  float cosT = inversesqrt(1.0 + x * x * 0.35);
  float opd = 2.0 * 1.46 * dfilm * cosT;          /* n(SiO2)=1.46 */
  vec3 lambda = vec3(630.0, 532.0, 465.0);
  vec3 film = 0.5 - 0.5 * cos(6.2831 * opd / lambda);
  vec3 col = mix(vec3(0.72), film * 1.15 + 0.3, band);
  ${RAW_STYLE ? "col = vec3(0.92); /* raw: light is brightness only */" : ""}
  float refl = 0.9 + 0.2 * grain;                 /* die-to-die brightness */
  float a = m * refl * (0.04 + 0.55 * band + wake * pool * 0.6) * uOn;
  gl_FragColor = vec4(col, a);
}`;
      const sh = (type: number, src: string): WebGLShader | null => {
        const s = gl.createShader(type);
        if (!s) return null;
        gl.shaderSource(s, src);
        gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
          console.warn("[HomeFlow] wafer shader:", gl.getShaderInfoLog(s));
          return null;
        }
        return s;
      };
      const vs = sh(gl.VERTEX_SHADER, vsrc);
      const fs = sh(gl.FRAGMENT_SHADER, fsrc);
      const prog = gl.createProgram();
      if (!vs || !fs || !prog) return null;
      gl.attachShader(prog, vs);
      gl.attachShader(prog, fs);
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
      gl.useProgram(prog);
      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      const aP = gl.getAttribLocation(prog, "aP");
      gl.enableVertexAttribArray(aP);
      gl.vertexAttribPointer(aP, 2, gl.FLOAT, false, 0, 0);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      return {
        gl,
        u: {
          res: gl.getUniformLocation(prog, "uRes"),
          c: gl.getUniformLocation(prog, "uC"),
          size: gl.getUniformLocation(prog, "uSize"),
          cell: gl.getUniformLocation(prog, "uCell"),
          ring: gl.getUniformLocation(prog, "uRing"),
          pulse: gl.getUniformLocation(prog, "uPulse"),
          on: gl.getUniformLocation(prog, "uOn"),
        },
      };
    })();

    /* RAW: the G emits — a fading stream of the hero field's glyphs rising
       out of the chip in the isometric rest. Species by intensity, exactly
       the hero's ladder, so the two ends of the page speak one language. */
    const drawEmission = (t: number, out: TimelineOut): void => {
      ctx2.clearRect(0, 0, W, H);
      if (!RAW_STYLE || out.glowA <= 0.01) return;
      const { s } = out;
      ctx2.save();
      ctx2.strokeStyle = ink;
      ctx2.fillStyle = ink;
      ctx2.lineWidth = 1;
      const N = 42;
      const len = s.h * 1.2;
      /* the stream pours from the G itself: its PROJECTED position, since
         the plate is tilted in 3D and the geometric centre is elsewhere */
      const mb = mark.getBoundingClientRect();
      const ox = mb.left + mb.width / 2;
      const oy = mb.top + mb.height / 2;
      for (let i = 0; i < N; i++) {
        const lane = i % 3;
        const ph = (t * 0.14 + i / N) % 1;
        const x =
          ox + (lane - 1) * mb.width * 0.28 + Math.sin(ph * 5 + i * 2.4) * s.w * 0.06 * ph;
        const y = oy - ph * len;
        const inten = (1 - ph) * out.glowA;
        if (inten < 0.05) continue;
        ctx2.globalAlpha = Math.min(1, inten * 1.2) * 0.8;
        if (inten < 0.2) ctx2.fillRect(x - 0.75, y - 0.75, 1.5, 1.5);
        else if (inten < 0.35) ctx2.fillRect(x - 3, y - 0.75, 6, 1.5);
        else if (inten < 0.5) ctx2.strokeRect(x - 2.5, y - 2.5, 5, 5);
        else if (inten < 0.68) {
          ctx2.beginPath();
          ctx2.moveTo(x - 3, y - 3);
          ctx2.lineTo(x + 3, y + 3);
          ctx2.moveTo(x + 3, y - 3);
          ctx2.lineTo(x - 3, y + 3);
          ctx2.stroke();
        } else if (inten < 0.85) {
          ctx2.strokeRect(x - 3.5, y - 3.5, 7, 7);
          ctx2.fillRect(x - 1, y - 1, 2, 2);
        } else ctx2.fillRect(x - 2.5, y - 2.5, 5, 5);
      }
      ctx2.restore();
    };

    /* ---- the solar flare ----
       As the reveal launches, light bursts from behind the plate: a core
       bloom plus chromatically split streaks along the horizontal — drawn
       additively UNDER the plate, so it reads as light escaping its edges. */
    const drawFlare = (out: TimelineOut): void => {
      if (RAW_STYLE || !out.dark) return;
      const st = easeIO(clamp01((out.sheenT - 0.12) / 0.72));
      const fi = Math.exp(-Math.pow((st - 0.28) * 3.4, 2)) * (1 - out.glowA);
      if (fi <= 0.015) return;
      const { s } = out;
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      const core = ctx.createRadialGradient(s.cx, s.cy, 0, s.cx, s.cy, s.w * 0.95);
      core.addColorStop(0, `rgba(255, 250, 240, ${(0.45 * fi).toFixed(3)})`);
      core.addColorStop(1, "rgba(255, 250, 240, 0)");
      ctx.fillStyle = core;
      ctx.fillRect(s.cx - s.w, s.cy - s.w, s.w * 2, s.w * 2);
      /* streaks: warm above, white centre, cool below — the split */
      const streak = (tint: string, dy: number, lenF: number, thF: number, a: number): void => {
        ctx.save();
        ctx.translate(s.cx, s.cy + dy);
        ctx.scale(s.w * lenF, s.w * thF);
        const g2 = ctx.createRadialGradient(0, 0, 0, 0, 0, 1);
        g2.addColorStop(0, tint.replace("$A", (a * fi).toFixed(3)));
        g2.addColorStop(1, tint.replace("$A", "0"));
        ctx.fillStyle = g2;
        ctx.fillRect(-1, -1, 2, 2);
        ctx.restore();
      };
      streak("rgba(255, 208, 156, $A)", -2, 1.55, 0.028, 0.55);
      streak("rgba(255, 252, 246, $A)", 0, 1.8, 0.016, 0.9);
      streak("rgba(158, 198, 255, $A)", 2, 1.55, 0.028, 0.5);
      streak("rgba(255, 252, 246, $A)", 0, 0.55, 0.11, 0.35);
      ctx.restore();
    };

    const drawWafers = (t: number, out: TimelineOut, darkAt: number): void => {
      if (!glOK) return;
      const { gl, u } = glOK;
      const dpr = Math.min(devicePixelRatio || 1, 2);
      if (glCanvas.width !== W * dpr || glCanvas.height !== H * dpr) {
        glCanvas.width = W * dpr;
        glCanvas.height = H * dpr;
      }
      gl.viewport(0, 0, glCanvas.width, glCanvas.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      const on = out.dark ? clamp01((t - darkAt) / 0.2) : 0;
      if (on <= 0.001) return;
      gl.uniform2f(u.res, glCanvas.width, glCanvas.height);
      gl.uniform2f(u.c, out.s.cx * dpr, out.s.cy * dpr);
      gl.uniform1f(u.size, out.s.w * dpr);
      /* the engine's bit size, replicated from drawEngine's layout math,
         so wafer dies and pipeline data-bits are the same chip */
      const KF = keyStates(W, H).full;
      const LF = engineLayout(KF, W > 720);
      const bitF = Math.max(3, ((LF.colW - 44) / (MC - 1)) * 0.42);
      gl.uniform1f(u.cell, (bitF / 0.56) * dpr);
      block.style.setProperty("--bit", `${bitF.toFixed(1)}px`);
      /* the reveal wavefront: scrubbed from the hold beat, eased
         identically to the plate's sheen — one light, one event */
      const stE = easeIO(clamp01((out.sheenT - 0.12) / 0.72));
      gl.uniform1f(u.ring, stE);
      gl.uniform1f(u.pulse, 0.88 + 0.12 * Math.sin(t * 1.1));
      gl.uniform1f(u.on, on);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    /* tE is time since the engine's reveal: it drives the one-time layer
       build-in, and every generation's phase is derived from it. */
    const drawEngine = (tE: number, out: TimelineOut): void => {
      const { s, engineA } = out;
      if (engineA <= 0.01 || tE < 0) return;
      const wide = W > 720;
      const L = engineLayout(s, wide);
      ctx.save();
      ctx.strokeStyle = ink;
      ctx.fillStyle = ink;
      ctx.lineWidth = 1;
      ctx.font = "10px 'JetBrains Mono', ui-monospace, monospace";

      /* Stage boxes, materialising layer by layer on first reveal. */
      const stageA: number[] = [];
      const boxes: { x: number; y: number; w: number; h: number }[] = [];
      for (let c = 0; c < 4; c++) {
        stageA[c] = clamp01((tE - STAGE_APPEARS[c]) / 0.6);
        const bx = L.x + c * L.colW + 6;
        const bw = L.colW - 12;
        boxes[c] = { x: bx, y: L.y, w: bw, h: L.h };
        if (stageA[c] <= 0) continue;
        ctx.globalAlpha = engineA * stageA[c] * 0.35;
        ctx.strokeRect(bx, L.y, bw, L.h);
        ctx.globalAlpha = engineA * stageA[c] * 0.7;
        ctx.fillText(ENGINE_LABELS[c], bx, L.y - 8);
      }

      /* Content rects fill their stage boxes edge to edge — non-square cell
         spacing is fine for square chips, and empty container is not. */
      const pad = (b: { x: number; y: number; w: number; h: number }) => ({
        x: b.x + 16,
        y: b.y + 20,
        w: b.w - 32,
        h: b.h - 40,
      });
      const traffic = pad(boxes[0]);
      const mazeBox = pad(boxes[1]);
      const evalBox = pad(boxes[2]);
      const bit = Math.max(3, (mazeBox.w / (MC - 1)) * 0.42);
      const os = bit * 4.2;

      /* POST-TRAIN is two chambers: a square at the top where the databits
         collect into the model, and a registry below that the formed model
         drops into. Four models stay visible; older ones shift up and out
         as a new one arrives. This is the loop made explicit: every
         model's production traffic seeds the next round. */
      const dieSide = Math.min(boxes[3].w - 44, boxes[3].h * 0.3);
      const dieBox = {
        x: boxes[3].x + (boxes[3].w - dieSide) / 2,
        y: boxes[3].y + 22,
        w: dieSide,
        h: dieSide,
      };
      const regBox = {
        x: boxes[3].x + 16,
        y: dieBox.y + dieBox.h + 20,
        w: boxes[3].w - 32,
        h: boxes[3].h - dieBox.h - 22 - 20 - 16,
      };
      /* One separator between the forming area and the model list — the
         column's own frame already bounds everything else. */
      if (stageA[3] > 0) {
        ctx.globalAlpha = engineA * stageA[3] * 0.35;
        ctx.fillRect(boxes[3].x, regBox.y - 10, boxes[3].w, 1);
      }
      const dieC: [number, number] = [
        dieBox.x + dieBox.w / 2,
        dieBox.y + dieBox.h / 2,
      ];
      /* the packed die fills its chamber */
      const DP = (dieSide * 0.82) / ENGINE.DS;

      /* Generation g's weights arrive in the registry at g*GEN_PERIOD+8.9. */
      const latest = Math.floor((tE - 8.9) / GEN_PERIOD);
      const startF =
        latest < 4 ? 0 : latest - 4 + clamp01((tE - (latest * GEN_PERIOD + 8.9)) / 0.5);
      /* four slots, centred vertically in the registry area */
      const slotPos = (row: number): [number, number] => [
        regBox.x + regBox.w * 0.24,
        regBox.y + regBox.h * (0.5 + (row - 1.5) * 0.22),
      ];
      const modelLabel = (k: number): string =>
        k === 0 ? "MODEL 1" : `MODEL 1.${k}`;

      const at = (
        box: { x: number; y: number; w: number; h: number },
        nx: number,
        ny: number,
      ): [number, number] => [box.x + nx * box.w, box.y + ny * box.h];

      /* Every live generation, oldest first. A generation exists from a
         full period BEFORE its launch — its traces trickle into the
         traffic column while the previous generation is still mid-flight,
         so production traffic never stops coming in — until its
         choreography ends. */
      const gLo = Math.max(0, Math.ceil((tE - GEN_LEN) / GEN_PERIOD));
      const gHi = Math.floor(tE / GEN_PERIOD) + 1;
      for (let g = gLo; g <= gHi; g++) {
      const T = tE - g * GEN_PERIOD;
      const outPt = slotPos(Math.min(g, 3));

      /* The chips. Keyframes are the original hero's, verbatim. */
      for (const b of ENGINE.bits) {
        /* trickle-in: this trace only exists once it has been captured */
        const appear = -GEN_PERIOD * (0.05 + 0.9 * b.ta);
        if (T < appear) continue;
        const d = b.delay;
        const k0 = d;
        const k1 = d + 1.6;
        const k2 = 3.6 + 0.25 * d;
        const k3 = 4.4 + 0.25 * d;
        const k4 = 6.15 + 0.2 * d;
        const k5 = 7.0 + 0.2 * d;
        const k6 = b.k6;
        const k7 = k6 + 0.7;
        let px: number;
        let py: number;
        let alpha = 1;
        let size = bit;
        let crest = 0;

        const [sxp, syp] = at(traffic, b.sx, b.sy);
        const [mxp, myp] = at(mazeBox, b.mx, b.my);

        if (T < k0) {
          /* captured traces, streaming into the endpoint */
          px = sxp; py = syp;
          alpha = 0.4 * clamp01((T - appear) / 0.4);
          size = bit * 0.8;
        } else if (T < k1) {
          /* flight into the environment */
          const u = (T - k0) / 1.6;
          const e = easeIO(u);
          [px, py] = bez2(
            sxp, syp,
            sxp + (mxp - sxp) * 0.4, syp - L.h * 0.12,
            sxp + (mxp - sxp) * 0.75, myp - L.h * 0.08,
            mxp, myp, e,
          );
          alpha = Math.min(1, 0.4 + u * 3);
        } else if (T < k2) {
          /* the maze, with a landing bob */
          px = mxp;
          py = myp - Math.max(0, Math.sin(clamp01((T - k1) / 0.35) * Math.PI)) * 3;
        } else if (T < k3) {
          /* the maze melts into the eval grid */
          const e = easeIO((T - k2) / (k3 - k2));
          const [exp_, eyp] = at(evalBox, b.ex, b.ey);
          px = lerp(mxp, exp_, e);
          py = lerp(myp, eyp, e);
        } else if (!b.pass && T > b.tv) {
          /* scanned and failed: sink and fade */
          const u = clamp01((T - b.tv) / 0.6);
          if (u >= 1) continue;
          const [exp_, eyp] = at(evalBox, b.ex, b.ey);
          px = exp_; py = eyp + u * 18; alpha = 1 - u;
        } else if (T < k4) {
          /* the grid under the scan; passers flash and hop */
          const [exp_, eyp] = at(evalBox, b.ex, b.ey);
          px = exp_; py = eyp;
          if (T > b.tv) {
            const u = clamp01((T - b.tv) / 0.5);
            py -= Math.sin(u * Math.PI) * 5;
            crest = 1 - u;
          }
        } else if (!b.pass) {
          continue;
        } else if (T < k5) {
          /* passers pack into the die */
          const e = easeIO((T - k4) / (k5 - k4));
          const [exp_, eyp] = at(evalBox, b.ex, b.ey);
          px = lerp(exp_, dieC[0] + b.du * DP, e);
          py = lerp(eyp, dieC[1] + b.dv * DP, e);
        } else if (T < k6) {
          /* the die ripples: a radial wave, crests glowing amber */
          px = dieC[0] + b.du * DP;
          py = dieC[1] + b.dv * DP;
          const ramp = clamp01((T - k5) / 0.4);
          const w = Math.sin(T * 7 - b.dist * 9);
          py += w * bit * 0.45 * ramp;
          crest = Math.max(0, w) * ramp;
          size = bit * (1 + 0.12 * crest);
        } else if (T < k7) {
          /* the trained weights fall into the chip */
          /* the formed square condenses and drops into the registry as
             one object */
          const u = (T - k6) / 0.7;
          const e = u * u;
          px = lerp(dieC[0] + b.du * DP, outPt[0] + b.du * DP * 0.1, e);
          py = lerp(dieC[1] + b.dv * DP, outPt[1] + b.dv * DP * 0.1, e);
          size = bit * (1 - e * 0.7);
          alpha = 1 - e * 0.4;
        } else {
          continue;
        }

        ctx.globalAlpha = engineA * alpha;
        ctx.fillRect(px - size / 2, py - size / 2, size, size);
      }

      /* The rollout: one highlighted chip walking the maze, with a trail. */
      const au = (T - 2.3) / 1.4;
      const trailA = au > 0 && au < 1.5 ? Math.min(1, au < 1 ? 1 : (1.5 - au) / 0.5) : 0;
      if (trailA > 0 && ENGINE.path.length > 1) {
        const f = clamp01(au) * (ENGINE.path.length - 1);
        const i0 = Math.floor(f);
        ctx.globalAlpha = engineA * trailA * 0.45;
        ctx.beginPath();
        for (let i = 0; i <= Math.min(i0 + 1, ENGINE.path.length - 1); i++) {
          const [x, y] = at(mazeBox, ENGINE.path[i][0], ENGINE.path[i][1]);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
        if (au > 0 && au < 1) {
          const i1 = Math.min(i0 + 1, ENGINE.path.length - 1);
          const [x0, y0] = at(mazeBox, ENGINE.path[i0][0], ENGINE.path[i0][1]);
          const [x1, y1] = at(mazeBox, ENGINE.path[i1][0], ENGINE.path[i1][1]);
          const ax = lerp(x0, x1, f - i0);
          const ay = lerp(y0, y1, f - i0);
          const asz = bit * 1.5;
          ctx.globalAlpha = engineA;
          ctx.fillRect(ax - asz / 2, ay - asz / 2, asz, asz);
          ctx.strokeRect(ax - asz, ay - asz, asz * 2, asz * 2);
        }
      }

      /* The scan: an x-ray line sweeping down the eval grid. */
      const bu = (T - 4.8) / 1.0;
      const bo = bu > -0.1 && bu < 1.1 ? Math.min(1, (bu + 0.1) * 5, (1.1 - bu) * 5) : 0;
      if (bo > 0) {
        const scanY = evalBox.y + evalBox.h * clamp01(bu);
        ctx.globalAlpha = engineA * bo * 0.08;
        ctx.fillRect(boxes[2].x + 4, scanY - 10, boxes[2].w - 8, 20);
        ctx.globalAlpha = engineA * bo;
        ctx.fillRect(boxes[2].x + 4, scanY, boxes[2].w - 8, 1);
      }
      } /* end of generation loop */

      /* The model registry. The arriving one fades in under its converging
         chips and pulses once; the top one fades out as the list shifts. */
      if (stageA[3] > 0 && latest >= 0) {
        ctx.font = "9px 'JetBrains Mono', ui-monospace, monospace";
        for (let m = Math.max(0, latest - 4); m <= latest; m++) {
          const since = tE - (m * GEN_PERIOD + 8.9);
          const aIn = clamp01(since / 0.5);
          if (aIn <= 0) continue;
          const rowF = m - startF;
          const a = engineA * stageA[3] * aIn * clamp01(1 + rowF);
          if (a <= 0.01) continue;
          const [mx0, my0] = slotPos(rowF);
          const oss = os * (1 + 0.1 * Math.max(0, 1 - since / 0.8));
          ctx.globalAlpha = a;
          ctx.strokeRect(mx0 - oss / 2, my0 - oss / 2, oss, oss);
          ctx.globalAlpha = a * 0.9;
          ctx.fillRect(mx0 - oss / 4, my0 - oss / 4, oss / 2, oss / 2);
          ctx.globalAlpha = a * 0.75;
          ctx.fillText(modelLabel(m), mx0 + oss / 2 + 10, my0 + 3);
        }
      }
      ctx.restore();
    };

    /* ---- the loop ---- */
    let targetP = 0;
    let g = reduced ? 1 : 0;
    let lastT = performance.now();
    let raf = 0;
    block.classList.toggle("gr-flow-block--raw", RAW_STYLE);
    /* Wall-clock moment the engine became visible; the cycle counts from
       here, so a reveal always opens on the capture phase and the layers
       build in order. Cleared when the engine frosts away again. */
    let engineStart = -1;

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

      if (out.engineA > 0.35 && engineStart < 0) engineStart = t;
      else if (out.engineA < 0.02) engineStart = -1;
      const tE = engineStart >= 0 ? t - engineStart : -1;

      /* lights hard-off the moment the square forms; back on the moment
         the scroll retreats past it */
      if (out.dark && !forcedDark) {
        prevTheme = rootEl.dataset.theme;
        easeThemeFlip();
        rootEl.dataset.theme = "dark";
        forcedDark = true;
        darkAt = t;
      } else if (!out.dark && forcedDark) {
        easeThemeFlip();
        if (prevTheme === undefined) delete rootEl.dataset.theme;
        else rootEl.dataset.theme = prevTheme;
        forcedDark = false;
      }

      drawWafers(t, out, darkAt);
      ctx.clearRect(0, 0, W, H);
      drawPanel(out);
      drawEngine(tE, out);
      drawFlare(out);
      drawGlow(t, out);
      drawEmission(t, out);

      const place = (el: HTMLElement, extra: string): void => {
        el.style.width = `${s.w}px`;
        el.style.height = `${s.h}px`;
        el.style.transform =
          `translate(${s.cx - s.w / 2}px, ${s.cy - s.h / 2}px) ${extra} ` +
          `rotateX(${s.rx}deg) rotateZ(${s.rz}deg)`;
      };
      place(block, "");
      top.style.borderRadius = `${s.r}px`;
      const blur = (out.solid ? 0 : out.frost * FROST_BLUR_MAX).toFixed(1);
      top.style.backdropFilter = `blur(${blur}px)`;
      (top.style as CSSStyleDeclaration & { webkitBackdropFilter: string }).webkitBackdropFilter = `blur(${blur}px)`;
      /* on the landing beats the plate becomes the silicon chip — its
         material lives in CSS (.gr-flow-block--chip), so the inline veil
         is cleared rather than fought */
      block.classList.toggle("gr-flow-block--chip", out.solid);
      if (out.solid) {
        top.style.background = "";
        top.style.borderColor = "";
      } else {
        const veilA = out.frost * FROST_VEIL_MAX;
        top.style.background = `rgba(${veil[0]}, ${veil[1]}, ${veil[2]}, ${veilA.toFixed(3)})`;
        top.style.borderColor = `rgba(${veil[0]}, ${veil[1]}, ${veil[2]}, ${(0.25 + out.frost * 0.35).toFixed(3)})`;
      }
      /* the chip's thickness: two side faces folded under the plate,
         edge-on (invisible) while it is frontal */
      const depth = Math.max(10, s.w * 0.045);
      faceS.style.height = `${depth}px`;
      faceE.style.width = `${depth}px`;

      /* the G lights up the moment the lights go off — outline while the
         chip is frontal, filled once it turns to the isometric view */
      mark.style.opacity = `${out.markAlpha * (out.dark ? clamp01((t - darkAt) / 0.25) : 0)}`;
      mark.classList.toggle("gr-flow-mark--filled", out.glowA > 0.999);
      block.style.setProperty("--plate-r", `${s.r}px`);

      /* the cinematic sweep: ONE pass of light across the chip while it
         is straight on, before the tilt begins */
      const st = clamp01((out.sheenT - 0.12) / 0.72);
      sheen.style.opacity = `${(out.dark && st < 1 ? Math.sin(st * Math.PI) : 0).toFixed(3)}`;
      sheen.style.transform = `translateX(${(-130 + 260 * easeIO(st)).toFixed(1)}%)`;

      place(shadowEl, `translate(${s.w * 0.06}px, ${s.h * 0.14}px)`);
      shadowEl.style.opacity = `${out.shadowAlpha * (out.dark ? 0.5 : 1)}`;

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
      /* never leave the reader in a theme they did not choose */
      if (forcedDark) {
        if (prevTheme === undefined) delete rootEl.dataset.theme;
        else rootEl.dataset.theme = prevTheme;
      }
      clearTimeout(easeTimer);
      rootEl.classList.remove("gr-theme-ease");
    };
  }, []);

  return (
    <div className="gr-flow" ref={runwayRef} style={{ height: `${RUNWAY_VH}vh` }}>
      <div className="gr-flow-stage">
        <canvas className="gr-flow-wafers" ref={glRef} />
        <canvas className="gr-flow-field" ref={canvasRef} />
        <div className="gr-flow-shadow" ref={shadowRef} />
        <div className="gr-flow-block" ref={blockRef}>
          <div className="gr-flow-top" ref={topRef}>
            <div className="gr-flow-die" />
            <div className="gr-flow-mark" ref={markRef}>
              <Logo mark />
              <div className="gr-flow-mark-bits" />
            </div>
            <div className="gr-flow-sheen" ref={sheenRef} />
          </div>
          <div className="gr-flow-face gr-flow-face--s" ref={faceSRef} />
          <div className="gr-flow-face gr-flow-face--e" ref={faceERef} />
          {/* RAW thickness: a stacked extrusion that FOLLOWS the rounded
              corners, unlike flat side faces */}
          {Array.from({ length: 10 }, (_, i) => (
            <div
              className={`gr-flow-slice${i === 9 ? " gr-flow-slice--last" : ""}`}
              key={i}
              style={{ transform: `translateZ(${(-2.2 * (i + 1)).toFixed(1)}px)` }}
            />
          ))}
        </div>
        <canvas className="gr-flow-over" ref={overRef} />

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
