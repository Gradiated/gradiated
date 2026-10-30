import { expect, it } from "vitest";
import {
  networkConnections,
  networkFrame,
  networkLayers,
  makeNetworkPoints,
  networkPosition,
  NETWORK_CYCLE_SECONDS,
} from "../src/components/design/neural-network";

it("connects only neighbouring layers and keeps connection ends within their node dots", () => {
  for (const connection of networkConnections) {
    for (const [point, layer] of [
      [connection.from, connection.layer],
      [connection.to, connection.layer + 1],
    ] as const) {
      const distance = Math.min(
        ...networkLayers[layer].map((node) =>
          Math.hypot(point.x - node.x, (point.y - node.y) / 2),
        ),
      );
      expect(distance).toBeCloseTo(0.015);
    }
  }
});

it("redistributes grains far enough to make the changing connections visible at card size", () => {
  let seed = 17;
  const points = makeNetworkPoints(() => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;

    return seed / 4294967296;
  }).filter((point) => point.kind === "connection");
  const travelling = points.filter((point) => {
    const from = point.states[3];
    const to = point.states[0];

    return Math.hypot(to.x - from.x, (to.y - from.y) / 2) * 500 > 8;
  });

  expect(travelling.length / points.length).toBeGreaterThan(0.3);
  for (let pattern = 0; pattern < 4; pattern += 1) {
    const counts = networkConnections.map(
      (_, edge) =>
        points.filter((point) => point.states[pattern].edge === edge).length,
    );

    expect(Math.min(...counts)).toBeGreaterThan(0);
    expect(Math.max(...counts) / Math.min(...counts)).toBeGreaterThan(3);
    expect(counts.reduce((sum, count) => sum + count, 0)).toBe(points.length);
  }
});

it("moves one layer at a time and holds later layers until the sweep reaches them", () => {
  const middle = networkFrame(1.35);

  expect(middle.layers[0].progress).toBe(1);
  expect(middle.layers[1].progress).toBeGreaterThan(0);
  expect(middle.layers[2].progress).toBe(0);
  expect(middle.layers[3].progress).toBe(0);
  for (let time = 0; time < NETWORK_CYCLE_SECONDS; time += 0.05) {
    const moving = networkFrame(time).layers.filter(
      (layer) => layer.progress > 0 && layer.progress < 1,
    );
    expect(moving.length).toBeLessThanOrEqual(1);
  }
});

it("starts each sweep from the completed positions without a reset jump", () => {
  const end = networkFrame(NETWORK_CYCLE_SECONDS - 0.000001);
  const restart = networkFrame(NETWORK_CYCLE_SECONDS);

  expect(end.layers.every((layer) => layer.progress === 1)).toBe(true);
  expect(restart.layers.every((layer) => layer.progress === 0)).toBe(true);
  expect(restart.previousPattern).toBe(end.currentPattern);
  expect(restart.currentPattern).not.toBe(end.currentPattern);
});

it("moves grains directly between arrangements with the same smooth morph as the initial formation", () => {
  let seed = 12;
  const points = makeNetworkPoints(() => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;

    return seed / 4294967296;
  });
  const start = networkFrame(0);
  const middle = networkFrame(0.525);
  const end = networkFrame(0.9);
  let varied = 0;

  for (const point of points) {
    if (point.kind === "node") {
      expect(networkPosition(point, middle)).toBe(point);
      continue;
    }
    if (point.layer !== 0) {
      expect(networkPosition(point, middle)).toBe(point.states[3]);
      continue;
    }

    expect(networkPosition(point, start)).toBe(point.states[3]);
    expect(networkPosition(point, end)).toBe(point.states[0]);
    const position = networkPosition(point, middle);
    const linear = {
      x: (point.states[3].x + point.states[0].x) / 2,
      y: (point.states[3].y + point.states[0].y) / 2,
    };
    expect(position.x).toBeCloseTo(linear.x, 10);
    expect(position.y).toBeCloseTo(linear.y, 10);
    if (
      Math.abs(point.states[0].x - point.states[3].x) > 0.02 &&
      Math.abs(point.states[0].y - point.states[3].y) > 0.02
    )
      varied += 1;
    expect(position.x).toBeGreaterThan(networkLayers[0][0].x);
    expect(position.x).toBeLessThan(networkLayers[1][0].x);
    expect(position.y).toBeGreaterThan(0);
    expect(position.y).toBeLessThan(1);
  }
  expect(varied).toBeGreaterThan(500);
});
