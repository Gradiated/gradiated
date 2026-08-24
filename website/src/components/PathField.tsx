import { useEffect, useRef } from 'react';
import type { ReactElement } from 'react';

type Point = { x: number; y: number };
type TrailMode = 'open' | 'action' | 'code';
type PointerState = Point & { mode: TrailMode };
type Trail = { points: Point[]; born: number; duration: number; depth: number; source: Point };

export const PathField = (): ReactElement => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;

    const context = canvas.getContext('2d');
    if (!context) return undefined;

    const trails: Trail[] = [];
    let pointer: PointerState | null = null;
    let lastPathOrigin: PointerState | null = null;
    let lastSpawn = 0;
    let shouldSpawn = false;
    let frame = 0;
    let pageHeight = 0;
    const spawnEvery = 60;

    const resize = (): void => {
      const scale = Math.min(window.devicePixelRatio || 1, 2);
      pageHeight = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, window.innerHeight);
      canvas.width = window.innerWidth * scale;
      canvas.height = pageHeight * scale;
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${pageHeight}px`;
      context.setTransform(scale, 0, 0, scale, 0, 0);
    };

    const grow = (x: number, y: number, initialAngle: number, depth: number, length: number, seed: number): void => {
      const points: Point[] = [{ x, y }];
      const steps = 6 + Math.floor(seed * 3);
      let angle = initialAngle;
      for (let index = 1; index <= steps; index += 1) {
        const progress = index / steps;
        if (index % 2 === 0) {
          angle += (Math.random() - 0.5) * 0.72;
          angle = Math.round(angle / (Math.PI / 2)) * (Math.PI / 2);
        }
        const step = (length / steps) * (0.72 + progress * 0.46);
        const previous = points[index - 1];
        points.push({ x: previous.x + Math.cos(angle) * step, y: previous.y + Math.sin(angle) * step });
      }
      trails.push({ points, born: performance.now(), duration: 2150 + depth * 150, depth, source: { x, y } });
      if (depth > 0) {
        const fork = points[Math.max(3, Math.floor(steps * (0.48 + seed * 0.22)))];
        const branchAngle = Math.round((angle + (seed > 0.5 ? Math.PI / 2 : -Math.PI / 2)) / (Math.PI / 2)) * (Math.PI / 2);
        grow(fork.x, fork.y, branchAngle, depth - 1, length * 0.57, Math.random());
      }
    };

    const spawn = (): void => {
      if (!pointer) return;
      const direction = Math.random() > 0.5 ? 0 : Math.PI;
      const exploratory = pointer.mode === 'open';
      const angle = exploratory ? direction + (Math.random() - 0.5) * 0.7 : direction;
      const depth = pointer.mode === 'action' ? 0 : pointer.mode === 'code' ? 1 : 2;
      const length = pointer.mode === 'action' ? 72 : pointer.mode === 'code' ? 92 : 96 + Math.random() * 68;
      grow(pointer.x, pointer.y, angle, depth, length, Math.random());
      lastSpawn = performance.now();
      lastPathOrigin = { ...pointer };
      shouldSpawn = false;
    };

    const draw = (now: number): void => {
      context.clearRect(0, 0, window.innerWidth, pageHeight);
      for (let index = trails.length - 1; index >= 0; index -= 1) {
        const trail = trails[index];
        const age = now - trail.born;
        if (age > trail.duration) {
          trails.splice(index, 1);
          continue;
        }
        const reveal = Math.min(1, age / 480);
        const fade = 1 - Math.pow(age / trail.duration, 1.7);
        const visible = Math.max(2, Math.floor(trail.points.length * reveal));
        context.beginPath();
        trail.points.slice(0, visible).forEach((point, pointIndex) => {
          if (pointIndex === 0) context.moveTo(point.x, point.y);
          else context.lineTo(point.x, point.y);
        });
        const end = trail.points[visible - 1];
        const distance = Math.hypot(end.x - trail.source.x, end.y - trail.source.y);
        const alpha = Math.max(0, fade * (0.34 - distance / 1250));
        const darkMode = document.documentElement.dataset.theme === 'dark';
        const traceAlpha = darkMode ? Math.min(1, alpha * 2.7) : alpha;
        context.strokeStyle = darkMode ? `rgba(240, 236, 226, ${traceAlpha})` : `rgba(28, 27, 24, ${traceAlpha})`;
        context.lineWidth = Math.max(0.55, 1.22 - trail.depth * 0.16);
        context.stroke();
        context.strokeStyle = darkMode ? `rgba(192, 154, 104, ${Math.min(1, traceAlpha * 1.3)})` : `rgba(154, 116, 73, ${alpha * 1.25})`;
        context.lineWidth = 0.8;
        trail.points.slice(0, visible).forEach((point, pointIndex) => {
          if (pointIndex % 2 !== 0) return;
          const size = pointIndex === 0 || pointIndex === visible - 1 ? 3.6 : 2.2;
          context.strokeRect(point.x - size / 2, point.y - size / 2, size, size);
        });
      }
      if (pointer && shouldSpawn && now - lastSpawn > spawnEvery) spawn();
      frame = window.requestAnimationFrame(draw);
    };

    const onPointerMove = (event: PointerEvent): void => {
      const target = event.target instanceof Element ? event.target : null;
      const mode: TrailMode = target?.closest('a, button, input') ? 'action' : target?.closest('pre, code') ? 'code' : 'open';
      pointer = { x: event.clientX, y: event.clientY + window.scrollY, mode };
      if (!lastPathOrigin || Math.hypot(pointer.x - lastPathOrigin.x, pointer.y - lastPathOrigin.y) > 1) shouldSpawn = true;
    };
    const onVisibilityChange = (): void => {
      if (document.hidden) window.cancelAnimationFrame(frame);
      else frame = window.requestAnimationFrame(draw);
    };

    window.addEventListener('pointermove', onPointerMove, { passive: true });
    window.addEventListener('resize', resize, { passive: true });
    document.addEventListener('visibilitychange', onVisibilityChange);
    resize();
    frame = window.requestAnimationFrame(draw);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

  return <canvas ref={canvasRef} className="path-field pointer-events-none absolute inset-0 z-0 mix-blend-multiply opacity-[.38]" aria-hidden="true" />;
};
