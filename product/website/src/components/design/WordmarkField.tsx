import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { WaferField } from "../../lib/wafer-field";

/**
 * The wordmark, built from wafer chips, with a shimmer band sweeping across it.
 *
 * The mark is static — assembled on load and left there. Chip geometry derives
 * from the lattice unit, so chipStep is exactly half a lattice cell and the
 * wordmark is made of the same dies as the rest of the page.
 *
 * Colours come from the computed role tokens rather than being hardcoded, so
 * the palette carries through with no change here, and the background stays
 * null so the module shows through.
 *
 * THE MARK IS PAINTED WITH THE GROUND'S OWN GRADIENT — shallows under the
 * grove-2 theme, morning under the Dark theme, and so on. The engine fills
 * every chip from one flat `chipColor`, and it is vendored, so the gradient is
 * composited on afterwards: render() is the single entry point every draw path
 * goes through (the shimmer's own rAF included), so wrapping it on the
 * instance recolours every frame without touching the engine.
 *
 * The composite runs in three ops, and the order is the whole trick:
 *
 *   1. snapshot the chips as drawn — this is the only copy of the shimmer's
 *      per-chip brightness, which step 2 is about to discard
 *   2. `source-in` the gradient, which repaints every covered pixel and keeps
 *      nothing but their alpha, so the mark becomes the gradient exactly
 *   3. blend the snapshot back, which reapplies that brightness
 *
 * Chips are always drawn BLACK and the sweep always lightens. What changes
 * between themes is only step 3, and it changes which half of the mark the
 * gradient lands on:
 *
 *   `screen` on a DARK ground — black is screen's identity, so an unswept chip
 *      comes through as pure gradient and the sweep lifts it. The mark is the
 *      gradient; the shimmer is a highlight.
 *
 *   `multiply` on a LIGHT ground — black is multiply's annihilator, so an
 *      unswept chip comes through as ink and only the swept ones reach the
 *      gradient. The mark is ink; the SHIMMER is the gradient.
 *
 * The light case exists because every gradient in the palette runs to a light
 * stop, and on limestone that stop is close enough to the ground that the tail
 * of the wordmark disappeared. Ink holds the shape at full contrast and the
 * gradient still gets to travel across it.
 */

