import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { Link } from "react-router-dom";
import { Arrow } from "./icons";
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
  /* the complete diagram is there from the first frame; a slight
     ken-burns settle on scroll, then straight to isometric */
  settle: [0.0, 0.26],
  land: [0.26, 0.64],
  siliconRest: [0.64, 1.0],
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
  zoom: number;     /* the ken-burns settle */
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
    chip: { cx: W / 2, cy: H * 0.5, w: vm * 0.34, h: vm * 0.34, r: 10, rx: 0, rz: 0 },
    land: { cx: W * (wide ? 0.25 : 0.5), cy: H * (wide ? 0.52 : 0.38), w: vm * 0.32, h: vm * 0.32, r: 10, rx: 58, rz: 45 },
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
    zoom: 1,
    glowA: 0,
    siliconCopyA: 0,
  };
  out.blockA = 1;
  out.markAlpha = 1;
  /* reverse ken-burns: one slow push-in across the whole fold — the camera
     drifts toward the socket for as long as the board is on stage, through
     the landing and the rest, instead of backing off and stopping */
  out.zoom = 1 + 0.07 * g;
  if (g < BEATS.settle[1]) {
    /* frontal arrival: nothing beyond the push-in */
  } else if (g < BEATS.land[1]) {
    const t = easeIO(seg(g, BEATS.land));
    out.s = mixState(K.chip, K.land, t);
    out.blockA = 1;
    out.markAlpha = 1;
    out.shadowAlpha = easeO(clamp01((t - 0.3) / 0.7)) * 0.55;
    out.glowA = easeIO(t);
  } else {
    out.s = K.land;
    out.blockA = 1;
    out.markAlpha = 1;
    out.shadowAlpha = 0.55;
    out.glowA = 1;
    /* a slower ramp than the old *3 pop — the copy rises, sharpens and
     settles over the first half of the rest beat (see --enter in the CSS) */
  out.siliconCopyA = easeO(Math.min(1, seg(g, BEATS.siliconRest) * 1.8));
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
       Drawn to the reference blueprint: a 244x305mm ATX placement diagram
       in pure ink — bracketed mono labels, pin fields, combed connectors,
       hatched slot contacts, dashed keepouts, dimension chrome — with the
       chip seated on U1. The canvas shares the plate's 3D transform
       (rotation origin AT the socket). No traces, no colour: a drawing. */
    const bctx = glCanvas.getContext("2d");
    if (!bctx) return;
    let boardK = 0;
    let boardBuilt = -1;

    const BW = 244;
    const BH = 305;
    const BM = 18; /* margin for the dimension chrome */
    const SOCK = { x: 64, y: 40, w: 60, h: 60, cx: 94, cy: 70 };

    /* STROKE DISCIPLINE: every line is exactly one device pixel, in ONE
       shared paint — the loop fold's hairline (ink @ 30%). Solid ink is
       reserved for data (pin dots, text sits between). Coincident lines
       are drawn once. */
    const A_LINE = 0.3;
    const A_TEXT = 0.45;
    const TOTAL = 110; /* sum of the gate weights below */

    const drawBoardArt = (k: number, T: number): void => {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      const pw = Math.round((BW + 2 * BM) * k * dpr);
      if (glCanvas.width !== pw) {
        glCanvas.width = pw;
        glCanvas.height = Math.round((BH + 2 * BM) * k * dpr);
      }
      bctx.setTransform(k * dpr, 0, 0, k * dpr, BM * k * dpr, BM * k * dpr);
      bctx.clearRect(-BM, -BM, BW + 2 * BM, BH + 2 * BM);
      bctx.strokeStyle = ink;
      bctx.fillStyle = ink;
      bctx.lineWidth = 1 / (k * dpr); /* exactly one device pixel */
      const F = 3.4;

      /* the plotter's budget: elements appear in draw order */
      const budget = T * TOTAL;
      let used = 0;
      const gate = (w: number): boolean => {
        used += w;
        return used <= budget + 1e-4;
      };

      const rect = (x: number, y: number, w: number, h: number, r = 0.6): void => {
        bctx.globalAlpha = A_LINE;
        bctx.beginPath();
        bctx.roundRect(x, y, w, h, r);
        bctx.stroke();
      };
      const text = (t: string, x: number, y: number, size = F): void => {
        bctx.globalAlpha = A_TEXT;
        bctx.font = `${size}px "JetBrains Mono", ui-monospace, monospace`;
        bctx.fillText(t, x, y);
      };
      const dot = (x: number, y: number, s2 = 1.1): void => {
        bctx.fillRect(x - s2 / 2, y - s2 / 2, s2, s2);
      };
      const dotRow = (x: number, y: number, n: number, dx: number): void => {
        bctx.globalAlpha = A_LINE;
        for (let i = 0; i < n; i++) dot(x + i * dx, y);
      };
      const block4 = (x: number, y: number, w = 12, h = 12): void => {
        rect(x, y, w, h, 0.6);
        bctx.globalAlpha = A_LINE;
        dot(x + w * 0.3, y + h * 0.3);
        dot(x + w * 0.7, y + h * 0.3);
        dot(x + w * 0.3, y + h * 0.7);
        dot(x + w * 0.7, y + h * 0.7);
      };
      const slot = (x: number, y: number, w: number, h: number, notch: number): void => {
        rect(x, y, w, h, 0.8);
        const ix = x + 2;
        const iw = w - 4;
        const iy = y + h / 2 - 1.6;
        rect(ix, iy, iw, 3.2, 0.4);
        bctx.globalAlpha = A_LINE;
        const nx = x + w * notch;
        for (let hx = ix + 1.2; hx < ix + iw - 0.8; hx += 1.55) {
          if (Math.abs(hx - nx) < 1.6) continue;
          bctx.beginPath();
          bctx.moveTo(hx, iy + 0.5);
          bctx.lineTo(hx, iy + 2.7);
          bctx.stroke();
        }
        bctx.beginPath();
        bctx.moveTo(nx, y);
        bctx.lineTo(nx, y + h);
        bctx.stroke();
      };
      const mount = (x: number, y: number): void => {
        bctx.globalAlpha = A_LINE;
        bctx.beginPath();
        bctx.arc(x, y, 2, 0, Math.PI * 2);
        bctx.stroke();
        bctx.beginPath();
        bctx.arc(x, y, 4.4, 0, Math.PI * 2);
        bctx.stroke();
      };

      /* 1. board outline (8) */
      if (gate(8)) {
        bctx.globalAlpha = A_LINE;
        bctx.beginPath();
        bctx.moveTo(6, 2);
        bctx.lineTo(220, 2);
        bctx.lineTo(224, 6);
        bctx.lineTo(224, 26);
        bctx.lineTo(238, 26);
        bctx.lineTo(242, 30);
        bctx.lineTo(242, 299);
        bctx.arcTo(242, 303, 238, 303, 4);
        bctx.lineTo(6, 303);
        bctx.arcTo(2, 303, 2, 299, 4);
        bctx.lineTo(2, 6);
        bctx.arcTo(2, 2, 6, 2, 4);
        bctx.closePath();
        bctx.stroke();
      }
      /* 2. mounting holes (4) */
      if (gate(4)) {
        mount(11, 11);
        mount(233, 37);
        mount(11, 294);
        mount(233, 294);
      }
      /* 3. dimension chrome (2) */
      if (gate(2)) {
        bctx.setLineDash([2.2, 2.6]);
        bctx.globalAlpha = A_LINE;
        bctx.beginPath();
        bctx.moveTo(0, -BM + 4); bctx.lineTo(0, BH + BM - 4);
        bctx.moveTo(BW, -BM + 4); bctx.lineTo(BW, BH + BM - 4);
        bctx.moveTo(-BM + 4, 0); bctx.lineTo(BW + BM - 4, 0);
        bctx.moveTo(-BM + 4, BH); bctx.lineTo(BW + BM - 4, BH);
        bctx.stroke();
        bctx.setLineDash([]);
        bctx.beginPath();
        bctx.moveTo(2, -9); bctx.lineTo(BW - 2, -9);
        bctx.moveTo(2, -9); bctx.lineTo(5.4, -10.6);
        bctx.moveTo(2, -9); bctx.lineTo(5.4, -7.4);
        bctx.moveTo(BW - 2, -9); bctx.lineTo(BW - 5.4, -10.6);
        bctx.moveTo(BW - 2, -9); bctx.lineTo(BW - 5.4, -7.4);
        bctx.stroke();
        text("x=0", 0, -12.5);
        text("x=244mm", BW - 26, -12.5);
        text("y=0", BW + 5, 1);
        text("y=305mm", BW + 5, BH + 1);
      }
      /* 4. the socket the chip is already seated on (8) */
      if (gate(8)) {
        bctx.setLineDash([2, 2.6]);
        rect(SOCK.x - 7, SOCK.y - 7, SOCK.w + 14, SOCK.h + 14, 1);
        bctx.setLineDash([]);
        const sx = SOCK.x;
        const sy = SOCK.y;
        const sw = SOCK.w;
        const ch = 7;
        bctx.globalAlpha = A_LINE;
        bctx.beginPath();
        bctx.moveTo(sx + ch, sy);
        bctx.lineTo(sx + sw - ch, sy);
        bctx.lineTo(sx + sw, sy + ch);
        bctx.lineTo(sx + sw, sy + sw - ch);
        bctx.lineTo(sx + sw - ch, sy + sw);
        bctx.lineTo(sx + ch, sy + sw);
        bctx.lineTo(sx, sy + sw - ch);
        bctx.lineTo(sx, sy + ch);
        bctx.closePath();
        bctx.stroke();
        for (const [mx2, my2] of [
          [sx + 6, sy + 6], [sx + sw - 6, sy + 6],
          [sx + 6, sy + sw - 6], [sx + sw - 6, sy + sw - 6],
        ] as const) {
          bctx.beginPath();
          bctx.arc(mx2, my2, 1.8, 0, Math.PI * 2);
          bctx.stroke();
        }
      }
      /* 5. VRM column (8) */
      if (gate(8)) {
        text("|V|", 39, 60);
        block4(38, 62);
        text("|M|", 39, 84);
        block4(38, 86);
        text("|A|", 39, 106);
        block4(38, 108);
        block4(38, 128);
      }
      /* 6. EPS power (6) */
      if (gate(6)) {
        text("[EPS1][EPS2]", 21, 10);
        rect(20, 12, 46, 10, 1);
        rect(22, 14, 42, 6, 0.6);
        dotRow(25, 17, 13, 3.1);
        rect(36, 26, 13, 12, 0.8);
        bctx.globalAlpha = A_LINE;
        for (let i = 0; i < 3; i++) {
          dot(39 + i * 3.6, 29.5);
          dot(39 + i * 3.6, 34);
        }
      }
      /* 7. VRM_B comb (5) */
      if (gate(5)) {
        text("VRM_B", 90, 17.5);
        rect(62, 20, 72, 8.6, 1);
        rect(64, 22, 68, 4.6, 0.5);
        bctx.globalAlpha = A_LINE;
        for (let i = 0; i < 27; i++) {
          bctx.beginPath();
          bctx.moveTo(65.5 + i * 2.5, 22.6);
          bctx.lineTo(65.5 + i * 2.5, 26);
          bctx.stroke();
        }
      }
      /* 8. FAN_CPU (3) */
      if (gate(3)) {
        text("[FAN_CPU]", 148, 10);
        rect(138, 12, 48, 11, 1);
        for (let i = 0; i < 4; i++) rect(143 + i * 11, 15, 5, 5, 0.4);
      }
      /* 9. DIMMs (12) */
      if (gate(12)) {
        const dimmX = [144, 156, 168, 180];
        ["A1", "A2", "B1", "B2"].forEach((t2, i) => text(t2, dimmX[i] + 0.6, 24));
        dimmX.forEach((dx) => {
          rect(dx, 26, 7, 100, 1);
          rect(dx + 1.8, 29, 3.4, 44, 0.4);
          rect(dx + 1.8, 79, 3.4, 44, 0.4);
          bctx.globalAlpha = A_LINE;
          bctx.beginPath();
          bctx.moveTo(dx, 76);
          bctx.lineTo(dx + 7, 76);
          bctx.stroke();
        });
        text("DDR5 DIMMs", 148, 133);
      }
      /* 10. the ATX24 stack (8) */
      if (gate(8)) {
        text("+ - +", 196, 41, 2.8);
        block4(196, 44, 13, 13);
        text("[24]", 212, 53);
        text("|pn|", 197, 64);
        block4(196, 66, 13, 13);
        text("|AT|", 197, 86);
        block4(196, 88, 13, 13);
        text("|X|", 198, 108);
        block4(196, 110, 13, 13);
        text("+ - +", 196, 128, 2.8);
      }
      /* 11. rear I/O (14) */
      if (gate(14)) {
        text("[RJ45]", 5, 36);
        rect(4, 38, 14, 15, 1);
        rect(6.5, 41, 9, 9.5, 0.5);
        bctx.globalAlpha = A_LINE;
        for (let i = 0; i < 6; i++) {
          bctx.beginPath();
          bctx.moveTo(7.5 + i * 1.4, 41);
          bctx.lineTo(7.5 + i * 1.4, 44);
          bctx.stroke();
        }
        text("[USB]", 5, 60);
        rect(4, 62, 12, 18, 2);
        rect(7, 66, 6, 10, 1);
        text("[rear]", 5, 87);
        rect(4, 89, 11, 14, 2);
        rect(6.8, 92, 5.4, 8, 2.4);
        text("[HDMI]", 5, 110);
        bctx.globalAlpha = A_LINE;
        bctx.beginPath();
        bctx.moveTo(4, 112); bctx.lineTo(20, 112); bctx.lineTo(20, 121);
        bctx.lineTo(17, 124); bctx.lineTo(7, 124); bctx.lineTo(4, 121);
        bctx.closePath();
        bctx.stroke();
        rect(6.5, 114.5, 11, 6, 2.6);
        text("|DP|", 5, 131);
        bctx.globalAlpha = A_LINE;
        bctx.beginPath();
        bctx.moveTo(4, 133); bctx.lineTo(18, 133); bctx.lineTo(20, 135.5);
        bctx.lineTo(20, 143); bctx.lineTo(4, 143);
        bctx.closePath();
        bctx.stroke();
        rect(6.5, 135.5, 11, 5, 2.2);
        text("[AUD]", 5, 155);
        rect(4, 157, 13, 14, 1.4);
        bctx.globalAlpha = A_LINE;
        bctx.beginPath();
        bctx.arc(10.5, 164, 3.1, 0, Math.PI * 2);
        bctx.stroke();
      }
      /* 12. PWM + WiFi (4) */
      if (gate(4)) {
        text("[U2 PWM]", 36, 144.5);
        rect(36, 146.5, 27, 7, 0.8);
        dotRow(39, 150, 8, 3);
        text("|WiFi|", 36, 160.5);
        rect(36, 162.5, 21, 8, 0.8);
        dotRow(39, 166.5, 5, 3.4);
      }
      /* 13. FANS / USB_F (3) */
      if (gate(3)) {
        text("[FANS]", 188, 136);
        rect(186, 138, 27, 8, 0.8);
        dotRow(189, 141, 8, 3);
        dotRow(189, 143.6, 8, 3);
        text("[USB_F]", 188, 151);
        rect(188, 153, 19, 6.4, 0.8);
        dotRow(190.5, 156.2, 5, 3.2);
      }
      /* 14. PCIE1 + clock (6) */
      if (gate(6)) {
        text("[", 60, 143);
        text("PCIE1  PCIe 5.0 x16", 88, 143);
        text("]", 168, 143);
        slot(60, 146, 112, 10, 0.72);
        text("[U9 CLK][Y1]", 128, 162.5);
        rect(130, 164, 24, 6.4, 0.8);
        dotRow(132.8, 167.2, 7, 2.8);
      }
      /* 15. M2 + PCIE2 (6) */
      if (gate(6)) {
        text("[", 40, 173.5);
        text("M2_2 Gen4   (PCH)", 62, 173.5);
        text("]", 128, 173.5);
        slot(40, 176, 90, 9, 0.8);
        text("[=====", 40, 191.5);
        text("PCIE2  PCIe 4.0 x4", 62, 191.5);
        text("=====]", 116, 191.5);
        slot(40, 194, 90, 9, 0.8);
      }
      /* 16. PCIE3 (2) */
      if (gate(2)) {
        text("[= PCIE3 x1 =]", 48, 213.5);
        slot(48, 216, 28, 7, 0.7);
      }
      /* 17. PCH cluster (6) */
      if (gate(6)) {
        rect(146, 176, 16, 16, 1);
        dotRow(149, 180, 4, 3.2);
        dotRow(149, 184, 4, 3.2);
        dotRow(149, 188, 4, 3.2);
        text("|U3 |", 146, 197);
        text("|PCH|", 146, 201.5);
        text("+ - +", 146, 173.5, 2.8);
        text("[BIOS]", 170, 173.5);
        rect(168, 176, 22, 8, 0.8);
        dotRow(171, 180, 6, 3.1);
        text("+ - +", 204, 173.5, 2.8);
        block4(202, 176, 13, 13);
        text("|SA|", 217, 183);
        text("|TA|", 217, 188);
        text("[SuperIO/EC]", 168, 205.5);
        rect(198, 207, 20, 7, 0.8);
        dotRow(200.6, 210.5, 5, 3.2);
      }
      /* 18. battery, audio island, bottom headers (5) */
      if (gate(5)) {
        bctx.globalAlpha = A_LINE;
        bctx.beginPath();
        bctx.arc(134, 220, 9.5, 0, Math.PI * 2);
        bctx.stroke();
        text("( BT1 )", 124, 221.5);
        bctx.setLineDash([2, 2.4]);
        rect(13, 203, 27, 28, 0.8);
        bctx.setLineDash([]);
        text("U8", 17, 211);
        text("AUDIO", 17, 216.5);
        text("island", 17, 222);
        text("[HDA]", 16, 238);
        rect(15, 240, 30, 8, 0.8);
        dotRow(18, 244, 9, 3);
        text("[FP]", 180, 238);
        rect(176, 240, 30, 8, 0.8);
        dotRow(179, 243, 9, 3);
        dotRow(179, 245.6, 9, 3);
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

      /* the board: drawn in mm at scale k, anchored so the chip sits on
         U1, rotating about the socket, revealed as a circle from it */
      const k = Math.min((s.w * 1.0) / SOCK.w, 6.2);
      if (k > 0.5 && Math.abs(k - boardK) > 0.01) {
        boardK = k;
        drawBoardArt(k, 1);
      }
      const ocx = (BM + SOCK.cx) * k;
      const ocy = (BM + SOCK.cy) * k;
      glCanvas.style.width = `${((BW + 2 * BM) * k).toFixed(1)}px`;
      glCanvas.style.height = `${((BH + 2 * BM) * k).toFixed(1)}px`;
      glCanvas.style.transformOrigin = `${ocx.toFixed(1)}px ${ocy.toFixed(1)}px`;
      glCanvas.style.transform =
        `translate(${(s.cx - ocx).toFixed(1)}px, ${(s.cy - ocy).toFixed(1)}px) rotateX(${s.rx}deg) rotateZ(${s.rz}deg) scale(${out.zoom.toFixed(4)})`;
      glCanvas.style.opacity = "1";
      block.style.setProperty("--bit", `${Math.max(3.5, s.w * 0.013).toFixed(1)}px`);

      drawEmission(t, out);

      block.style.width = `${s.w}px`;
      block.style.height = `${s.h}px`;
      block.style.opacity = `${out.blockA.toFixed(3)}`;
      block.style.transform =
        `translate(${s.cx - s.w / 2}px, ${s.cy - s.h / 2}px) rotateX(${s.rx}deg) rotateZ(${s.rz}deg) scale(${out.zoom.toFixed(4)})`;
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
      /* the CSS turns this into rise + blur, so the entrance is one value */
      siliconCopy.style.setProperty("--enter", out.siliconCopyA.toFixed(3));

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
          <Link className="gr-button gr-button--main gr-flow-cta" to="/careers/">
            Build with us
            <Arrow />
          </Link>
        </div>
      </div>
    </div>
  );
};
