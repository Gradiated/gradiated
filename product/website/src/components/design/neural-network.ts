type Point = { x: number; y: number };

export const NETWORK_ASPECT = 2;

export const networkLayers = [3, 4, 4, 4, 2].map((count, layer) =>
  Array.from({ length: count }, (_, index) => ({
    x: 0.075 + layer * 0.2125,
    y: 0.5 + (index - (count - 1) / 2) * 0.205,
    layer,
  })),
);

export const networkConnections = networkLayers
  .slice(0, -1)
  .flatMap((nodes, layer) =>
    nodes.flatMap((from) =>
      networkLayers[layer + 1].map((to) => {
        const dx = to.x - from.x;
        const dy = (to.y - from.y) / NETWORK_ASPECT;
        const length = Math.hypot(dx, dy);
        const ux = dx / length;
        const uy = dy / length;
        const inset = 0.015;

        return {
          layer,
          from: {
            x: from.x + ux * inset,
            y: from.y + uy * inset * NETWORK_ASPECT,
          },
          to: { x: to.x - ux * inset, y: to.y - uy * inset * NETWORK_ASPECT },
          normal: { x: -uy, y: ux * NETWORK_ASPECT },
        };
      }),
    ),
  );

type ConnectionTarget = Point & { edge: number };

export type NetworkPoint = Point &
  (
    | { kind: "node"; layer: number }
    | {
        kind: "connection";
        layer: number;
        states: ConnectionTarget[];
      }
  );

const patternCount = 4;
const densities = [1, 2, 5, 12];
const weight = (edge: number, pattern: number) =>
  densities[(edge * 7 + pattern) % patternCount];

export const makeNetworkPoints = (next: () => number): NetworkPoint[] => {
  const points: NetworkPoint[] = [];
  const allocations = networkLayers.slice(0, -1).map((_, layer) => {
    const edges = networkConnections
      .map((edge, index) => ({ ...edge, index }))
      .filter((edge) => edge.layer === layer);

    return Array.from({ length: patternCount }, (_, pattern) => {
      const masses = edges.map((edge) => weight(edge.index, pattern));
      const total = masses.reduce((sum, mass) => sum + mass, 0);
      let cumulative = 0;

      return edges.map((edge, index) => {
        cumulative += masses[index] / total;

        return { edge: edge.index, end: cumulative };
      });
    });
  });

  networkConnections.forEach((edge, index) => {
    const count = Math.ceil(
      Math.hypot(
        edge.to.x - edge.from.x,
        (edge.to.y - edge.from.y) / NETWORK_ASPECT,
      ) * 650,
    );

    for (let i = 0; i < count; i += 1) {
      const along = i / (count - 1);
      const slot = next();
      const spread = next() * 2 - 1;
      const states = allocations[edge.layer].map((allocation, pattern) => {
        // Keep a few grains on every settled connection, including the weakest paths.
        const selected =
          i % 5 === 0
            ? index
            : (
                allocation.find((entry) => slot < entry.end) ??
                allocation.at(-1)!
              ).edge;
        const target = networkConnections[selected];
        const position =
          i % 5 === 0
            ? along
            : (along + pattern * 0.381966 + slot * (pattern + 1)) % 1;
        const taper = 0.4 + Math.sin(position * Math.PI) * 0.6;
        const offset = spread * 0.0025 * taper;

        return {
          x:
            target.from.x +
            (target.to.x - target.from.x) * position +
            target.normal.x * offset,
          y:
            target.from.y +
            (target.to.y - target.from.y) * position +
            target.normal.y * offset,
          edge: selected,
        };
      });

      points.push({
        x: states[patternCount - 1].x,
        y: states[patternCount - 1].y,
        kind: "connection",
        layer: edge.layer,
        states,
      });
    }
  });

  for (const nodes of networkLayers) {
    for (const node of nodes) {
      for (let i = 0; i < 135; i += 1) {
        const angle = next() * Math.PI * 2;
        const radius = Math.sqrt(next()) * 0.017;

        points.push({
          x: node.x + Math.cos(angle) * radius,
          y: node.y + Math.sin(angle) * radius * NETWORK_ASPECT,
          kind: "node",
          layer: node.layer,
        });
      }
    }
  }

  return points.sort((a, b) => a.x - b.x || a.y - b.y);
};

const easeInOut = (value: number) => {
  const t = Math.min(1, Math.max(0, value));

  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
};

export const NETWORK_CYCLE_SECONDS = 4.2;

export const networkFrame = (clock: number) => {
  const cycle = Math.floor(clock / NETWORK_CYCLE_SECONDS);
  const phase = clock - cycle * NETWORK_CYCLE_SECONDS;

  return {
    previousPattern: (cycle + patternCount - 1) % patternCount,
    currentPattern: cycle % patternCount,
    layers: networkLayers.slice(0, -1).map((_, layer) => ({
      progress: Math.min(1, Math.max(0, (phase - 0.2 - layer * 0.85) / 0.65)),
    })),
  };
};

export const networkPosition = (
  point: NetworkPoint,
  frame: ReturnType<typeof networkFrame>,
): Point => {
  if (point.kind === "node") return point;

  const from = point.states[frame.previousPattern];
  const to = point.states[frame.currentPattern];
  const progress = frame.layers[point.layer].progress;
  if (progress === 0) return from;
  if (progress === 1) return to;

  const t = easeInOut(progress);

  return { x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t };
};
