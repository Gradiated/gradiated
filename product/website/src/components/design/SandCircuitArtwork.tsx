import { useEffect, useId, useRef } from "react";
import type { ReactElement } from "react";
import "./sand-circuit.css";

type Point = { x: number; y: number };
type Grain = {
  dune: Point;
  circuit: Point;
  size: number;
  tone: number;
  phase: number;
  wind: boolean;
};

const CIRCUIT_ASPECT = 2;

const random = (seed: number) => () => {
  seed = (seed + 0x6d2b79f5) | 0;
  let value = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
  return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
};

const crest = (x: number): number =>
  0.28 + 0.54 * Math.pow(Math.abs(x - 0.43), 1.4) + 0.035 * Math.sin(x * 9);

const circuitPoints = (): Point[] => {
  const points: Point[] = [];
  const line = (from: Point, to: Point) => {
    const count = Math.ceil(Math.hypot(to.x - from.x, to.y - from.y) * 700);
    for (let i = 0; i < count; i += 1) {
      const t = i / count;
      points.push({
        x: from.x + (to.x - from.x) * t,
        y: from.y + (to.y - from.y) * t,
      });
    }
  };
  const wire = (nodes: number[][]) => {
    for (let i = 1; i < nodes.length; i += 1) {
      line(
        { x: nodes[i - 1][0], y: nodes[i - 1][1] },
        { x: nodes[i][0], y: nodes[i][1] },
      );
    }
  };
  const circle = (x: number, y: number, radius: number) => {
    for (let i = 0; i < 72; i += 1) {
      const angle = (i / 72) * Math.PI * 2;
      points.push({
        x: x + Math.cos(angle) * radius,
        y: y + Math.sin(angle) * radius * CIRCUIT_ASPECT,
      });
    }
  };
  const nand = (x: number, y: number) => {
    wire([
      [x, y - 0.105],
      [x, y + 0.105],
      [x + 0.055, y + 0.105],
    ]);
    line({ x, y: y - 0.105 }, { x: x + 0.055, y: y - 0.105 });
    for (let i = 0; i <= 140; i += 1) {
      const angle = -Math.PI / 2 + (i / 140) * Math.PI;
      points.push({
        x: x + 0.055 + Math.cos(angle) * 0.08,
        y: y + Math.sin(angle) * 0.105,
      });
    }
    circle(x + 0.15, y, 0.015);
  };

  nand(0.24, 0.31);
  nand(0.24, 0.69);
  nand(0.65, 0.5);
  wire([
    [0.08, 0.26],
    [0.24, 0.26],
  ]);
  wire([
    [0.08, 0.36],
    [0.24, 0.36],
  ]);
  wire([
    [0.08, 0.64],
    [0.24, 0.64],
  ]);
  wire([
    [0.08, 0.74],
    [0.24, 0.74],
  ]);
  wire([
    [0.405, 0.31],
    [0.52, 0.31],
    [0.52, 0.45],
    [0.65, 0.45],
  ]);
  wire([
    [0.405, 0.69],
    [0.52, 0.69],
    [0.52, 0.55],
    [0.65, 0.55],
  ]);
  wire([
    [0.815, 0.5],
    [0.92, 0.5],
  ]);
  for (const [x, y] of [
    [0.08, 0.26],
    [0.08, 0.36],
    [0.08, 0.64],
    [0.08, 0.74],
    [0.92, 0.5],
  ]) {
    circle(x, y, 0.007);
  }
  return points;
};

const makeGrains = (): Grain[] => {
  const next = random(43);
  const circuit = circuitPoints().sort((a, b) => a.x - b.x || a.y - b.y);
  const dunes: Array<Point & { wind: boolean }> = [];
  for (let i = 0; i < 10000; i += 1) {
    const x = -0.06 + next() * 1.12;
    const ridge = crest(x);
    dunes.push({
      x,
      y: ridge + Math.pow(next(), 1.05) * (1.16 - ridge),
      wind: false,
    });
  }
  for (let i = 0; i < 220; i += 1) {
    const x = 0.32 + next() * 0.38;
    dunes.push({ x, y: crest(x), wind: true });
  }
  dunes.sort((a, b) => a.x - b.x || a.y - b.y);

  return dunes.map((dune, i) => ({
    dune,
    circuit: {
      x:
        circuit[Math.floor((i / dunes.length) * circuit.length)].x +
        (next() - 0.5) * 0.004,
      y:
        circuit[Math.floor((i / dunes.length) * circuit.length)].y +
        (next() - 0.5) * 0.006,
    },
    size: 0.65 + next() * 0.9,
    tone: next(),
    phase: next(),
    wind: dune.wind,
  }));
};

