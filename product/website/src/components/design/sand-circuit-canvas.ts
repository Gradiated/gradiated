import { networkFrame, networkPosition } from "./neural-network";
import { CIRCUIT_ASPECT, crest, makeGrains } from "./sand-circuit-particles";
import type { Grain } from "./sand-circuit-particles";

export const createSandCanvas = (canvas: HTMLCanvasElement) => {
  const context = canvas.getContext("2d");
  const duneCache = document.createElement("canvas");
  duneCache.width = 0;
  duneCache.height = 0;
  const duneContext = duneCache.getContext("2d");
  if (!context || !duneContext) return;

  const grains = makeGrains();
  const bodyGrains = grains.filter((grain) => !grain.wind);
  const windGrains = grains.filter((grain) => grain.wind);
  let width = 0;
  let height = 0;

  const paint = (
    context: CanvasRenderingContext2D,
    points: Grain[],
    eased: number,
    clock: number,
    networkClock = 0,
  ) => {
    const scale = Math.min(width / 960, height / 600);
    const artWidth = Math.max(width * 0.94, scale * 850);
    const artHeight = height * 0.88;
    const left = (width - artWidth) / 2;
    const top = height * 0.05;
    const circuitWidth = Math.min(width * 0.94, height * 0.88 * CIRCUIT_ASPECT);
    const circuitHeight = circuitWidth / CIRCUIT_ASPECT;
    const circuitLeft = (width - circuitWidth) / 2;
    const circuitTop = (height - circuitHeight) / 2;

    const network = eased > 0 ? networkFrame(networkClock) : undefined;

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
      const point = network
        ? networkPosition(grain.circuit, network)
        : grain.circuit;
      const targetX = point.x;
      const targetY = point.y;
      x += (circuitLeft + targetX * circuitWidth - x) * eased;
      y += (circuitTop + targetY * circuitHeight - y) * eased;
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
        70 + grain.tone * 30,
        59 + grain.tone * 25,
        42 + grain.tone * 20,
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
  const render = (
    progress: number,
    clock: number,
    networkClock = 0,
  ): boolean => {
    if (!width || !height) return false;

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
        paint(duneContext, bodyGrains, 0, clock);
      }
      context.drawImage(duneCache, 0, 0, width, height);
      paint(context, windGrains, 0, clock);
    } else {
      paint(context, grains, eased, clock, networkClock);
    }

    return true;
  };

  const resize = (nextWidth: number, nextHeight: number): boolean => {
    if (
      !nextWidth ||
      !nextHeight ||
      (nextWidth === width && nextHeight === height)
    )
      return false;

    width = nextWidth;
    height = nextHeight;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    return true;
  };

  return { render, resize };
};
