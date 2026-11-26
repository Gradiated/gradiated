import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/* Each bead is a point sprite shaded as a sphere and written at its true depth. */

const PAIRS = 20;
const TWIST = 0.55; /* radians per base pair */
const RISE = 0.42; /* units along the axis per base pair */
const LEAN = 0.62; /* the axis leans left, in radians */
const GROOVE =
  Math.PI * 0.82; /* the second strand's phase: major/minor groove */

type Bead = [x: number, y: number, z: number, radius: number, hue: number];

const buildHelix = (): Bead[] => {
  const beads: Bead[] = [];
  const length = (PAIRS - 1) * RISE;
  /* Pink at the top, through violet and blue, to teal at the foot. */
  const hueAt = (y: number) => 0.5 + ((y + length / 2) / length) * 0.44;
  const at = (t: number, phase: number): [number, number, number] => {
    const angle = t * TWIST + phase;
    return [Math.cos(angle), t * RISE - length / 2, Math.sin(angle)];
  };

  for (const phase of [0, GROOVE]) {
    for (let t = 0; t <= PAIRS - 1; t += 0.07) {
      const [x, y, z] = at(t, phase);
      beads.push([x, y, z, 0.11, hueAt(y)]);
    }
    for (let n = 0; n < PAIRS; n += 1) {
      const [x, y, z] = at(n, phase);
      beads.push([x, y, z, 0.17, hueAt(y)]);
    }
  }

  for (let n = 0; n < PAIRS; n += 1) {
    const a = at(n, 0);
    const b = at(n, GROOVE);
    const hue = hueAt(a[1]);
    for (let k = 1; k < 16; k += 1) {
      const f = k / 16;
      beads.push([
        a[0] + (b[0] - a[0]) * f,
        a[1] + (b[1] - a[1]) * f,
        a[2] + (b[2] - a[2]) * f,
        0.075,
        f < 0.5 ? hue + 0.05 : hue - 0.07,
      ]);
    }
  }
  return beads;
};

const VERTEX = `#version 300 es
in vec3 aPos;
in float aRadius;
in float aHue;
uniform float uSpin;
uniform float uLean;
uniform float uScale;
uniform vec2 uView;
uniform float uDpr;
out float vHue;
out float vRadius;
out float vShade;
const float FOCAL = 9.0;
void main() {
  float c = cos(uSpin), s = sin(uSpin);
  vec3 p = vec3(aPos.x * c - aPos.z * s, aPos.y, aPos.x * s + aPos.z * c);
  float cl = cos(uLean), sl = sin(uLean);
  p = vec3(p.x * cl - p.y * sl, p.x * sl + p.y * cl, p.z);
  float persp = FOCAL / (FOCAL - p.z);
  vec2 screen = p.xy * persp * uScale;
  gl_Position = vec4(screen / (uView * 0.5), 0.5 - p.z * 0.04, 1.0);
  gl_PointSize = aRadius * 2.0 * persp * uScale * uDpr + 1.0;
  vHue = aHue;
  vRadius = aRadius;
  vShade = clamp(0.64 + p.z * 0.36, 0.28, 1.0);
}`;

const FRAGMENT = `#version 300 es
precision highp float;
in float vHue;
in float vRadius;
in float vShade;
out vec4 color;
vec3 hsv(float h, float s, float v) {
  vec3 k = clamp(abs(fract(h + vec3(0.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0) - 1.0, 0.0, 1.0);
  return v * mix(vec3(1.0), k, s);
}
void main() {
  vec2 q = gl_PointCoord * 2.0 - 1.0;
  q.y = -q.y;
  float r2 = dot(q, q);
  if (r2 > 1.0) discard;
  vec3 n = vec3(q, sqrt(1.0 - r2));
  vec3 key = normalize(vec3(-0.55, 0.65, 0.75));
  vec3 fill = normalize(vec3(0.7, -0.3, 0.6));
  vec3 base = hsv(fract(vHue), 0.72, 0.95);
  float diffuse = max(dot(n, key), 0.0);
  float soft = max(dot(n, fill), 0.0) * 0.28;
  float spec = pow(max(dot(n, normalize(key + vec3(0.0, 0.0, 1.0))), 0.0), 70.0);
  float rim = pow(1.0 - n.z, 3.0);
  vec3 lit = base * (0.22 + diffuse * 0.85 + soft)
    + vec3(1.0) * spec * 0.85
    + mix(base, vec3(1.0), 0.5) * rim * 0.35;
  lit *= vShade;
  float edge = smoothstep(1.0, 0.86, r2);
  gl_FragDepth = gl_FragCoord.z - n.z * vRadius * 0.04;
  color = vec4(pow(lit, vec3(1.0 / 1.15)) * edge, edge);
}`;

export const DnaHelix = (): ReactElement => {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const gl = element?.getContext("webgl2", {
      alpha: true,
      antialias: true,
      premultipliedAlpha: true,
    });
    if (!element || !gl) return;

    const compile = (type: number, source: string) => {
      const shader = gl.createShader(type);
      if (!shader) return null;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
    };
    const vertex = compile(gl.VERTEX_SHADER, VERTEX);
    const fragment = compile(gl.FRAGMENT_SHADER, FRAGMENT);
    const program = gl.createProgram();
    if (!vertex || !fragment || !program) return;
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return;
    gl.useProgram(program);

    const beads = buildHelix();
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array(beads.flat()),
      gl.STATIC_DRAW,
    );
    const attribute = (name: string, size: number, offset: number) => {
      const location = gl.getAttribLocation(program, name);
      gl.enableVertexAttribArray(location);
      gl.vertexAttribPointer(location, size, gl.FLOAT, false, 20, offset);
    };
    attribute("aPos", 3, 0);
    attribute("aRadius", 1, 12);
    attribute("aHue", 1, 16);

    const uniform = (name: string) => gl.getUniformLocation(program, name);
    const uSpin = uniform("uSpin");
    const uLean = uniform("uLean");
    const uScale = uniform("uScale");
    const uView = uniform("uView");
    const uDpr = uniform("uDpr");

    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.clearColor(0, 0, 0, 0);

    const still = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let visible = false;
    let dpr = 1;
    let width = 0;
    let height = 0;

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = element.clientWidth;
      height = element.clientHeight;
      element.width = Math.max(1, Math.round(width * dpr));
      element.height = Math.max(1, Math.round(height * dpr));
      gl.viewport(0, 0, element.width, element.height);
    };

    const draw = (time: number) => {
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      /* Fit the leaning helix inside the box, both ways. */
      const length = (PAIRS - 1) * RISE;
      const scale = Math.min(
        height / (length * Math.cos(LEAN) + 2.6),
        width / (length * Math.sin(LEAN) + 2.6),
      );
      gl.uniform1f(uSpin, time / 2400);
      gl.uniform1f(uLean, LEAN);
      gl.uniform1f(uScale, scale);
      gl.uniform2f(uView, width, height);
      gl.uniform1f(uDpr, dpr);
      gl.drawArrays(gl.POINTS, 0, beads.length);
    };

    const loop = (time: number) => {
      draw(time);
      frame = requestAnimationFrame(loop);
    };
    const sync = () => {
      cancelAnimationFrame(frame);
      if (still.matches || !visible) draw(3000);
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
      gl.deleteBuffer(buffer);
      gl.deleteProgram(program);
    };
  }, []);

  return (
    <canvas aria-hidden="true" className="gr-lab-dna-canvas" ref={canvas} />
  );
};
