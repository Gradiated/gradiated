import type { ScatterPattern } from "./wafer-field";

export type ArtworkPreset = {
  background: string;
  backgroundTo: string;
  chip: string;
  invert: boolean;
  palette: string[];
  scatter: ScatterPattern;
  seed: number;
  source: string;
  threshold: number;
};

const palettes = {
  aegean: {
    background: "#407486",
    backgroundTo: "#a9bebf",
    chip: "#efece3",
    palette: ["#f6f3ec", "#d5ccbb", "#a9bebf", "#73959f", "#1f3b50"],
  },
  grove: {
    background: "#505e39",
    backgroundTo: "#aab49a",
    chip: "#efece3",
    palette: ["#f6f3ec", "#d5ccbb", "#aab49a", "#838e70", "#232a17"],
  },
  kiln: {
    background: "#be5e31",
    backgroundTo: "#e9b748",
    chip: "#efece3",
    palette: ["#f6f3ec", "#e7e2d6", "#e9b748", "#be5e31", "#883534"],
  },
  plum: {
    background: "#696585",
    backgroundTo: "#b4adb8",
    chip: "#efece3",
    palette: ["#f6f3ec", "#d5ccbb", "#b4adb8", "#8b87a4", "#291e3a"],
  },
  taupe: {
    background: "#94754f",
    backgroundTo: "#d5ccbb",
    chip: "#232a17",
    palette: ["#f6f3ec", "#e7e2d6", "#c8c1b4", "#94754f", "#323c20"],
  },
};

export const artworkBackground = ({
  background,
  backgroundTo,
  seed,
}: Pick<ArtworkPreset, "background" | "backgroundTo" | "seed">): string =>
  `linear-gradient(${118 + (seed % 37)}deg, ${background}, ${backgroundTo})`;

const source = (
  name:
    | "circuit-black"
    | "circuit-green"
    | "dunes-aerial"
    | "sand-ripples"
    | "waves-aerial",
) => `/assets/artwork-sources/${name}.jpg`;

/** The photographs supply natural structure; only the sampled field survives. */
export const artworkPresets: Record<string, ArtworkPreset> = {
  carat: {
    ...palettes.grove,
    invert: true,
    scatter: "orbit-in",
    seed: 11,
    source: source("circuit-black"),
    threshold: 112,
  },
  thesis: {
    ...palettes.aegean,
    invert: false,
    scatter: "radial-burst",
    seed: 23,
    source: source("dunes-aerial"),
    threshold: 142,
  },
  mission: {
    ...palettes.grove,
    invert: true,
    scatter: "radial-burst",
    seed: 32,
    source: source("waves-aerial"),
    threshold: 112,
  },
  product: {
    ...palettes.aegean,
    invert: false,
    scatter: "wave-rise",
    seed: 43,
    source: source("circuit-green"),
    threshold: 132,
  },
  sequencing: {
    ...palettes.plum,
    invert: true,
    scatter: "gravity-drop",
    seed: 54,
    source: source("circuit-black"),
    threshold: 146,
  },
  people: {
    ...palettes.taupe,
    invert: true,
    scatter: "orbit-in",
    seed: 61,
    source: source("sand-ripples"),
    threshold: 128,
  },
  judgement: {
    ...palettes.grove,
    invert: false,
    scatter: "spiral-in",
    seed: 72,
    source: source("dunes-aerial"),
    threshold: 156,
  },
  gate: {
    ...palettes.kiln,
    invert: false,
    scatter: "gravity-drop",
    seed: 83,
    source: source("circuit-green"),
    threshold: 110,
  },
  values: {
    ...palettes.aegean,
    invert: true,
    scatter: "random",
    seed: 98,
    source: source("waves-aerial"),
    threshold: 154,
  },
  brand: {
    ...palettes.plum,
    invert: false,
    scatter: "orbit-in",
    seed: 107,
    source: source("sand-ripples"),
    threshold: 144,
  },
};
