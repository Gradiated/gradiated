import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { Logo } from "./Logo";

/**
 * The chip fold (new-homepage-layout, fold 4).
 *
 * The loop fold above shows the machine; this fold shows what it lands on.
 * One scroll-scrubbed shot in the site's raw ink language: the chip arrives
 * frontal — outlined plate, die perimeter, hairline G — over a wafer field
 * whose reveal wavefront carries the plate's own geometry; then it tilts to
 * the isometric rest, the G fills with data-bits, and a stream of the hero
 * field's glyphs pours out of it while the silicon copy is read.
 *
 * Physics contract: geometry follows scroll through a critically-damped
 * chase on REAL elapsed time; micro-life (field, emission) runs on
 * wall-clock so the scene stays alive while the user reads.
 */

const BEATS = {
  intro: [0.0, 0.16],
  /* just long enough for the reveal wavefront - then straight to iso */
  hold: [0.16, 0.34],
  land: [0.34, 0.68],
  siliconRest: [0.68, 1.0],
} as const;

/** Runway height in viewport-heights; the scrub's total scroll distance. */
export const RUNWAY_VH = 420;

/** Time constant of the damped chase (seconds). The object's weight. */
const DAMPING_TAU = 0.14;

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
  blockA: number;   /* the chip's arrival */
  markAlpha: number;
  shadowAlpha: number;
  on: boolean;      /* the chip exists — timestamps the field's fade-in */
  holdT: number;    /* progress through the frontal hold — the reveal */
  glowA: number;    /* progress into the isometric view */
  siliconCopyA: number;
};

const keyStates = (
  W: number,
  H: number,
): Record<"chip" | "land", BlockState> => {
  const vm = Math.min(W, H);
  const wide = W > 720;
  return {
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
    s: K.chip,
    blockA: 0,
    markAlpha: 0,
    shadowAlpha: 0,
    on: g > 0.02,
    holdT: 0,
    glowA: 0,
    siliconCopyA: 0,
  };
  if (g < BEATS.intro[1]) {
    const t = easeO(seg(g, BEATS.intro));
    const small = { ...K.chip, w: K.chip.w * 0.88, h: K.chip.h * 0.88, cy: K.chip.cy + H * 0.04 };
    out.s = mixState(small, K.chip, t);
    out.blockA = easeO(clamp01(t * 1.5));
    out.markAlpha = clamp01((t - 0.4) / 0.6);
  } else if (g < BEATS.hold[1]) {
    out.s = K.chip;
    out.blockA = 1;
    out.markAlpha = 1;
    out.holdT = seg(g, BEATS.hold);
  } else if (g < BEATS.land[1]) {
    const t = easeIO(seg(g, BEATS.land));
    out.s = mixState(K.chip, K.land, t);
    out.blockA = 1;
    out.markAlpha = 1;
    out.shadowAlpha = easeO(clamp01((t - 0.3) / 0.7)) * 0.55;
    out.holdT = 1;
    out.glowA = easeIO(t);
  } else {
    out.s = K.land;
    out.blockA = 1;
    out.markAlpha = 1;
    out.shadowAlpha = 0.55;
    out.holdT = 1;
    out.glowA = 1;
    out.siliconCopyA = easeO(seg(g, BEATS.siliconRest) * 3);
  }
  return out;
};

