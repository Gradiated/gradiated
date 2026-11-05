import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { BEAM_FRAGMENT } from "./beam.frag";

/**
 * The homepage's beam: a cone of light narrowing to a point.
 *
 * Inference is many things resolving into one, so the shape gathers rather
 * than spreads, and the light runs along it toward the point — faster as the
 * channel narrows, which is what convergence looks like when it moves.
 *
 * A SHADER, AND FOR A REASON. The first attempt drew soft particles to a 2D
 * canvas and it did two things wrong: it read as blobs sliding rather than as
 * a field, and it heated the machine. Both have the same cause — the CPU was
 * compositing a full-viewport surface sixty times a second. Here the field is
 * an expression evaluated per pixel by the GPU, which is the work it exists
 * to do; the CPU's only job each frame is to set a clock uniform.
 *
 * It is also why there is no blur anywhere. The softness is in the falloffs —
 * see beam.frag.ts — so nothing has to be smeared after the fact, and a large
 * gaussian is the single most expensive thing this effect could have asked
 * for.
 *
 * THE GUARDS MATTER MORE THAN THE EFFECT. It renders at 0.6 of CSS size and
 * caps at 1.25x device pixels, because a field this soft loses nothing to
 * being upscaled; it stops entirely when scrolled out of the fold or when the
 * tab is hidden; and it holds ~40fps rather than chasing the display, since
 * nothing here moves fast enough to need more. If it still costs too much on
 * any machine, RESOLUTION is the dial.
 */

/** Share of the CSS size actually rendered. The field has no detail to lose. */
const RESOLUTION = 0.6;
/** Frames per second. The motion is slow; the display's rate is not needed. */
const FPS = 40;
/** Keep the colour field moving, but at a background rather than focal pace. */
const MOTION_RATE = 0.08;
/** How far the field comes up over the page. */
const ALPHA = 0.9;

const VERTEX = /* glsl */ `
  attribute vec2 aPosition;
  void main() {
    gl_Position = vec4(aPosition, 0.0, 1.0);
  }
`;

type Stop = [number, number, number];

const parse = (value: string): Stop | null => {
  const hex = value.trim();
  const short = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(hex);
  const full = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  const read = (parts: string[]) =>
    parts.map(
      (part) => parseInt(part.length === 1 ? part + part : part, 16) / 255,
    ) as Stop;
  if (short) return read([short[1], short[2], short[3]]);
  if (full) return read([full[1], full[2], full[3]]);
  return null;
};

