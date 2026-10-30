type Point = { x: number; y: number };
export type ChipGrain = {
  sand: Point;
  chip: Point;
  size: number;
  shade: number;
  surface: number;
};

export const makeChipGrains = (): ChipGrain[] => {
  let seed = 719;
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  const points: Array<Point & { surface: number }> = [];
  const project = (u: number, v: number, z: number): Point => ({
    x: 320 + (u - v) * 125,
    y: 278 + (u + v) * 48 - z * 24,
  });
  const add = (u: number, v: number, z: number, surface: number) => {
    points.push({ ...project(u, v, z), surface });
  };
  const line = (a: number[], b: number[], surface: number, density = 100) => {
    const count = Math.ceil(Math.hypot(...a.map((n, i) => n - b[i])) * density);
    for (let i = 0; i <= count; i += 1) {
      const t = i / count;
      add(
        ...(a.map((n, j) => n + (b[j] - n) * t) as [number, number, number]),
        surface,
      );
    }
  };
  // The missing front quadrant exposes the wiring levels and vertical contacts.
  const cut = (u: number, v: number) => u > 0.16 && v > -0.12;
  for (let i = 0; i < 1600; i += 1) {
    const u = random() * 2 - 1;
    const v = random() * 2 - 1;
    add(u, v, 0, 0);
    add(u, 1, -random() * 0.7, 0);
    add(1, v, -random() * 0.7, 0);
  }
  for (let layer = 1; layer <= 4; layer += 1) {
    const z = layer * 0.95;
    for (let i = 0; i < 260; i += 1) {
      const u = random() * 2 - 1;
      const v = random() * 2 - 1;
      if (!cut(u, v)) add(u, v, z, 1);
      if (v > -0.12) add(0.16, v, z - random() * 0.38, 1);
      if (u > 0.16) add(u, -0.12, z - random() * 0.38, 1);
    }
    const corners = [
      [-1, -1],
      [1, -1],
      [1, -0.12],
      [0.16, -0.12],
      [0.16, 1],
      [-1, 1],
      [-1, -1],
    ];
    for (let i = 1; i < corners.length; i += 1) {
      line([...corners[i - 1], z], [...corners[i], z], 1, 55);
    }
    for (let track = 0; track < 10; track += 1) {
      const lane = -0.91 + track * 0.19;
      const alongU = layer % 2 === 1;
      const end = lane > (alongU ? -0.12 : 0.16) ? (alongU ? 0.16 : -0.12) : 1;
      for (const offset of [-0.016, 0.016]) {
        const a = alongU
          ? [-1, lane + offset, z + 0.08]
          : [lane + offset, -1, z + 0.08];
        const b = alongU
          ? [end, lane + offset, z + 0.08]
          : [lane + offset, end, z + 0.08];
        line(a, b, 2, 90);
      }
      if (track % 2 === 0) {
        const u = alongU ? end - 0.06 : lane;
        const v = alongU ? lane : end - 0.06;
        line([u, v, z + 0.08], [u, v, z - 0.87], 2, 50);
      }
    }
  }
  for (let track = 0; track < 9; track += 1) {
    const u = 0.25 + (track % 3) * 0.25;
    const v = 0.05 + Math.floor(track / 3) * 0.29;
    line([u, v, 0.07], [u + 0.12, v, 0.07], 2, 130);
    line([u + 0.06, v - 0.07, 0.12], [u + 0.06, v + 0.07, 0.12], 2, 100);
  }
  return points.map((chip, i) => {
    const t = i / points.length;
    const x = -36 + Math.pow(random(), 1.2) * 700;
    const ridge =
      36 + 304 * (1 - Math.pow(1 - Math.min(1, Math.max(0, x / 640)), 2.2));
    const depth = random() < 0.16 ? random() : Math.pow(random(), 0.43);
    const y = ridge + depth * Math.max(0, 414 - ridge);
    return {
      chip,
      sand: {
        x,
        y,
      },
      shade: random(),
      surface: chip.surface,
      size: 0.55 + random() * 0.8 + t * 0.12,
    };
  });
};