export const HomeFlow = (): ReactElement => {
  const runwayRef = useRef<HTMLDivElement>(null);
  const blockRef = useRef<HTMLDivElement>(null);
  const shadowRef = useRef<HTMLDivElement>(null);
  const markRef = useRef<HTMLDivElement>(null);
  const topRef = useRef<HTMLDivElement>(null);
  const glRef = useRef<HTMLCanvasElement>(null);
  const overRef = useRef<HTMLCanvasElement>(null);
  const siliconCopyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const runway = runwayRef.current;
    const block = blockRef.current;
    const shadowEl = shadowRef.current;
    const mark = markRef.current;
    const top = topRef.current;
    const glCanvas = glRef.current;
    const overCanvas = overRef.current;
    const siliconCopy = siliconCopyRef.current;
    if (!runway || !block || !shadowEl || !mark || !top || !glCanvas || !overCanvas || !siliconCopy)
      return;
    const ctx2 = overCanvas.getContext("2d");
    if (!ctx2) return;

    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const rootEl = (block.closest(".gr-root") as HTMLElement) ?? document.documentElement;

    let ink = "#2F2D29";
    let goldV: [number, number, number] = [0.75, 0.6, 0.28];
    const readTheme = (): void => {
      const cs = getComputedStyle(rootEl);
      ink = cs.getPropertyValue("--color-text").trim() || "#2F2D29";
      /* the wafer field is GOLD — the brand's kiln amber */
      const gold = cs.getPropertyValue("--color-kiln-300").trim() || "#e9b748";
      const gm = /^#([0-9a-f]{6})$/i.exec(gold);
      if (gm)
        goldV = [
          parseInt(gm[1].slice(0, 2), 16) / 255,
          parseInt(gm[1].slice(2, 4), 16) / 255,
          parseInt(gm[1].slice(4, 6), 16) / 255,
        ];
    };
    readTheme();
    const themeWatch = new MutationObserver(readTheme);
    themeWatch.observe(rootEl, { attributes: true, attributeFilter: ["data-theme"] });
    const scheme = matchMedia("(prefers-color-scheme: dark)");
    scheme.addEventListener("change", readTheme);

    let W = 0;
    let H = 0;
    const resize = (): void => {
      W = window.innerWidth;
      H = window.innerHeight;
      const dpr = Math.min(devicePixelRatio || 1, 2);
      overCanvas.width = W * dpr;
      overCanvas.height = H * dpr;
      ctx2.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    addEventListener("resize", resize);

    /* ---- the motherboard ----
       A technical illustration of the board the chip sits on, drawn once
       per size into its own canvas. The canvas shares the plate's 3D
       transform, so the board lies flat under the frontal chip and tilts
       with it into the isometric view. Seeded, so it never redraws
       differently. */
    const bctx = glCanvas.getContext("2d");
    if (!bctx) return;
    let boardPx = 0;

    const drawBoardArt = (S: number): void => {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      glCanvas.width = S * dpr;
      glCanvas.height = S * dpr;
      bctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      bctx.clearRect(0, 0, S, S);

      let seed = 7;
      const rnd = (): number => {
        seed = (seed * 16807) % 2147483647;
        return (seed - 1) / 2147483646;
      };
      const c = S / 2;
      const u = S / 2.7; /* the plate's width at this scale */
      const gold = getComputedStyle(rootEl).getPropertyValue("--color-kiln-300").trim() || "#e9b748";

      bctx.strokeStyle = ink;
      bctx.lineWidth = 1;

      const rr = (x: number, y: number, w: number, h: number, r: number): void => {
        bctx.beginPath();
        bctx.roundRect(x, y, w, h, r);
        bctx.stroke();
      };

      /* board edge + mounting holes */
      bctx.globalAlpha = 0.32;
      rr(6, 6, S - 12, S - 12, 18);
      for (const [hx, hy] of [[26, 26], [S - 26, 26], [26, S - 26], [S - 26, S - 26]] as const) {
        bctx.globalAlpha = 0.35;
        bctx.beginPath();
        bctx.arc(hx, hy, 7, 0, Math.PI * 2);
        bctx.stroke();
        bctx.beginPath();
        bctx.arc(hx, hy, 2.4, 0, Math.PI * 2);
        bctx.stroke();
      }

      /* the socket the chip seats into, with its keepout */
      const sk = u * 0.62;
      bctx.globalAlpha = 0.4;
      rr(c - sk, c - sk, sk * 2, sk * 2, 10);
      bctx.globalAlpha = 0.18;
      bctx.setLineDash([2, 5]);
      rr(c - sk - 14, c - sk - 14, (sk + 14) * 2, (sk + 14) * 2, 14);
      bctx.setLineDash([]);

      /* trace bundles: out of each socket side, one 45-degree dogleg,
         ending on a gilt pad */
      const pad = (x: number, y: number): void => {
        bctx.save();
        bctx.globalAlpha = 0.55;
        bctx.fillStyle = gold;
        bctx.fillRect(x - 2.2, y - 2.2, 4.4, 4.4);
        bctx.restore();
      };
      const bundle = (side: number): void => {
        const n = 7 + Math.floor(rnd() * 3);
        for (let i = 0; i < n; i++) {
          const f = (i + 0.5) / n;
          const a = c + (f - 0.5) * sk * 1.7;      /* along the socket edge */
          const run1 = 22 + rnd() * (S / 2 - sk - 70);
          const dog = (rnd() < 0.5 ? -1 : 1) * (8 + rnd() * 26);
          const run2 = 12 + rnd() * (S / 2 - sk - run1 - 40);
          bctx.globalAlpha = 0.2 + rnd() * 0.08;
          bctx.beginPath();
          let x = 0;
          let y = 0;
          if (side === 0) { /* right */
            x = c + sk; y = a;
            bctx.moveTo(x, y); x += run1; bctx.lineTo(x, y);
            x += Math.abs(dog); y += dog; bctx.lineTo(x, y);
            x += run2; bctx.lineTo(x, y);
          } else if (side === 1) { /* left */
            x = c - sk; y = a;
            bctx.moveTo(x, y); x -= run1; bctx.lineTo(x, y);
            x -= Math.abs(dog); y += dog; bctx.lineTo(x, y);
            x -= run2; bctx.lineTo(x, y);
          } else if (side === 2) { /* down */
            x = a; y = c + sk;
            bctx.moveTo(x, y); y += run1; bctx.lineTo(x, y);
            y += Math.abs(dog); x += dog; bctx.lineTo(x, y);
            y += run2; bctx.lineTo(x, y);
          } else { /* up */
            x = a; y = c - sk;
            bctx.moveTo(x, y); y -= run1; bctx.lineTo(x, y);
            y -= Math.abs(dog); x += dog; bctx.lineTo(x, y);
            y -= run2; bctx.lineTo(x, y);
          }
          bctx.stroke();
          pad(x, y);
        }
      };
      bundle(0);
      bundle(1);
      bundle(2);
      bundle(3);

      /* component footprints, sparse */
      bctx.globalAlpha = 0.3;
      /* an SOIC top-right, pin stubs on both long sides */
      const sx = c + sk + 30;
      const sy = c - sk - 58;
      rr(sx, sy, 52, 24, 3);
      for (let i = 0; i < 6; i++) {
        const px = sx + 7 + i * 8;
        bctx.beginPath();
        bctx.moveTo(px, sy - 4); bctx.lineTo(px, sy);
        bctx.moveTo(px, sy + 24); bctx.lineTo(px, sy + 28);
        bctx.stroke();
      }
      /* capacitor pair, left */
      for (let i = 0; i < 2; i++) {
        bctx.beginPath();
        bctx.arc(c - sk - 52, c - 20 + i * 40, 8, 0, Math.PI * 2);
        bctx.stroke();
        bctx.beginPath();
        bctx.moveTo(c - sk - 56, c - 20 + i * 40);
        bctx.lineTo(c - sk - 48, c - 20 + i * 40);
        bctx.stroke();
      }
      /* a DIMM-ish slot along the bottom, with its notch */
      const dw = u * 1.3;
      rr(c - dw / 2, S - 54, dw, 13, 2);
      bctx.beginPath();
      bctx.moveTo(c - dw / 6, S - 54);
      bctx.lineTo(c - dw / 6, S - 41);
      bctx.stroke();
      /* passives: little resistor pairs scattered off the corners */
      for (let i = 0; i < 10; i++) {
        const qx = c + (rnd() - 0.5) * (S - 130);
        const qy = c + (rnd() - 0.5) * (S - 130);
        if (Math.abs(qx - c) < sk + 26 && Math.abs(qy - c) < sk + 26) continue;
        bctx.globalAlpha = 0.24;
        bctx.strokeRect(qx, qy, 5, 8);
        bctx.strokeRect(qx + 8, qy, 5, 8);
      }
      bctx.globalAlpha = 1;
    };

    /* the G emits — a fading stream of the hero field's glyphs, from the
       G's PROJECTED position, on the overlay above the plate */
    const drawEmission = (t: number, out: TimelineOut): void => {
      ctx2.clearRect(0, 0, W, H);
      if (out.glowA <= 0.01) return;
      const { s } = out;
      ctx2.save();
      ctx2.strokeStyle = ink;
      ctx2.fillStyle = ink;
      ctx2.lineWidth = 1;
      const N = 42;
      const len = s.h * 1.2;
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

    /* ---- the loop ---- */
    let targetP = 0;
    let g = reduced ? 1 : 0;
    let lastT = performance.now();
    let raf = 0;
    let wasOn = false;
    let chipAt = 0;

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

      if (out.on && !wasOn) {
        wasOn = true;
        chipAt = t;
      } else if (!out.on) wasOn = false;

      /* the board: shares the plate's transform, revealed by an expanding
         clip during the hold */
      const bs = Math.round(s.w * 2.7);
      if (bs > 10 && bs !== boardPx) {
        boardPx = bs;
        drawBoardArt(bs);
      }
      glCanvas.style.width = `${bs}px`;
      glCanvas.style.height = `${bs}px`;
      glCanvas.style.transform =
        `translate(${s.cx - bs / 2}px, ${s.cy - bs / 2}px) rotateX(${s.rx}deg) rotateZ(${s.rz}deg)`;
      const reveal = (1 - easeIO(out.holdT)) * 32;
      glCanvas.style.clipPath = `inset(${reveal.toFixed(2)}% round 26px)`;
      glCanvas.style.opacity = `${(out.blockA * clamp01((t - chipAt) / 0.4) * (out.on ? 1 : 0)).toFixed(3)}`;
      block.style.setProperty("--bit", `${Math.max(3.5, s.w * 0.013).toFixed(1)}px`);

      drawEmission(t, out);

      block.style.width = `${s.w}px`;
      block.style.height = `${s.h}px`;
      block.style.opacity = `${out.blockA.toFixed(3)}`;
      block.style.transform =
        `translate(${s.cx - s.w / 2}px, ${s.cy - s.h / 2}px) rotateX(${s.rx}deg) rotateZ(${s.rz}deg)`;
      block.style.setProperty("--plate-r", `${s.r}px`);
      top.style.borderRadius = `${s.r}px`;

      mark.style.opacity = `${out.markAlpha}`;
      mark.classList.toggle("gr-flow-mark--filled", out.glowA > 0.999);

      shadowEl.style.width = `${s.w}px`;
      shadowEl.style.height = `${s.h}px`;
      shadowEl.style.transform =
        `translate(${s.cx - s.w / 2 + s.w * 0.06}px, ${s.cy - s.h / 2 + s.h * 0.14}px) rotateX(${s.rx}deg) rotateZ(${s.rz}deg)`;
      shadowEl.style.opacity = `${out.shadowAlpha * 0.6}`;

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
        <canvas className="gr-flow-board" ref={glRef} />
        <div className="gr-flow-shadow" ref={shadowRef} />
        <div className="gr-flow-block gr-flow-block--raw gr-flow-block--chip" ref={blockRef}>
          <div className="gr-flow-top" ref={topRef}>
            <div className="gr-flow-die" />
            <div className="gr-flow-mark" ref={markRef}>
              <Logo mark />
              <div className="gr-flow-mark-bits" />
            </div>
          </div>
          {Array.from({ length: 10 }, (_, i) => (
            <div
              className={`gr-flow-slice${i === 9 ? " gr-flow-slice--last" : ""}`}
              key={i}
              style={{ transform: `translateZ(${(-2.2 * (i + 1)).toFixed(1)}px)` }}
            />
          ))}
        </div>
        <canvas className="gr-flow-over" ref={overRef} />

        <div className="gr-flow-copy gr-flow-copy--silicon" ref={siliconCopyRef}>
          <h2 className="gr-heading">All the way down to the silicon</h2>
          <p className="gr-muted">
            Waste in inference isn&apos;t in one place. It comes from model
            architectures that thrash memory, kernels that leave chips
            half-idle, and schedulers that keep expensive capacity waiting.
            Where possible, the workload should shape the silicon.
          </p>
          <p className="gr-muted">
            We design chips for specific model families and provide the
            weights we generate. Through hardware optimization, our goal is to
            be the most efficient, configurable, and reliable place to run
            inference for those base model families.
          </p>
        </div>
      </div>
    </div>
  );
};
