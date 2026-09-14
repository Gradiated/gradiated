import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { artworkBackground, type ArtworkPreset } from "../../lib/artwork";
import { WaferField } from "../../lib/wafer-field";

export type WaferArtworkOptions = ArtworkPreset & {
  chipSize?: number;
  columns?: number;
  cornerRadius?: number;
  gap?: number;
  rows?: number;
};

export const WaferArtwork = ({
  className = "",
  options,
}: {
  className?: string;
  options: WaferArtworkOptions;
}): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;

    let disposed = false;
    let field: WaferField | null = null;
    let play = () => {};
    let generation = 0;
    let animationFrame = 0;

    const draw = async () => {
      if (disposed) return;
      const currentGeneration = ++generation;
      const width = Math.max(240, host.clientWidth);
      const height = Math.max(180, host.clientHeight);
      const columns = options.columns ?? 144;
      const rows = options.rows ?? Math.max(12, Math.round(columns * (height / width)));
      const step = Math.max(2, Math.floor(Math.min(width / columns, height / rows)));
      const gap = options.gap ?? Math.max(1, Math.round(step * 0.22));
      const chipSize = options.chipSize ?? Math.max(1, step - gap);

      const nextField = new WaferField(canvas, {
        autoShimmer: false,
        bgColor: "transparent",
        chipColor: options.chip,
        chipSize,
        cornerRadius: options.cornerRadius ?? 0,
        depthAmount: 0,
        gap,
        pixelRatio: window.devicePixelRatio || 1,
        shading: "flat",
      });
      nextField.resize(columns, rows);
      await nextField.setShapeFromImage(options.source, {
        cols: columns,
        fill: true,
        fit: "cover",
        invert: options.invert,
        mode: "luminance",
        palette: options.palette,
        rows,
        threshold: options.threshold,
      });
      if (disposed || currentGeneration !== generation) {
        nextField.stop();
        return;
      }

      field?.stop();
      field = nextField;
      cancelAnimationFrame(animationFrame);
      field.scatterIn(options.scatter).setProgress(1);
      canvas.style.opacity = "1";
      let progress = 1;
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

      // Keep one scatter path. A new hover reverses from the current frame.
      const transition = (target: number, duration: number, done?: () => void) => {
        cancelAnimationFrame(animationFrame);
        const start = performance.now();
        const from = progress;
        const step = (now: number) => {
          if (!field || disposed) return;
          const elapsed = Math.min(1, (now - start) / duration);
          const eased = elapsed * elapsed * (3 - 2 * elapsed);
          progress = from + (target - from) * eased;
          field.setProgress(progress);
          canvas.style.opacity = String(progress);
          if (elapsed < 1) animationFrame = requestAnimationFrame(step);
          else done?.();
        };
        animationFrame = requestAnimationFrame(step);
      };

      play = () => {
        if (!field || reduced.matches) return;
        transition(0, Math.max(80, 280 * progress), () => transition(1, 720));
      };
    };

    void draw();
    const trigger = host.closest<HTMLElement>(".gr-story-link, .gr-nav-note") ?? host;
    const onPlay = () => play();
    trigger.addEventListener("mouseenter", onPlay);
    trigger.addEventListener("focus", onPlay);
    const observer = new ResizeObserver(() => { void draw(); });
    observer.observe(host);

    return () => {
      disposed = true;
      cancelAnimationFrame(animationFrame);
      observer.disconnect();
      trigger.removeEventListener("mouseenter", onPlay);
      trigger.removeEventListener("focus", onPlay);
      field?.stop();
    };
  }, [options]);

  return (
    <div
      className={`gr-wafer-artwork ${className}`.trim()}
      ref={hostRef}
      style={{ background: artworkBackground(options) }}
    >
      <canvas aria-hidden ref={canvasRef} />
    </div>
  );
};
