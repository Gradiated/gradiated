type Point = { x: number; y: number };
export type Grain = {
  dune: Point;
  circuit: Point;
  size: number;
  tone: number;
  phase: number;
  wind: boolean;
};

export const CIRCUIT_ASPECT = 2;

const random = (seed: number) => () => {
  seed = (seed + 0x6d2b79f5) | 0;
  let value = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
  return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
};

export const crest = (x: number): number =>
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

export const makeGrains = (): Grain[] => {
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

  return dunes.map((dune, i) => {
    const point = circuit[Math.floor((i / dunes.length) * circuit.length)];

    return {
      dune,
      circuit: {
        x: point.x + (next() - 0.5) * 0.004,
        y: point.y + (next() - 0.5) * 0.006,
      },
      size: 0.65 + next() * 0.9,
      tone: next(),
      phase: next(),
      wind: dune.wind,
    };
  });
};
