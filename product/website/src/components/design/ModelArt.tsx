import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/**
 * Programmatic artwork for a model card: a slow fluid wash in the
 * provider's colours, the mark floating on it.
 *
 * The material is domain-warped noise — one fbm field bending the
 * coordinates another is read through — now evaluated in a fragment
 * shader so the currents DRIFT in real time. The motion is wall-clock
 * micro-life at a glacial pace: apparent if you watch, never waving at
 * you. The wash is kept deliberately quiet — colours pulled toward a
 * pale base, lightness breathing shallow — so the card reads as
 * material, not spectacle.
 *
 * The slug seeds structure (flow direction, warp, scale, ramp order), so
 * cards differ in character and are stable across renders.
 *
 * Guards, in the HeroBeam tradition: small buffer, 24fps, paused
 * offscreen, and prefers-reduced-motion gets a single still frame.
 */

const PALETTES: Record<string, string[]> = {
  "deepseek-v4-1-flash": ["#4D6BFE", "#8FA5FF", "#DCE4FF", "#2B3FA8"],
  "glm-5-3-flash": ["#5E5CE6", "#9D8CFF", "#E4DEFF", "#3634A3"],
  "kev-9b": ["#E9B748", "#BE5E31", "#F6E7C8", "#5E6043"],
};

const FALLBACK = ["#C8C1B4", "#EFECE3", "#A9A192", "#6B6557"];

const FPS = 24;
/** Buffer scale: the wash has no detail to lose. */
const RESOLUTION = 0.5;
/** How far toward the pale base every colour is pulled. The calm dial. */
const SOFTEN = 0.38;
/** Field time rate: glacial on purpose. */
const RATE = 0.03;

const VERT = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAG = `
precision mediump float;
uniform vec2 uSize;
uniform float uTime;
uniform vec2 uOffset;
uniform float uScale;
uniform float uWarp;
uniform vec2 uDir;
uniform vec3 uRamp0;
uniform vec3 uRamp1;
uniform vec3 uRamp2;
uniform vec3 uRamp3;
uniform vec3 uBase;

float hash2(vec2 p) {
  return fract(sin(p.x * 127.1 + p.y * 311.7) * 43758.5453);
}
float vnoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  float a = hash2(i);
  float b = hash2(i + vec2(1.0, 0.0));
  float c = hash2(i + vec2(0.0, 1.0));
  float d = hash2(i + vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}
float fbm(vec2 p) {
  return 0.55 * vnoise(p) + 0.3 * vnoise(p * 2.1) + 0.15 * vnoise(p * 4.3);
}
vec3 ramp(float f) {
  f = clamp(f, 0.0, 0.999) * 3.0;
  if (f < 1.0) return mix(uRamp0, uRamp1, f);
  if (f < 2.0) return mix(uRamp1, uRamp2, f - 1.0);
  return mix(uRamp2, uRamp3, f - 2.0);
}
void main() {
  vec2 p = gl_FragCoord.xy / uSize;
  vec2 q = vec2(p.x * uDir.x - p.y * uDir.y, p.x * uDir.y + p.y * uDir.x);
  vec2 s = q * uScale + uOffset;
  float t = uTime;
  /* the warp drifts: the currents re-route themselves over time */
  float wx = fbm(s + vec2(1.7 + t, 9.2));
  float wy = fbm(s + vec2(8.3, 2.8 + t * 0.8));
  float f = fbm(s + uWarp * vec2(wx, wy) + vec2(t * 0.35, -t * 0.22));
  /* compressed toward the middle: a quieter spread of the ramp */
  float idx = clamp((f - 0.28) * 1.15 + 0.25, 0.0, 1.0);
  vec3 col = ramp(idx);
  /* shallow breathing light, and the pull toward the pale base */
  float light = 0.96 + 0.07 * fbm(s * 3.0 + vec2(4.4, 6.1 + t * 0.5));
  col = mix(col * light, uBase, ${SOFTEN});
  gl_FragColor = vec4(col, 1.0);
}
`;

const hashSeed = (s: string): number => {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) % 2147483646 || 11;
};

const hex = (c: string): [number, number, number] => [
  parseInt(c.slice(1, 3), 16) / 255,
  parseInt(c.slice(3, 5), 16) / 255,
  parseInt(c.slice(5, 7), 16) / 255,
];

