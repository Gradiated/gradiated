import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { makeChipGrains } from "./chip-grains";
import {
  fpgaBlocks,
  fpgaConnections,
  fpgaRoutes,
  fpgaTracks,
  makeFpgaGrains,
  projectFpga,
} from "./fpga-grains";

const fpgaColours = [
  [58, 63, 68],
  [195, 200, 205],
  [32, 37, 42],
  [196, 155, 60],
  [24, 28, 32],
];

export const ChipLayersArtwork = ({
  variant = "chip",
  playOnMount = false,
  morphSpeed = 4,
}: {
  variant?: "chip" | "fpga";
  playOnMount?: boolean;
  morphSpeed?: number;
}): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    const trigger = host?.closest<HTMLElement>("a, [data-grain-trigger]");
    if (!host || !canvas || !context || !trigger) return;

    const grains = variant === "fpga" ? makeFpgaGrains() : makeChipGrains();
    const bounds = grains.reduce(
      (box, { chip }) => ({
        left: Math.min(box.left, chip.x),
        right: Math.max(box.right, chip.x),
        top: Math.min(box.top, chip.y),
        bottom: Math.max(box.bottom, chip.y),
      }),
      { left: Infinity, right: -Infinity, top: Infinity, bottom: -Infinity },
    );
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let width = 0;
    let height = 0;
    let hovered = trigger.matches(":hover");
    let focused = trigger === document.activeElement;
    let target = Number(playOnMount || hovered || focused);
    let progress = reduced.matches ? target : 0;
    let visible = false;
    let frame = 0;
    let previous = 0;

    const draw = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      const scale = Math.min(width / 640, height / 400);
      const left = (width - (bounds.left + bounds.right) * scale) / 2;
      const top = (height - (bounds.top + bounds.bottom) * scale) / 2;
      const ease = progress * progress * (3 - 2 * progress);
      for (const grain of grains) {
        const sandX = (grain.sand.x / 640) * width;
        const sandY = (grain.sand.y / 400) * height;
        const x = sandX + (left + grain.chip.x * scale - sandX) * ease;
        const y = sandY + (top + grain.chip.y * scale - sandY) * ease;
        const light =
          grain.surface === 2
            ? ease * 0.78
            : grain.surface === 1
              ? ease * 0.2
              : 0;
        let r = 35 + grain.shade * 13 + light * 175;
        let g = 19 + grain.shade * 8 + light * 147;
        let b = 24 + grain.shade * 8 + light * 107;
        if (variant === "fpga") {
          const [red, green, blue] = fpgaColours[grain.surface];
          r = 31 + grain.shade * 16 + (red - 31) * ease;
          g = 36 + grain.shade * 17 + (green - 36) * ease;
          b = 42 + grain.shade * 19 + (blue - 42) * ease;
        }
        context.fillStyle = `rgba(${Math.round(r)},${Math.round(g)},${Math.round(b)},${0.55 + grain.shade * 0.4})`;
        context.beginPath();
        context.arc(x, y, Math.max(0.45, grain.size * scale), 0, Math.PI * 2);
        context.fill();
      }
      host.dataset.morph = progress.toFixed(3);
      host.dataset.ready = "true";
    };
    const tick = (now: number) => {
      frame = 0;
      if (!visible || document.hidden) return;

      const elapsed = previous ? Math.min((now - previous) / 1000, 0.05) : 0;
      previous = now;
      progress += (target - progress) * (1 - Math.exp(-elapsed * morphSpeed));
      if (Math.abs(target - progress) < 0.001) progress = target;
      draw();
      if (progress !== target) frame = requestAnimationFrame(tick);
    };
    const schedule = () => {
      if (frame || !visible || document.hidden || progress === target) return;

      previous = 0;
      frame = requestAnimationFrame(tick);
    };
    const applyTarget = () => {
      if (reduced.matches) progress = target;
      draw();
      schedule();
    };
    const update = () => {
      target = Number(hovered || focused);
      applyTarget();
    };
    const enter = () => {
      hovered = true;
      update();
    };
    const leave = () => {
      hovered = false;
      update();
    };
    const focus = () => {
      focused = true;
      update();
    };
    const blur = () => {
      focused = false;
      update();
    };
    const resize = () => {
      width = host.clientWidth;
      height = host.clientHeight;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      draw();
    };
    const observer = new ResizeObserver(resize);
    const intersection = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible) schedule();
      else {
        cancelAnimationFrame(frame);
        frame = 0;
      }
    });
    resize();
    observer.observe(host);
    intersection.observe(host);
    trigger.addEventListener("mouseenter", enter);
    trigger.addEventListener("mouseleave", leave);
    trigger.addEventListener("focus", focus);
    trigger.addEventListener("blur", blur);
    reduced.addEventListener("change", applyTarget);
    document.addEventListener("visibilitychange", schedule);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      intersection.disconnect();
      trigger.removeEventListener("mouseenter", enter);
      trigger.removeEventListener("mouseleave", leave);
      trigger.removeEventListener("focus", focus);
      trigger.removeEventListener("blur", blur);
      reduced.removeEventListener("change", applyTarget);
      document.removeEventListener("visibilitychange", schedule);
    };
  }, [morphSpeed, playOnMount, variant]);

  return (
    <div
      aria-hidden="true"
      className={`sand-library-chip${variant === "fpga" ? " sand-library-chip--fpga" : ""}`}
      ref={hostRef}
    >
      <svg
        className="sand-library-chip-poster"
        viewBox="0 0 640 400"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        {variant === "fpga" ? (
          <>
            {[...fpgaTracks, ...fpgaConnections, ...fpgaRoutes].map(
              (route, index) => (
                <polyline
                  key={`route-${index}`}
                  points={route
                    .map(([u, v]) => {
                      const point = projectFpga(u, v);
                      return `${point.x},${point.y}`;
                    })
                    .join(" ")}
                />
              ),
            )}
            {fpgaBlocks.map(({ u, v }, index) => (
              <polygon
                key={index}
                points={[
                  [-0.5, -0.5, 0.25],
                  [0.5, -0.5, 0.25],
                  [0.5, -0.5, 0],
                  [0.5, 0.5, 0],
                  [-0.5, 0.5, 0],
                  [-0.5, 0.5, 0.25],
                ]
                  .map(([du, dv, z]) => {
                    const point = projectFpga(u + du, v + dv, z);
                    return `${point.x},${point.y}`;
                  })
                  .join(" ")}
                fill="#bfc5c9"
              />
            ))}
          </>
        ) : (
          <g transform="translate(0 -27.5)">
            {[0, 1, 2, 3].map((layer) => (
              <path
                key={layer}
                d="M70 250 320 154 570 250 465 290 360 250 215 306Z"
                transform={`translate(0 ${-layer * 25})`}
              />
            ))}
            <path d="M70 250V280L320 376 570 280V250M320 346V376" />
          </g>
        )}
      </svg>
      <canvas ref={canvasRef} />
    </div>
  );
};
