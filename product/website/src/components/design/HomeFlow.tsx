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
       The reference ATX blueprint (244x305mm), drawn to scale with the
       chip seated on U1 — the socket is the anchor, everything else is
       placed from the spec. The canvas shares the plate's 3D transform
       (rotation origin AT the socket), so the board lies flat under the
       frontal chip and tilts with it into the isometric view. */
    const bctx = glCanvas.getContext("2d");
    if (!bctx) return;
    let boardK = 0;

    const BW = 244;
    const BH = 305;
    const SOCK = { x: 75, y: 45, w: 50, h: 60, cx: 100, cy: 75 };

    const drawBoardArt = (k: number): void => {
      const dpr = 1.5;
      glCanvas.width = Math.round(BW * k * dpr);
      glCanvas.height = Math.round(BH * k * dpr);
      bctx.setTransform(k * dpr, 0, 0, k * dpr, 0, 0); /* draw in mm */
      bctx.clearRect(0, 0, BW, BH);
      const gold = getComputedStyle(rootEl).getPropertyValue("--color-kiln-300").trim() || "#e9b748";
      const hair = 1 / (k * dpr); /* one device pixel, in mm */
      bctx.strokeStyle = ink;
      bctx.fillStyle = ink;
      bctx.lineWidth = hair * 1.4;

      const R = (x: number, y: number, w: number, h: number, r = 0.8, a = 0.4): void => {
        bctx.globalAlpha = a;
        bctx.beginPath();
        bctx.roundRect(x, y, w, h, r);
        bctx.stroke();
      };
      const label = (t: string, x: number, y: number, a = 0.34): void => {
        bctx.globalAlpha = a;
        bctx.font = `${10 * hair * dpr * 1.9}px "JetBrains Mono", ui-monospace, monospace`;
        bctx.fillText(t, x, y);
      };
      /* orthogonal route with one 45-degree chamfer */
      const route = (x1: number, y1: number, x2: number, y2: number, a = 0.2): void => {
        const dx = x2 - x1;
        const dy = y2 - y1;
        bctx.globalAlpha = a;
        bctx.beginPath();
        bctx.moveTo(x1, y1);
        if (Math.abs(dx) > Math.abs(dy)) {
          const mx = x2 - Math.sign(dx) * Math.abs(dy);
          bctx.lineTo(mx, y1);
        } else {
          const my = y2 - Math.sign(dy) * Math.abs(dx);
          bctx.lineTo(x1, my);
        }
        bctx.lineTo(x2, y2);
        bctx.stroke();
      };

      /* board edge + mounting holes (ATX positions) */
      R(1, 1, BW - 2, BH - 2, 3, 0.45);
      for (const [hx, hy] of [
        [6.35, 33], [6.35, 165.1], [6.35, 287],
        [163.8, 33], [163.8, 165.1], [163.8, 287],
        [237.5, 33], [237.5, 165.1], [237.5, 287],
      ] as const) {
        bctx.globalAlpha = 0.4;
        bctx.beginPath();
        bctx.arc(hx, hy, 2, 0, Math.PI * 2);
        bctx.stroke();
        bctx.beginPath();
        bctx.arc(hx, hy, 4, 0, Math.PI * 2);
        bctx.globalAlpha = 0.18;
        bctx.stroke();
      }

      /* U1 socket + cooler keepout */
      R(SOCK.x, SOCK.y, SOCK.w, SOCK.h, 1.5, 0.5);
      bctx.setLineDash([1.5, 3]);
      R(52, 22, 96, 96, 2, 0.16);
      bctx.setLineDash([]);
      label("U1 LGA1700", SOCK.x, SOCK.y - 2);

      /* VRM banks: 8 stages each, inductors facing the socket */
      for (let i = 0; i < 8; i++) {
        R(38, 30 + i * 11.2, 14, 9.6, 0.5, 0.32);
        R(62 + i * 10, 16, 8.6, 14, 0.5, 0.32);
      }
      label("VRM", 38, 27);
      R(40, 125, 6, 6, 0.5, 0.35);
      label("U2", 47.5, 130);

      /* DDR5 DIMMs with their key notches, gilt contact strips */
      const dimmX = [160, 169, 178, 187];
      dimmX.forEach((dx, i) => {
        R(dx, 20, 7, 133, 1, 0.42);
        bctx.globalAlpha = 0.42;
        bctx.beginPath();
        bctx.moveTo(dx, 86);
        bctx.lineTo(dx + 7, 86);
        bctx.stroke();
        bctx.save();
        bctx.globalAlpha = 0.4;
        bctx.fillStyle = gold;
        bctx.fillRect(dx + 2.6, 24, 1.8, 58);
        bctx.fillRect(dx + 2.6, 90, 1.8, 58);
        bctx.restore();
        label(["A1", "A2", "B1", "B2"][i], dx + 0.6, 17.5, 0.3);
      });
      label("DDR5", 160, 160);

      /* chipset + friends */
      R(160, 195, 25, 25, 1.5, 0.45);
      R(165, 200, 15, 15, 0.8, 0.2);
      label("U3 PCH", 160, 193);
      R(195, 215, 5, 6, 0.4, 0.35);
      label("BIOS", 201.5, 220);
      R(195, 245, 14, 14, 0.8, 0.35);
      label("SIO/EC", 195, 262.5);
      R(34, 20, 7, 7, 0.5, 0.35);
      label("GbE", 42.5, 25.5);
      R(32, 130, 22, 30, 1, 0.35);
      label("WiFi", 36, 146);
      R(140, 180, 5, 5, 0.4, 0.35);
      R(147, 181, 3.2, 2.5, 0.3, 0.35);
      label("CLK", 139.5, 178);

      /* expansion: PCIe + M.2 (gilt edge contacts on the x16) */
      R(40, 162, 89, 8, 0.8, 0.45);
      bctx.save();
      bctx.globalAlpha = 0.35;
      bctx.fillStyle = gold;
      bctx.fillRect(42, 165, 60, 1.6);
      bctx.restore();
      label("PCIE1 x16 GEN5", 40, 159.5);
      R(40, 223, 89, 8, 0.8, 0.38);
      label("PCIE2 x4", 40, 220.5);
      R(40, 264, 25, 8, 0.8, 0.34);
      label("PCIE3 x1", 40, 261.5);
      bctx.setLineDash([2, 2.4]);
      R(60, 136, 80, 22, 1.2, 0.3);
      R(60, 190, 80, 22, 1.2, 0.3);
      bctx.setLineDash([]);
      label("M.2 GEN5", 62, 141.5);
      label("M.2 GEN4", 62, 195.5);
      bctx.globalAlpha = 0.35;
      bctx.beginPath();
      bctx.arc(137, 147, 1.6, 0, Math.PI * 2);
      bctx.stroke();
      bctx.beginPath();
      bctx.arc(137, 201, 1.6, 0, Math.PI * 2);
      bctx.stroke();

      /* power + storage connectors: pin fields */
      R(225, 88, 10, 52, 1, 0.42);
      for (let i = 0; i < 12; i++) {
        bctx.globalAlpha = 0.3;
        bctx.fillRect(227.2, 90.4 + i * 4.15, 1.7, 1.7);
        bctx.fillRect(231.1, 90.4 + i * 4.15, 1.7, 1.7);
      }
      label("ATX24", 224, 85.5);
      R(36, 2, 18, 10, 0.8, 0.4);
      for (let i = 0; i < 4; i++) {
        bctx.globalAlpha = 0.3;
        bctx.fillRect(38.4 + i * 4.3, 4, 1.8, 1.8);
        bctx.fillRect(38.4 + i * 4.3, 7.8, 1.8, 1.8);
      }
      R(56, 2, 9, 10, 0.8, 0.35);
      label("EPS12V", 36, 15.5);
      R(226, 190, 15, 40, 1, 0.38);
      for (let i = 0; i < 4; i++) {
        bctx.globalAlpha = 0.32;
        bctx.strokeRect(228, 192.5 + i * 9.6, 11, 6.4);
      }
      label("SATA", 226, 187.5);

      /* rear I/O along the left edge */
      R(0.5, 18, 22, 16, 1, 0.4);
      label("RJ45", 3, 26.5, 0.3);
      R(0.5, 40, 18, 60, 1, 0.4);
      for (let i = 0; i < 4; i++) R(3, 44 + i * 14, 12, 9, 0.8, 0.24);
      label("USB", 3.5, 104.5, 0.3);
      R(0.5, 105, 15, 30, 1, 0.4);
      label("HDMI/DP", 1, 140, 0.3);
      R(0.5, 140, 20, 25, 1, 0.4);
      for (let i = 0; i < 3; i++) {
        bctx.globalAlpha = 0.3;
        bctx.beginPath();
        bctx.arc(7 + (i % 2) * 7, 147 + i * 7.5, 2.6, 0, Math.PI * 2);
        bctx.stroke();
      }

      /* audio island on its split ground */
      bctx.setLineDash([1.2, 2.2]);
      R(2, 245, 40, 58, 1.5, 0.28);
      bctx.setLineDash([]);
      R(12, 262, 7, 7, 0.5, 0.35);
      label("AUDIO", 12, 258);

      /* headers + battery */
      R(150, 12, 8, 3, 0.4, 0.3);
      R(215, 150, 8, 12, 0.4, 0.3);
      R(222, 164, 20, 10, 0.8, 0.3);
      R(205, 292, 12, 6, 0.4, 0.3);
      R(8, 292, 12, 6, 0.4, 0.3);
      bctx.globalAlpha = 0.38;
      bctx.beginPath();
      bctx.arc(151, 261, 11, 0, Math.PI * 2);
      bctx.stroke();
      label("CR2032", 143, 261.8, 0.26);

      /* the buses: DDR channels, x16 lanes, DMI staircase, VCORE feeds */
      for (let i = 0; i < 6; i++) {
        route(125, 52 + i * 9, 160, 40 + i * 14, 0.16);
      }
      for (let i = 0; i < 8; i++) {
        route(80 + i * 5.6, 105, 46 + i * 10.5, 162, 0.16);
      }
      for (let i = 0; i < 3; i++) {
        route(118 + i * 3, 105, 162 + i * 6, 195, 0.14);
      }
      for (let i = 0; i < 6; i++) {
        bctx.globalAlpha = 0.24;
        bctx.beginPath();
        bctx.moveTo(52, 38 + i * 12);
        bctx.lineTo(75, 50 + i * 9);
        bctx.stroke();
      }
      route(172, 220, 84, 227, 0.13);
      route(185, 207, 226, 200, 0.13);
      route(199, 221, 185, 214, 0.14);
      route(145, 182, 129, 166, 0.13);
      route(45, 12, 45, 2 + 10, 0.16);
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

      /* the board: drawn in mm at scale k, anchored so the chip sits on
         U1, rotating about the socket, revealed as a circle from it */
      const k = Math.min((s.w * 1.12) / SOCK.w, 6.2);
      if (k > 0.5 && Math.abs(k - boardK) > 0.01) {
        boardK = k;
        drawBoardArt(k);
      }
      glCanvas.style.width = `${(BW * k).toFixed(1)}px`;
      glCanvas.style.height = `${(BH * k).toFixed(1)}px`;
      glCanvas.style.transformOrigin = `${(SOCK.cx * k).toFixed(1)}px ${(SOCK.cy * k).toFixed(1)}px`;
      glCanvas.style.transform =
        `translate(${(s.cx - SOCK.cx * k).toFixed(1)}px, ${(s.cy - SOCK.cy * k).toFixed(1)}px) rotateX(${s.rx}deg) rotateZ(${s.rz}deg)`;
      const maxR = Math.hypot(144, 230) * k;
      const rev = lerp(s.w * 0.6, maxR, easeIO(out.holdT));
      glCanvas.style.clipPath = `circle(${rev.toFixed(0)}px at ${(SOCK.cx * k).toFixed(1)}px ${(SOCK.cy * k).toFixed(1)}px)`;
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