const compile = (
  gl: WebGLRenderingContext,
  kind: number,
  source: string,
): WebGLShader | null => {
  const shader = gl.createShader(kind);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    /* Surfaced rather than swallowed: a shader that fails to compile leaves
       the page looking merely empty, which is indistinguishable from the
       effect being switched off. */
    console.error("beam shader:", gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
};

export const HeroBeam = (): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;

    const gl = canvas.getContext("webgl", {
      alpha: true,
      antialias: false,
      /* The field is redrawn every frame, so there is nothing worth keeping
         between them — and telling the driver so avoids a copy. */
      preserveDrawingBuffer: false,
      /* True, and the shader multiplies its own output — see beam.frag.ts.
         `false` is not honoured by iOS WebKit, which composites the buffer as
         premultiplied either way; declaring what WebKit will do anyway, and
         writing pixels to match, is the only portable contract. */
      premultipliedAlpha: true,
      powerPreference: "low-power",
    });
    if (!gl) return;

    const vertex = compile(gl, gl.VERTEX_SHADER, VERTEX);
    const fragment = compile(gl, gl.FRAGMENT_SHADER, BEAM_FRAGMENT);
    if (!vertex || !fragment) return;

    const program = gl.createProgram();
    if (!program) return;
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error("beam program:", gl.getProgramInfoLog(program));
      return;
    }
    gl.useProgram(program);

    /* Two triangles covering clip space. The shader works in fragment
       coordinates, so the geometry carries no information at all. */
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]),
      gl.STATIC_DRAW,
    );
    const position = gl.getAttribLocation(program, "aPosition");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

    /* NO BLENDING, deliberately.
     *
     * There is exactly one draw over a freshly cleared transparent buffer, so
     * there is nothing to blend against — and blending here was the bug that
     * turned the whole fold white. SRC_ALPHA/ONE_MINUS_SRC_ALPHA writes RGB
     * already multiplied by alpha, while `premultipliedAlpha: false` tells the
     * compositor the opposite, so it divided by alpha a second time and washed
     * every pixel toward white. Writing the fragment straight is both correct
     * and one less state to get wrong.
     */

    const uRes = gl.getUniformLocation(program, "uRes");
    const uTime = gl.getUniformLocation(program, "uTime");
    const uWarm = gl.getUniformLocation(program, "uWarm");
    const uHot = gl.getUniformLocation(program, "uHot");
    const uCool = gl.getUniformLocation(program, "uCool");
    const uOlive = gl.getUniformLocation(program, "uOlive");
    const uPlum = gl.getUniformLocation(program, "uPlum");
    const uAlpha = gl.getUniformLocation(program, "uAlpha");
    const uApexY = gl.getUniformLocation(program, "uApexY");

    const root = host.closest<HTMLElement>(".gr-root") ?? document.body;

    /* Existing brand gradients, not a palette of its own: shallows runs teal
       to amber, which is the beam from its point to its body, and ember's red
       is the heat at the wide end.
       
       Deliberately NOT --gradient-from/--gradient-to. Those are the theme's
       own pair, and on taupe that pair is terrace — pale stone to olive — so
       the beam came out as stone painted on stone. A beam has to be able to
       differ from the ground it lies on. */
    const readColours = () => {
      const styles = getComputedStyle(root);
      const at = (name: string, fallback: string) =>
        parse(styles.getPropertyValue(name)) ?? parse(fallback) ?? [0, 0, 0];
      /* Ember and shallows in continuous succession, with the palette's own
         olive and plum as the bridges between them: red -> amber -> olive ->
         teal -> plum -> red is a walk around the brand's wheel, where the
         three-stop version cycled primaries and read like a test card. All
         five are live tokens — retune brand.css and the beam follows. */
      /* The relaunch cycle, settled in the lab against the new system:
         yellow -> teal -> azure -> sky -> red.

         The structural properties of the original survive the recolour.
         The wrap seam is red -> yellow — the energy family's own rungs —
         so the warm passage still plays as one swell across the join.
         And sky is the leg that sits nearest the zinc ground, the breath
         between waves rather than a flicker.

         The uniform names (hot/warm/olive/cool/plum) are the five SEATS
         of the cycle, named for the palette that first sat in them — not
         for what sits there now. Rename them only with the shader. */
      gl.uniform3fv(uHot, at("--color-energy-yellow", "#f4ce56"));
      gl.uniform3fv(uWarm, at("--color-hw-teal", "#09b99e"));
      gl.uniform3fv(uOlive, at("--color-cloud-azure", "#009fd9"));
      gl.uniform3fv(uCool, at("--color-cloud-sky", "#8ed3f2"));
      gl.uniform3fv(uPlum, at("--color-energy-red", "#e4504e"));
    };

    let width = 0;
    let height = 0;
    const layout = () => {
      const box = host.getBoundingClientRect();
      if (box.width < 4 || box.height < 4) return;
      width = box.width;
      height = box.height;
      const dpr = Math.min(1.25, window.devicePixelRatio || 1);
      canvas.width = Math.max(2, Math.round(width * dpr * RESOLUTION));
      canvas.height = Math.max(2, Math.round(height * dpr * RESOLUTION));
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(uRes, canvas.width, canvas.height);
      /* The canvas runs past the fold so the colour can bleed into the next
         section, so "vertically centred" means centred on the FOLD — the
         module this sits in — not on the canvas. */
      const fold = host.parentElement?.getBoundingClientRect().height ?? height;
      gl.uniform1f(uApexY, height > 0 ? (fold * 0.5) / height : 0.5);
      /* Quieter in portrait on top of the structural fix: a phone shows the
         cone's brightest reach at arm's length and full width, so the field
         comes up less far there. 1 at square-and-wider, 0.7 at a tall phone. */
      const aspect = height > 0 ? width / height : 1;
      const trim = Math.min(1, Math.max(0.7, 0.7 + (aspect - 0.6) * 0.75));
      gl.uniform1f(uAlpha, ALPHA * trim);
    };

    const render = (seconds: number) => {
      gl.uniform1f(uTime, seconds * MOTION_RATE);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    layout();
    readColours();

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const started = performance.now();
    let frame = 0;
    let running = false;
    let last = 0;

    /* The loop owns its own lifetime; the observers only decide whether a
       frame does any WORK.
       
       Gating the loop's START on the IntersectionObserver was a bug: its first
       callback can arrive before the element has been laid out, report "not
       intersecting" for an element that is plainly on screen, and then never
       fire again because nothing subsequently changes. The result was a single
       static frame and no motion — with nothing in the console to say so.
       
       An idle rAF that returns immediately costs nothing worth measuring; a
       GPU draw is the expensive part, and that is what is actually skipped. */
    let visible = true;

    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      if (!visible || document.hidden) return;
      /* Held to FPS rather than the display's rate. */
      if (now - last < 1000 / FPS) return;
      last = now;
      render((now - started) / 1000);
    };

    const start = () => {
      if (running || reduced.matches) return;
      running = true;
      last = 0;
      frame = requestAnimationFrame(tick);
    };
    const stop = () => {
      if (!running) return;
      running = false;
      cancelAnimationFrame(frame);
    };

    /* One still frame first, so a reader who has asked for no motion gets the
       picture rather than an empty fold. */
    render(0);
    start();

    const seen = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
      },
      { threshold: 0 },
    );
    seen.observe(host);

    const resize = new ResizeObserver(() => {
      layout();
      render((performance.now() - started) / 1000);
    });
    resize.observe(host);

    const themed = new MutationObserver(() => {
      readColours();
      render((performance.now() - started) / 1000);
    });
    themed.observe(root, { attributeFilter: ["data-theme"], attributes: true });

    const onReduced = () => (reduced.matches ? stop() : start());
    reduced.addEventListener("change", onReduced);

    return () => {
      stop();
      seen.disconnect();
      resize.disconnect();
      themed.disconnect();
      reduced.removeEventListener("change", onReduced);
      /* The context is NOT released here, and that is deliberate.
       *
       * Releasing it looks like good hygiene and breaks the component in
       * development: React's StrictMode mounts an effect, tears it down and
       * mounts it again, so the cleanup ran before the real mount. Once a
       * context is lost, getContext on that canvas hands back the dead one and
       * every call after it is a silent no-op — a blank canvas with no error
       * anywhere, in dev only, while production and any headless check render
       * perfectly.
       *
       * The canvas is unmounted with this component, so the context goes with
       * it when collected; there is nothing here to leak. */
    };
  }, []);

  return (
    <div aria-hidden className="gr-beam" ref={hostRef}>
      <canvas className="gr-beam-canvas" ref={canvasRef} />
    </div>
  );
};
