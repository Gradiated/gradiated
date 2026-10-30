import { makeNetworkPoints, NETWORK_ASPECT } from "./neural-network";
import type { NetworkPoint } from "./neural-network";

type Point = { x: number; y: number };
export type Grain = {
  dune: Point;
  circuit: NetworkPoint;
  size: number;
  tone: number;
  phase: number;
  wind: boolean;
};

export const CIRCUIT_ASPECT = NETWORK_ASPECT;

const random = (seed: number) => () => {
  seed = (seed + 0x6d2b79f5) | 0;
  let value = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
  return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
};

export const crest = (x: number): number =>
  0.28 + 0.54 * Math.pow(Math.abs(x - 0.43), 1.4) + 0.035 * Math.sin(x * 9);

export const makeGrains = (): Grain[] => {
  const next = random(43);
  const circuit = makeNetworkPoints(next);
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
      circuit: point,
      size: 0.65 + next() * 0.9,
      tone: next(),
      phase: next(),
      wind: dune.wind,
    };
  });
};
