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

    /* ---- the wafer field (fragment shader) ----
       Square dies in the page's ink; the reveal is a wavefront in the
       plate's own rounded-rect geometry, and the resting field is pool-lit
       from the plate with a slow breath. */
    const glOK = (() => {
      const gl = glCanvas.getContext("webgl", { alpha: true, premultipliedAlpha: false });
      if (!gl) return null;
      const vsrc = "attribute vec2 aP; void main(){ gl_Position = vec4(aP, 0.0, 1.0); }";
      const fsrc = `
precision mediump float;
uniform vec2  uRes;
uniform vec2  uC;
uniform float uSize;
uniform float uCell;
uniform float uRing;
uniform float uPulse;
uniform vec3  uGold;
uniform float uOn;
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
  vec2 cc = (id * cell);
  float dr = sdBox(cc, vec2(uSize * 0.5), uSize * 0.02);
  float dn = dr / (uSize * 1.35);
  if (dn > 1.0) discard;
  float q = max(abs(lp.x), abs(lp.y));
  float m = 1.0 - smoothstep(0.26, 0.30, q);
  if (m <= 0.0) discard;
  float front = uRing * 1.25;
  float x = (dn - front) * 3.4;
  float band = exp(-x * x * 4.0);
  float wake = smoothstep(front, front - 0.3, dn);
  float pool = exp(-max(dn, 0.0) * 2.4) * uPulse;
  float grain = fract(sin(dot(id, vec2(12.9898, 78.233))) * 43758.5453);
  float refl = 0.9 + 0.2 * grain;
  /* gold wafer: a deep bronze shadow tone at rest, the bright kiln gold
     where the light lives */
  vec3 deep = uGold * vec3(0.62, 0.5, 0.34);
  vec3 col = mix(deep, uGold * 1.05, 0.3 + 0.55 * band + 0.15 * grain);
  float a = m * refl * (0.12 + 0.55 * band + wake * pool * 0.65) * uOn;
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
          gold: gl.getUniformLocation(prog, "uGold"),
          on: gl.getUniformLocation(prog, "uOn"),
        },
      };
    })();

    const drawWafers = (t: number, out: TimelineOut, chipAt: number): void => {
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
      const on = out.on ? clamp01((t - chipAt) / 0.3) : 0;
      if (on <= 0.001) return;
      const bit = Math.max(3.5, out.s.w * 0.013);
      gl.uniform2f(u.res, glCanvas.width, glCanvas.height);
      gl.uniform2f(u.c, out.s.cx * dpr, out.s.cy * dpr);
      gl.uniform1f(u.size, out.s.w * dpr);
      gl.uniform1f(u.cell, (bit / 0.56) * dpr);
      gl.uniform1f(u.ring, easeIO(out.holdT));
      gl.uniform1f(u.pulse, 1.0); /* no pulse - the field rests still */
      gl.uniform3f(u.gold, goldV[0], goldV[1], goldV[2]);
      gl.uniform1f(u.on, on * out.blockA);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      block.style.setProperty("--bit", `${bit.toFixed(1)}px`);
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

      drawWafers(t, out, chipAt);
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
        <canvas className="gr-flow-wafers" ref={glRef} />
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