export const ModelArt = ({
  icon,
  name,
  slug,
}: {
  icon?: string;
  name: string;
  slug: string;
}): ReactElement => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { antialias: false });
    if (!gl) return;

    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

    let seed = hashSeed(slug);
    const rnd = (): number => {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };
    const ramp = (PALETTES[slug] ?? FALLBACK).map(hex);
    for (let i = ramp.length - 1; i > 0; i--) {
      const j = Math.floor(rnd() * (i + 1));
      [ramp[i], ramp[j]] = [ramp[j], ramp[i]];
    }
    /* the pale base: the lightest stop, pulled further toward white */
    const lightest = [...ramp].sort(
      (a, b) => b[0] + b[1] + b[2] - (a[0] + a[1] + a[2]),
    )[0];
    const base = lightest.map((v) => v + (1 - v) * 0.55) as [
      number,
      number,
      number,
    ];

    const compile = (type: number, src: string): WebGLShader | null => {
      const sh = gl.createShader(type);
      if (!sh) return null;
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        console.warn("ModelArt shader:", gl.getShaderInfoLog(sh));
        return null;
      }
      return sh;
    };
    const vs = compile(gl.VERTEX_SHADER, VERT);
    const fs = compile(gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return;
    const prog = gl.createProgram();
    if (!prog) return;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    gl.useProgram(prog);

    const quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]),
      gl.STATIC_DRAW,
    );
    const aPos = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    const U = (n: string) => gl.getUniformLocation(prog, n);
    gl.uniform2f(U("uOffset"), rnd() * 40, rnd() * 40);
    gl.uniform1f(U("uScale"), 1.0 + rnd() * 1.1);
    gl.uniform1f(U("uWarp"), 1.0 + rnd() * 1.4);
    const ang = rnd() * Math.PI;
    gl.uniform2f(U("uDir"), Math.cos(ang), Math.sin(ang));
    gl.uniform3f(U("uRamp0"), ...(ramp[0] as [number, number, number]));
    gl.uniform3f(U("uRamp1"), ...(ramp[1] as [number, number, number]));
    gl.uniform3f(U("uRamp2"), ...(ramp[2] as [number, number, number]));
    gl.uniform3f(U("uRamp3"), ...(ramp[3] as [number, number, number]));
    gl.uniform3f(U("uBase"), ...base);
    const uTime = U("uTime");
    const uSize = U("uSize");

    const phase = rnd() * 100; /* cards drift out of step with each other */

    let W = 0;
    let H = 0;
    const resize = new ResizeObserver(() => {
      const box = canvas.getBoundingClientRect();
      const dpr = Math.min(devicePixelRatio || 1, 1.5) * RESOLUTION;
      W = Math.max(2, Math.round(box.width * dpr));
      H = Math.max(2, Math.round(box.height * dpr));
      canvas.width = W;
      canvas.height = H;
      gl.viewport(0, 0, W, H);
      gl.uniform2f(uSize, W, H);
    });
    resize.observe(canvas);

    let running = true;
    const seen = new IntersectionObserver(([e]) => {
      running = e.isIntersecting;
    });
    seen.observe(canvas);

    let raf = 0;
    let last = 0;
    const frame = (now: number): void => {
      raf = requestAnimationFrame(frame);
      if (!running || W < 2) return;
      if (now - last < 1000 / FPS) return;
      last = now;
      gl.uniform1f(uTime, phase + (now / 1000) * RATE);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    if (reduced) {
      /* one still frame, once sized */
      requestAnimationFrame(() => {
        gl.uniform1f(uTime, phase);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
      });
    } else {
      raf = requestAnimationFrame(frame);
    }

    return () => {
      cancelAnimationFrame(raf);
      resize.disconnect();
      seen.disconnect();
    };
  }, [slug]);

  return (
    <span aria-hidden className="gr-models-card-art">
      <canvas className="gr-model-art-field" ref={canvasRef} />
      {icon ? (
        <img alt="" className="gr-model-art-mark" src={icon} />
      ) : (
        <span className="gr-model-art-mark gr-model-art-mark--letter">
          {name.charAt(0).toUpperCase()}
        </span>
      )}
      <span className="gr-visually-hidden">{name}</span>
    </span>
  );
};
