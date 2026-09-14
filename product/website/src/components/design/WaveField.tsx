import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/**
 * The hero's ground: a field of wavy lines drawn in characters.
 *
 * WHY THIS IS GENERATED RATHER THAN THE SVG. The source artwork is 70 paths of
 * 65 sampled points — a photograph of one instant of a generative pattern. It
 * cannot be animated without a model of what produced it, and it is 145KB. So
 * the model is rebuilt here: horizontal lines, flat at the left edge and
 * increasingly wavy to the right, stacked evenly. Those are the artwork's own
 * measurements (amplitude ramps 9.7 -> 13.2 across 70 rows at 7.88 apart).
 *
 * IT LOOPS EXACTLY. Every term is a sine whose frequency in BOTH x and time is
 * an integer number of cycles per period, so at t=1 every point is where it
 * was at t=0. That is the whole reason for integer HARMONICS below — a
 * prettier irrational set would drift and never close.
 *
 * The characters are random per CELL, not per line and not per frame — see
 * glyphAt. Nothing is drawn cell by cell; each line is walked column by column
 * and stamped into a buffer, which is what keeps this cheap enough to run
 * every frame.
 */

/** Sines summed per line. [cycles across x, cycles per loop, weight]. */
const HARMONICS: [number, number, number][] = [
  [1, 1, 1],
  [2, -1, 0.5],
  [3, 2, 0.28],
  [5, -2, 0.16],
];

/** Character rows between one line and the next.

   NOT the artwork's line count. It has 70 lines over 569px — a ratio that
   only means anything at that size. A character grid gives roughly 56 rows in
   a hero, so asking for 70 lines put more lines than rows on the screen: every
   line rounded into its neighbour and the field drew as flat rules. What has
   to carry over is the RELATIONSHIP — lines a few rows apart, swinging far
   enough to cross — so the count is derived from the grid instead. */
const ROWS_PER_LINE = 3;

/** Swing, as a multiple of the gap between lines. The artwork's is ~1.6, which
    is what makes its lines interleave rather than run parallel. */
const AMPLITUDE_RATIO = 1.6;

/** One full cycle of the loop. */
const PERIOD_MS = 24000;

/** Frames per second. The motion is ambient; 24 is plenty and halves the work. */
const FPS = 24;

/** Ceilings, so an enormous viewport cannot make this expensive. */
const MAX_COLS = 240;
const MAX_ROWS = 110;

/** The character set the field is drawn from. */
const GLYPHS = "-=~+*/\\|<>:;.^";

/**
 * A character for a cell, stable for that cell.
 *
 * Deliberately keyed on the CELL and not on the frame. Re-rolling every frame
 * makes the whole field seethe, which reads as static rather than as a moving
 * surface; keyed this way the texture holds still and the lines travel
 * through it, picking up different characters as they go. The randomness is
 * in the field, the motion is in the lines.
 *
 * A hash rather than Math.random for the same reason: the same cell has to
 * give the same character on every frame, and on the server as in the browser.
 */
const glyphAt = (col: number, row: number): string => {
  let h = (col * 73856093) ^ (row * 19349663);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return GLYPHS[Math.abs(h ^ (h >>> 16)) % GLYPHS.length];
};

export const WaveField = (): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);
  const preRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const pre = preRef.current;
    if (!host || !pre) return;

    let cols = 0;
    let rows = 0;
    let frame = 0;
    let last = 0;
    let disposed = false;

    /* Measured from the rendered font rather than assumed: the grid has to be
       the monospace advance exactly, or the field drifts out of square as the
       viewport widens. */
    const measure = () => {
      const probe = document.createElement("span");
      probe.textContent = "0".repeat(50);
      probe.style.cssText =
        "position:absolute;visibility:hidden;white-space:pre;";
      pre.appendChild(probe);
      const charWidth = probe.getBoundingClientRect().width / 50;
      probe.remove();

      const lineHeight =
        parseFloat(getComputedStyle(pre).lineHeight) || charWidth * 1.6;
      cols = Math.min(MAX_COLS, Math.ceil(host.clientWidth / charWidth) + 1);
      rows = Math.min(MAX_ROWS, Math.ceil(host.clientHeight / lineHeight) + 1);
    };

    /* One line's vertical offset at a given column, in rows.

       `u` is position across the width, 0 to 1. The amplitude ramp is the
       artwork's defining feature: at u=0 every line is flat and they sit
       evenly, and by u=1 they are at full swing. */
    const offsetAt = (line: number, u: number, t: number, amplitude: number) => {
      let sum = 0;
      for (const [fx, ft, weight] of HARMONICS) {
        // The line index enters as a phase shift, so neighbours are offset
        // from each other and the field reads as a travelling wave rather
        // than as 70 copies of one curve.
        const phase = line * fx * 0.35;
        sum += weight * Math.sin(2 * Math.PI * (fx * u + ft * t + phase));
      }
      return sum * amplitude * u * u;
    };

    const draw = (now: number) => {
      frame = requestAnimationFrame(draw);
      if (now - last < 1000 / FPS) return;
      last = now;
      if (cols === 0 || rows === 0) return;

      const t = (now % PERIOD_MS) / PERIOD_MS;
      const buffer: string[][] = Array.from({ length: rows }, () =>
        new Array<string>(cols).fill(" "),
      );

      // Enough lines to fill the height at the chosen spacing, and a swing
      // measured against that spacing — so the field looks the same at any
      // viewport rather than flattening as the grid gets shorter.
      const lines = Math.max(2, Math.floor(rows / ROWS_PER_LINE));
      const amplitude = ROWS_PER_LINE * AMPLITUDE_RATIO;

      for (let line = 0; line < lines; line += 1) {
        const base = (line + 0.5) * ROWS_PER_LINE;
        let previous = offsetAt(line, 0, t, amplitude);
        let previousRow = Math.round(base + previous);

        for (let col = 0; col < cols; col += 1) {
          const u = col / (cols - 1);
          const offset = offsetAt(line, u, t, amplitude);
          const row = Math.round(base + offset);


          /* Fill the whole span this column covers, not just its endpoint.
             Where a line is steep it crosses several rows between one column
             and the next, and stamping only the endpoint left the curve as
             disconnected dashes — the steeper the segment, the more of it
             went missing, which is exactly where a line most needs to read as
             continuous. */
          const from = Math.min(previousRow, row);
          const to = Math.max(previousRow, row);
          for (let r = from; r <= to; r += 1) {
            if (r >= 0 && r < rows) buffer[r][col] = glyphAt(col, r);
          }

          previous = offset;
          previousRow = row;
        }
      }

      pre.textContent = buffer.map((row) => row.join("")).join("\n");
    };

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

    const start = () => {
      cancelAnimationFrame(frame);
      measure();
      if (reduced.matches) {
        // One frame, held. The field is a texture either way; it just stops
        // being motion.
        last = 0;
        draw(0);
        cancelAnimationFrame(frame);
        return;
      }
      frame = requestAnimationFrame(draw);
    };

    const observer = new ResizeObserver(() => {
      if (!disposed) start();
    });
    observer.observe(host);
    reduced.addEventListener("change", start);
    start();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      reduced.removeEventListener("change", start);
    };
  }, []);

  return (
    <div aria-hidden className="gr-wavefield" ref={hostRef}>
      <pre ref={preRef} />
    </div>
  );
};
