import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { makeChipGrains } from "./chip-grains";

export const ChipLayersArtwork = (): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    const trigger = host?.closest<HTMLAnchorElement>("a");
    if (!host || !canvas || !context || !trigger) return;

    const grains = makeChipGrains();
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let width = 0;
    let height = 0;
    let progress = 0;
    let target = 0;
    let hovered = false;
    let focused = false;
    let visible = false;
    let frame = 0;
    let previous = 0;

    const draw = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      const scale = Math.min(width / 640, height / 400);
      const left = (width - 640 * scale) / 2;
      const top = (height - 400 * scale) / 2;
      const ease = progress * progress * (3 - 2 * progress);
      for (const grain of grains) {
        const x = grain.sand.x + (grain.chip.x - grain.sand.x) * ease;
        const y = grain.sand.y + (grain.chip.y - grain.sand.y) * ease;
        const light =
          grain.surface === 2
            ? ease * 0.78
            : grain.surface === 1
              ? ease * 0.2
              : 0;
        const r = Math.round(35 + grain.shade * 13 + light * 175);
        const g = Math.round(19 + grain.shade * 8 + light * 147);
        const b = Math.round(24 + grain.shade * 8 + light * 107);
        context.fillStyle = `rgba(${r},${g},${b},${0.55 + grain.shade * 0.4})`;
        context.beginPath();
        context.arc(
          left + x * scale,
          top + y * scale,
          Math.max(0.45, grain.size * scale),
          0,
          Math.PI * 2,
        );
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
      progress += (target - progress) * (1 - Math.exp(-elapsed * 4));
      if (Math.abs(target - progress) < 0.001) progress = target;
      draw();
      if (progress !== target) frame = requestAnimationFrame(tick);
    };
    const schedule = () => {
      if (frame || !visible || document.hidden || progress === target) return;

      previous = 0;
      frame = requestAnimationFrame(tick);
    };
    const update = () => {
      target = Number(hovered || focused);
      if (reduced.matches) progress = target;
      draw();
      schedule();
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
    reduced.addEventListener("change", update);
    document.addEventListener("visibilitychange", schedule);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      intersection.disconnect();
      trigger.removeEventListener("mouseenter", enter);
      trigger.removeEventListener("mouseleave", leave);
      trigger.removeEventListener("focus", focus);
      trigger.removeEventListener("blur", blur);
      reduced.removeEventListener("change", update);
      document.removeEventListener("visibilitychange", schedule);
    };
  }, []);

  return (
    <div aria-hidden="true" className="sand-library-chip" ref={hostRef}>
      <svg
        className="sand-library-chip-poster"
        viewBox="0 0 640 400"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        {[0, 1, 2, 3].map((layer) => (
          <path
            key={layer}
            d="M70 250 320 154 570 250 465 290 360 250 215 306Z"
            transform={`translate(0 ${-layer * 25})`}
          />
        ))}
        <path d="M70 250V280L320 376 570 280V250M320 346V376" />
      </svg>
      <canvas ref={canvasRef} />
    </div>
  );
};
