export const siliconColours = {
  top: "#616469",
  side: "#414449",
  front: "#505359",
  edge: "#383b40",
  hatch: "#85888d",
  label: "#f5f3ed",
};

export const logicColours = {
  high: "var(--fab-logic-high, #40865a)",
  low: "var(--fab-logic-low, #b65b55)",
};

type MaterialFaces = [string, string, string];

const nDopedColours: MaterialFaces = [
  "var(--color-aegean-400)",
  "var(--color-aegean-600)",
  "var(--color-aegean-500)",
];

export const materialColours = {
  well: nDopedColours,
  n: nDopedColours,
  p: [
    "var(--color-kiln-600)",
    "var(--color-kiln-700)",
    "color-mix(in srgb, var(--color-kiln-600) 75%, var(--color-kiln-700))",
  ],
  insulator: [
    "var(--color-taupe-300)",
    "var(--color-taupe-400)",
    "var(--color-taupe-350)",
  ],
  nitride: [
    "var(--color-kiln-300)",
    "var(--color-taupe-500)",
    "color-mix(in srgb, var(--color-kiln-300) 65%, var(--color-taupe-500))",
  ],
  resist: [
    "color-mix(in srgb, var(--color-plum-400) 60%, var(--color-light-000))",
    "var(--color-plum-500)",
    "var(--color-plum-400)",
  ],
  gate: [
    "var(--color-grove-500)",
    "var(--color-grove-650)",
    "var(--color-grove-600)",
  ],
  metal: [
    "var(--color-light-400)",
    "var(--color-dark-300)",
    "var(--color-dark-400)",
  ],
} satisfies Record<string, MaterialFaces>;

export const exposureColours = {
  beamTop:
    "color-mix(in srgb, var(--color-light-000) 90%, var(--color-aegean-400))",
  beamBase: "var(--color-light-000)",
  glow: "var(--color-kiln-500)",
};

export const exposedResistColour = (amount: number, glow = 0) => {
  const exposed = `color-mix(in srgb, ${materialColours.resist[0]}, var(--color-plum-500) ${amount * 65}%)`;

  return glow > 0
    ? `color-mix(in srgb, ${exposed}, ${exposureColours.glow} ${glow * 100}%)`
    : exposed;
};
