import type { ChipGrain } from "./chip-grains";

type Position = { u: number; v: number };
type Point = [number, number];

export const fpgaBlocks: Position[] = Array.from({ length: 9 }, (_, index) => ({
  u: ((index % 3) - 1) * 2.35,
  v: (Math.floor(index / 3) - 1) * 2.35,
}));

export const projectFpga = (u: number, v: number, z = 0) => ({
  x: 320 + (u - v) * 40,
  y: 200 + (u + v) * 23 - z * 28,
});

const lanes = [-0.21, -0.07, 0.07, 0.21];

export const fpgaTracks: Point[][] = [-3.525, -1.175, 1.175, 3.525].flatMap(
  (channel) =>
    lanes.flatMap((offset): Point[][] => [
      [
        [-3.735, channel + offset],
        [3.735, channel + offset],
      ],
      [
        [channel + offset, -3.735],
        [channel + offset, 3.735],
      ],
    ]),
);

export const fpgaConnections: Point[][] = fpgaBlocks.flatMap(({ u, v }) =>
  [-1, 1].flatMap((direction) =>
    lanes.flatMap((lane): Point[][] => [
      [
        [u + direction * 0.5, v + lane],
        [u + direction * 1.175 + lane, v + lane],
      ],
      [
        [u + lane, v + direction * 0.5],
        [u + lane, v + direction * 1.175 + lane],
      ],
    ]),
  ),
);

const portSelection = [0, 2, 3, 1, 3, 0, 2, 0, 1];
const trunk = -1.245;
const branches = fpgaBlocks.map(({ u, v }, index): Point[] => {
  const channel = v < 0 ? v + 1.175 : v - 1.175;
  const side = v < 0 ? 0.5 : -0.5;
  const lane = lanes[portSelection[index]];

  return [
    [u + lane, channel + lane],
    [u + lane, v + side],
  ];
});
const busLevels = [...new Set(branches.map((branch) => branch[0][1]))].sort(
  (a, b) => a - b,
);
const buses = busLevels.map((v): Point[] => {
  const connections = [
    trunk,
    ...branches
      .filter((branch) => branch[0][1] === v)
      .map((branch) => branch[0][0]),
  ];

  return [
    [Math.min(...connections), v],
    [Math.max(...connections), v],
  ];
});

export const fpgaRoutes: Point[][] = [
  [
    [trunk, busLevels[0]],
    [trunk, busLevels[busLevels.length - 1]],
  ],
  ...buses,
  ...branches,
];

const fpgaJunctions: Point[] = [
  ...busLevels.map((v): Point => [trunk, v]),
  ...branches.map((branch) => branch[0]),
];

const blockSilhouettes = fpgaBlocks.map(({ u, v }) => [
  projectFpga(u - 0.5, v - 0.5, 0.25),
  projectFpga(u + 0.5, v - 0.5, 0.25),
  projectFpga(u + 0.5, v - 0.5),
  projectFpga(u + 0.5, v + 0.5),
  projectFpga(u - 0.5, v + 0.5),
  projectFpga(u - 0.5, v + 0.5, 0.25),
]);

const hiddenByBlock = (point: { x: number; y: number }) =>
  blockSilhouettes.some((polygon) =>
    polygon.every((a, index) => {
      const b = polygon[(index + 1) % polygon.length];
      const dx = b.x - a.x;
      const dy = b.y - a.y;

      return (
        dx * (point.y - a.y) - dy * (point.x - a.x) >= -1.2 * Math.hypot(dx, dy)
      );
    }),
  );

export const makeFpgaGrains = (): ChipGrain[] => {
  let seed = 3081;
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  const points: Array<{ chip: { x: number; y: number }; surface: number }> = [];
  const add = (u: number, v: number, z: number, surface: number) => {
    const chip = projectFpga(u, v, z);
    if ((surface === 2 || surface === 3) && hiddenByBlock(chip)) return;

    points.push({ chip, surface });
  };
  const line = (a: number[], b: number[], surface: number, density = 48) => {
    const count = Math.ceil(
      Math.hypot(...a.map((value, i) => value - b[i])) * density,
    );

    for (let i = 0; i <= count; i += 1) {
      const t = i / count;
      const [u, v, z] = a.map((value, j) => value + (b[j] - value) * t);
      add(u, v, z, surface);
    }
  };

  for (const [a, b] of [...fpgaTracks, ...fpgaConnections]) {
    line([...a, 0], [...b, 0], 2, 38);
  }
  for (const route of fpgaRoutes) {
    for (let i = 1; i < route.length; i += 1) {
      line([...route[i - 1], 0], [...route[i], 0], 3, 60);
    }
  }
  for (const [u, v] of fpgaJunctions) {
    for (let i = 0; i < 12; i += 1) {
      add(u + (random() - 0.5) * 0.07, v + (random() - 0.5) * 0.07, 0, 3);
    }
  }

  for (const { u, v } of fpgaBlocks) {
    for (let i = 0; i < 180; i += 1) {
      add(u - 0.5 + random(), v - 0.5 + random(), 0.25, 1);
      if (i < 70) {
        add(u - 0.5 + random(), v + 0.5, random() * 0.25, 0);
        add(u + 0.5, v - 0.5 + random(), random() * 0.25, 0);
      }
    }

    const corners = [
      [u - 0.5, v - 0.5, 0.25],
      [u + 0.5, v - 0.5, 0.25],
      [u + 0.5, v + 0.5, 0.25],
      [u - 0.5, v + 0.5, 0.25],
    ];

    for (let i = 0; i < 4; i += 1) line(corners[i], corners[(i + 1) % 4], 0);
    for (const i of [1, 2, 3]) {
      line(corners[i], [corners[i][0], corners[i][1], 0], 0);
    }
    line([u + 0.5, v - 0.5, 0], [u + 0.5, v + 0.5, 0], 0);
    line([u + 0.5, v + 0.5, 0], [u - 0.5, v + 0.5, 0], 0);
  }

  const lettering = [
    ["0111", "1000", "1000", "1000", "1000", "1000", "0111"],
    ["1000", "1000", "1000", "1000", "1000", "1000", "1111"],
    ["1110", "1001", "1001", "1110", "1001", "1001", "1110"],
  ];

  for (const { u, v } of fpgaBlocks) {
    lettering.forEach((letter, index) => {
      letter.forEach((row, y) => {
        [...row].forEach((pixel, x) => {
          if (pixel !== "1") return;

          for (let i = 0; i < 3; i += 1) {
            add(
              u + (index * 5 + x - 6.5) * 0.052 + (random() - 0.5) * 0.025,
              v + (y - 3) * 0.062 + (random() - 0.5) * 0.025,
              0.26,
              4,
            );
          }
        });
      });
    });
  }

  return points.map(({ chip, surface }) => {
    const radius = Math.sqrt(-2 * Math.log(Math.max(random(), 0.00001)));
    const angle = random() * Math.PI * 2;
    const x = 320 + Math.cos(angle) * radius * 135;
    const y = 200 + Math.sin(angle) * radius * 68 + Math.sin(x * 0.013) * 22;

    return {
      chip,
      surface,
      sand: { x, y },
      shade: random(),
      size: surface === 4 ? 0.55 + random() * 0.3 : 0.55 + random() * 0.8,
    };
  });
};