export const SandCircuitArtwork = (): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pattern = useId().replace(/:/g, "");

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!host || !canvas || !context) return;

    const grains = makeGrains();
    const bodyGrains = grains.filter((grain) => !grain.wind);
    const windGrains = grains.filter((grain) => grain.wind);
    const duneCache = document.createElement("canvas");
    duneCache.width = 0;
    duneCache.height = 0;
    const duneContext = duneCache.getContext("2d");
    if (!duneContext) return;
    const trigger =
      host.closest<HTMLElement>(".gr-story-link, .gr-nav-note, .sand-cover") ??
      host;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let width = 0;
    let height = 0;
    let progress = 0;
    let target = 0;
    let clock = 0;
    let previous = 0;
    let visible = false;
    let hovered = false;
    let focused = false;

    const paint = (
      context: CanvasRenderingContext2D,
      points: Grain[],
      eased: number,
    ) => {
      const scale = Math.min(width / 960, height / 600);
      const artWidth = Math.max(width * 0.94, scale * 850);
      const artHeight = height * 0.88;
      const left = (width - artWidth) / 2;
      const top = height * 0.05;
      const circuitWidth = Math.min(
        width * 0.94,
        height * 0.88 * CIRCUIT_ASPECT,
      );
      const circuitHeight = circuitWidth / CIRCUIT_ASPECT;
      const circuitLeft = (width - circuitWidth) / 2;
      const circuitTop = (height - circuitHeight) / 2;

      for (const grain of points) {
        let { x, y } = grain.dune;
        let alpha = 0.62 + grain.tone * 0.35;
        if (grain.wind) {
          const travel = (clock * 0.09 + grain.phase) % 1;
          x += travel * 0.28;
          y -= Math.sin(travel * Math.PI * 0.72) * 0.16;
          alpha *=
            (1 - eased) * Math.pow(Math.sin(travel * Math.PI), 1.5) + eased;
        }

        x = left + x * artWidth;
        y = top + y * artHeight;
        x += (circuitLeft + grain.circuit.x * circuitWidth - x) * eased;
        y += (circuitTop + grain.circuit.y * circuitHeight - y) * eased;
        const ridgeDistance = Math.max(0, grain.dune.y - crest(grain.dune.x));
        const ripple =
          Math.sin(grain.dune.x * 64 + ridgeDistance * 28) * 0.5 + 0.5;
        const shade = grain.tone * 0.62 + ripple * 0.22 + ridgeDistance * 0.12;
        const duneColor =
          shade > 0.73
            ? [242, 221, 172]
            : shade > 0.42
              ? [155, 108, 52]
              : [106, 73, 37];
        const circuitColor = [
          91 + grain.tone * 30,
          77 + grain.tone * 25,
          55 + grain.tone * 20,
        ];
        const color = duneColor.map((value, i) =>
          Math.round(value + (circuitColor[i] - value) * eased),
        );
        context.fillStyle = `rgba(${color.join(",")},${alpha})`;
        context.beginPath();
        context.arc(
          x,
          y,
          Math.max(0.55, grain.size * Math.max(0.8, scale)),
          0,
          Math.PI * 2,
        );
        context.fill();
      }
    };
    const render = () => {
      if (!width || !height) return;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      const eased = progress * progress * (3 - 2 * progress);
      if (progress === 0) {
        if (
          duneCache.width !== canvas.width ||
          duneCache.height !== canvas.height
        ) {
          duneCache.width = canvas.width;
          duneCache.height = canvas.height;
          duneContext.setTransform(ratio, 0, 0, ratio, 0, 0);
          paint(duneContext, bodyGrains, 0);
        }
        context.drawImage(duneCache, 0, 0, width, height);
        paint(context, windGrains, 0);
      } else {
        paint(context, grains, eased);
      }
      host.dataset.morph = progress.toFixed(3);
      host.dataset.ready = "true";
    };

    const tick = (now: number) => {
      frame = 0;
      if (!visible || document.hidden) return;
      const elapsed = previous ? Math.min((now - previous) / 1000, 0.05) : 0;
      previous = now;
      clock += elapsed;
      progress += (target - progress) * (1 - Math.exp(-elapsed * 4.5));
      if (Math.abs(target - progress) < 0.001) progress = target;
      render();
      if (!reduced.matches && (progress !== target || progress < 1))
        frame = requestAnimationFrame(tick);
    };
    const schedule = () => {
      if (frame || !visible || document.hidden) return;
      previous = 0;
      frame = requestAnimationFrame(tick);
    };
    const update = () => {
      target = reduced.matches ? 0 : Number(hovered || focused);
      if (reduced.matches) progress = 0;
      render();
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
      const nextWidth = Math.round(host.clientWidth);
      const nextHeight = Math.round(host.clientHeight);
      if (
        !nextWidth ||
        !nextHeight ||
        (nextWidth === width && nextHeight === height)
      )
        return;
      width = nextWidth;
      height = nextHeight;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      render();
      schedule();
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
    <div aria-hidden className="gr-sand-artwork" ref={hostRef}>
      <svg
        className="gr-sand-poster"
        viewBox="0 0 960 600"
        preserveAspectRatio="none"
      >
        <defs>
          <pattern
            id={pattern}
            width="6"
            height="6"
            patternUnits="userSpaceOnUse"
          >
            <circle cx="2" cy="2" r="1.3" fill="#a17e4c" />
          </pattern>
        </defs>
        <path
          d="M0 310 Q240 150 410 175 Q600 170 960 350 V600 H0Z"
          fill={`url(#${pattern})`}
        />
      </svg>
      <canvas ref={canvasRef} />
    </div>
  );
};