/** Relative luminance of a hex or rgb() colour, 0-1. */
const luminanceOf = (colour: string): number => {
  const hex = colour.trim().match(/^#([0-9a-f]{6})$/i);
  const [r, g, b] = hex
    ? [1, 3, 5].map((i) => parseInt(hex[1].slice(i - 1, i + 1), 16))
    : (colour.match(/\d+/g) ?? ["0", "0", "0"]).slice(0, 3).map(Number);
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
};

/** Chip geometry as fractions of the lattice unit. */
const CHIP_SIZE_U = 1 / 3;
const CHIP_GAP_U = 1 / 6;

/**
 * How many chips the mark is drawn across, at every width.
 *
 * This is the resolution of the image, not a size — the wordmark's thin
 * strokes need about this many columns before they resolve into letters.
 * Deriving the chip from the lattice unit alone was the bug: --u barely
 * changes between a desktop and a phone (24px to 23px), so the chip stayed
 * 8px with a 4px gap while the canvas went from 1152px wide to 387px. The mark
 * dropped from 96 columns to 32 and stopped being legible at all.
 *
 * 96 is what the desktop already had, so widening the mark is not a change
 * there — a phone now gets the same picture in smaller pixels.
 */
const CHIP_COLS = 96;

/** Chip size and gap for a given width, keeping the 2:1 size-to-gap ratio.
 *
 *  `unitStep` is a CEILING rather than the answer: the chip should never be
 *  chunkier than the lattice it is aligned to, however wide the page gets. */
const chipGeometry = (width: number, unitStep: number) => {
  const step = Math.min(unitStep, Math.max(3, Math.floor(width / CHIP_COLS)));
  const chipSize = Math.max(2, Math.round((step * 2) / 3));
  return { chipSize, gap: Math.max(1, step - chipSize) };
};

/**
 * The shimmer sweep.
 *
 * `intensity` is signed, and the sign is the whole reason this reads on every
 * theme: the engine lerps a chip toward white for positive values and toward
 * black for negative ones. A positive sweep is invisible on Grove and Dark,
 * where the chips are already near-white and have nowhere lighter to go — so
 * the direction is chosen from the chip colour's own luminance rather than
 * fixed. Both magnitudes sit at the engine's clamps (+0.85 / -0.6), the widest
 * swing available in either direction.
 *
 * `speed` is sweeps per second: roughly one pass every six seconds, slow enough
 * to follow across the mark. `width` is the band as a fraction of the sweep's
 * travel — narrow keeps its edge defined, and the engine's squared falloff
 * tightens the peak further.
 */
const SHIMMER = { angle: -45, speed: 0.16, width: 0.16 };
/* Always lightens: the chips are black before the gradient is composited over
   them, so the sweep has the engine's full positive range to climb. */
const SHIMMER_INTENSITY = 0.85;

/** Width-to-height ratio of public/brand/wordmark.svg's viewBox. */
const WORDMARK_ASPECT = 913.69 / 159.75;

export const WordmarkField = (): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;

    const root = host.closest<HTMLElement>(".gr-root") ?? document.body;
    const styles = getComputedStyle(root);
    const unit = parseFloat(styles.getPropertyValue("--u")) || 24;
    /* The lattice-derived chip, which is now the coarsest the mark may be
       rather than the size it always is — see chipGeometry. */
    const unitStep =
      Math.max(2, Math.round(unit * CHIP_SIZE_U)) +
      Math.max(1, Math.round(unit * CHIP_GAP_U));
    const initial = chipGeometry(host.clientWidth || 1152, unitStep);
    const chipSize = initial.chipSize;
    const gap = initial.gap;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

    /* The ground's gradient, read as its two stops. These are tokens in their
       own right — the background in --gradient-theme is composed FROM them —
       so nothing here has to parse a gradient string. Falls back to the ink,
       so a missing token leaves a legible mark rather than none. */
    const stopsNow = () => {
      const styles = getComputedStyle(root);
      const from = styles.getPropertyValue("--gradient-from").trim();
      const to = styles.getPropertyValue("--gradient-to").trim();
      if (from && to) return [from, to];
      const ink = styles.getPropertyValue("--color-text").trim() || "#1b1b19";
      return [ink, ink];
    };

    let stops = stopsNow();

    /* Which half of the mark the gradient lands on — see the note at the top.
       Read from the GROUND rather than the ink, because it is the ground the
       mark has to stay legible against. */
    let blend: GlobalCompositeOperation = "screen";
    const blendNow = () => {
      const ground = getComputedStyle(root)
        .getPropertyValue("--color-substrate")
        .trim();
      blend = luminanceOf(ground) > 0.5 ? "multiply" : "screen";
    };
    blendNow();

    // Off-screen twin, sized with the canvas, holding the snapshot from step 1.
    const sweep = document.createElement("canvas");
    const sweepCtx = sweep.getContext("2d");
    const ctx = canvas.getContext("2d");

    const tint = () => {
      if (!ctx || !sweepCtx) return;
      const { height, width } = canvas;
      if (width === 0 || height === 0) return;

      if (sweep.width !== width || sweep.height !== height) {
        sweep.width = width;
        sweep.height = height;
      }
      sweepCtx.setTransform(1, 0, 0, 1, 0, 0);
      sweepCtx.clearRect(0, 0, width, height);
      sweepCtx.drawImage(canvas, 0, 0);

      // Device pixels: render() leaves the transform scaled by pixelRatio.
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      const ramp = ctx.createLinearGradient(0, 0, width, 0);
      stops.forEach((stop, i) => {
        ramp.addColorStop(i / Math.max(1, stops.length - 1), stop);
      });
      ctx.globalCompositeOperation = "source-in";
      ctx.fillStyle = ramp;
      ctx.fillRect(0, 0, width, height);
      ctx.globalCompositeOperation = blend;
      ctx.drawImage(sweep, 0, 0);
      ctx.restore();
    };

    const field = new WaferField(canvas, {
      bgColor: null,
      // Black: screen's identity, so an unswept chip is pure gradient.
      chipColor: "#000000",
      chipSize,
      /* Square, even though the system's containers are rounded: a chip is a
         die, not a box. The radius scale governs UI surfaces; this is
         artwork. */
      cornerRadius: 0,
      gap,
      shading: "flat",
    });

    // Every draw path in the engine ends here, so this is the one seam the
    // composite needs. Bound before reassignment, or it recurses.
    const paint = field.render.bind(field);
    field.render = () => {
      paint();
      tint();
      return field;
    };

    let visible = false;
    let shimmering = false;
    let disposed = false;
    let geometryKey = "";

    const startShimmer = () => {
      if (shimmering || reduced.matches) return;
      shimmering = true;
      field.startShimmer({ ...SHIMMER, intensity: SHIMMER_INTENSITY });
    };

    const stopShimmer = () => {
      if (!shimmering) return;
      shimmering = false;
      field.stopShimmer();
    };

    const layout = async () => {
      const width = host.clientWidth;
      if (width === 0) return;

      /* Re-derived per layout, because it depends on the width: a narrower
         host gets smaller chips rather than fewer of them. chipSize and gap
         are plain properties on the engine and chipStep reads from them, so
         assigning here is all resize() needs to pick them up. */
      const geometry = chipGeometry(width, unitStep);
      field.chipSize = geometry.chipSize;
      field.gap = geometry.gap;
      const step = geometry.chipSize + geometry.gap;

      const cols = Math.max(8, Math.floor(width / step));
      const rows = Math.max(
        4,
        Math.round((cols * step) / WORDMARK_ASPECT / step),
      );

      // The resize observer fires for changes that do not affect the grid;
      // rebuilding then would restart the sweep for nothing. The step is part
      // of the key: the same column count at a different chip size is a
      // different picture.
      const key = `${cols}:${rows}:${step}`;
      if (key === geometryKey) return;
      geometryKey = key;

      stopShimmer();
      // The engine owns canvas sizing: resize() sets it to cols * chipStep - gap
      // (no trailing gap after the last chip). Setting it here as well would
      // fight that and leave the mark a gap-width off its own grid.
      field.setPixelRatio(window.devicePixelRatio || 1);
      field.resize(cols, rows);
      await field.setShapeFromImage("/brand/wordmark.svg", {
        cols,
        mode: "alpha",
        rows,
      });
      if (disposed) return;

      // Straight to the assembled state: there is no entrance to play.
      field.setProgress(1);
      if (visible) startShimmer();
    };

    // The sweep runs its own rAF, so it stops whenever the mark is off screen
    // rather than burning a frame budget for the whole session.
    const observer = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
        if (visible) startShimmer();
        else stopShimmer();
      },
      { rootMargin: "200px" },
    );
    observer.observe(host);

    const resizeObserver = new ResizeObserver(() => {
      void layout();
    });
    resizeObserver.observe(host);

    // The gradient is a canvas fill, not a CSS property, so it does not follow
    // a ground change on its own — the mark would keep the previous theme's
    // colours. data-theme as well as data-theme, because either can decide
    // the page's ground.
    const groundObserver = new MutationObserver(() => {
      stops = stopsNow();
      blendNow();
      field.render();
    });
    groundObserver.observe(root, {
      attributeFilter: ["data-theme", "data-theme"],
      attributes: true,
    });

    const onReducedChange = () => {
      if (reduced.matches) stopShimmer();
      else if (visible) startShimmer();
    };
    reduced.addEventListener("change", onReducedChange);

    void layout();

    return () => {
      disposed = true;
      stopShimmer();
      observer.disconnect();
      resizeObserver.disconnect();
      groundObserver.disconnect();
      reduced.removeEventListener("change", onReducedChange);
      field.stop();
    };
  }, []);

  return (
    <div
      aria-label="gradiated"
      className="gr-wordmark-field"
      ref={hostRef}
      role="img"
    >
      <canvas aria-hidden ref={canvasRef} />
    </div>
  );
};
