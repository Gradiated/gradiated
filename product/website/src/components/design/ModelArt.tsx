import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/**
 * Programmatic artwork for a model card: a Neat gradient in the
 * provider's colours, the mark floating white on it.
 *
 * Neat (neat.firecms.co) drives the material. Each card wears one of the
 * editor's authored presets, extracted verbatim: Oil Slick on DeepSeek,
 * Neat on GLM, Time on Kev. The slug seeds the field so each card is
 * deterministic across loads.
 *
 * Reduced motion pins speed to zero — Neat renders one still frame's
 * worth of gradient and sits.
 */

type NeatPreset = Record<string, unknown>;

/* The editor's presets, verbatim. */
const OIL_SLICK: NeatPreset = {
  colors: [
    { color: "#D6D4D1", enabled: true },
    { color: "#C6A8F0", enabled: true },
    { color: "#FFC3DA", enabled: true },
    { color: "#FFF700", enabled: true },
    { color: "#FFE7A6", enabled: false },
    { color: "#A8EDE4", enabled: false },
  ],
  speed: 1.5,
  horizontalPressure: 4.6,
  verticalPressure: 4.6,
  waveFrequencyX: 1.5,
  waveFrequencyY: 1.5,
  waveAmplitude: 4,
  secondaryWaveEnabled: true,
  secondaryWaveFrequencyX: 2.6,
  secondaryWaveFrequencyY: 1.4,
  secondaryWaveAmplitude: 6,
  secondaryWaveSpeed: 0.45,
  secondaryWaveAngle: 1.15,
  shadows: 0,
  highlights: 1,
  colorBrightness: 1.02,
  colorSaturation: 1,
  wireframe: false,
  colorBlending: 4.8,
  backgroundColor: "#D6D4D1",
  backgroundAlpha: 1,
  grainScale: 1,
  grainSparsity: 0,
  grainIntensity: 0.08,
  grainSpeed: 0.05,
  resolution: 1,
  flowEnabled: true,
  flowDistortionA: 0.6,
  flowDistortionB: 1.2,
  flowScale: 1.2,
  flowEase: 0.15,
  prismEdgeEnabled: true,
  prismEdgeIntensity: 0.45,
  prismEdgeThinness: 4,
  prismEdgeSpread: 1.2,
  prismEdgeRipple: 0.8,
  prismEdgeSpeed: 0.35,
  shapeType: "plane",
  cameraLock: true,
};

const NEAT: NeatPreset = {
  colors: [
    { color: "#FF5772", enabled: true },
    { color: "#4CB4BB", enabled: true },
    { color: "#FFC600", enabled: true },
    { color: "#8B6AE6", enabled: true },
    { color: "#2E0EC7", enabled: true },
    { color: "#FF9A9E", enabled: true },
  ],
  speed: 2.5,
  horizontalPressure: 3,
  verticalPressure: 4,
  waveFrequencyX: 2,
  waveFrequencyY: 3,
  waveAmplitude: 5,
  shadows: 1,
  highlights: 5,
  colorBrightness: 1,
  colorSaturation: 7,
  wireframe: false,
  colorBlending: 8,
  backgroundColor: "#003FFF",
  backgroundAlpha: 1,
  resolution: 1,
  flowEnabled: true,
  shapeType: "plane",
  cameraLock: true,
};

const TIME: NeatPreset = {
  colors: [
    { color: "#167CB3", enabled: true },
    { color: "#CB9854", enabled: true },
    { color: "#CE96CE", enabled: true },
    { color: "#E0115F", enabled: true },
    { color: "#FFFFFF", enabled: false },
    { color: "#000000", enabled: false },
  ],
  speed: 2.5,
  horizontalPressure: 5,
  verticalPressure: 5,
  waveFrequencyX: 2,
  waveFrequencyY: 3,
  waveAmplitude: 6,
  shadows: 2,
  highlights: 0,
  colorBrightness: 0.9,
  colorSaturation: -3,
  wireframe: false,
  colorBlending: 5,
  backgroundColor: "#A1A4B7",
  backgroundAlpha: 1,
  resolution: 0.4,
  flowDistortionA: 3.7,
  flowDistortionB: 0.8,
  flowScale: 1.6,
  flowEase: 0.32,
  flowEnabled: true,
  domainWarpEnabled: true,
  domainWarpIntensity: 0.1,
  domainWarpScale: 2.4,
  vignetteIntensity: 0.45,
  vignetteRadius: 0.55,
  bloomIntensity: 1.9,
  bloomThreshold: 0.6,
  chromaticAberration: 17,
  shapeType: "ribbon",
  shapeRotationX: 0.348,
  shapeRotationY: -26.783,
  shapeRotationZ: -0.29,
  planeBend: 2.3,
  planeTwist: -2.9,
  silhouetteFade: 0.83,
  ribbonFade: 0.31,
  flatShading: false,
  cameraLock: false,
  cameraRotationX: -0.014,
  cameraRotationY: -0.238,
};

/* Each provider's core colours, worn over the preset's physics: the
   materials keep their distinct motion, the paint stays on-brand so the
   row reads as one family. */
const BRAND: Record<string, { colors: string[]; bg: string }> = {
  "deepseek-v4-1-flash": {
    colors: ["#DCE4FF", "#8FA5FF", "#BFD1FF", "#4D6BFE"],
    bg: "#DCE4FF",
  },
  "glm-5-3-flash": {
    colors: ["#5E5CE6", "#9D8CFF", "#E4DEFF", "#3634A3"],
    bg: "#3634A3",
  },
  "kev-9b": {
    colors: ["#E9B748", "#BE5E31", "#F6E7C8", "#5E6043"],
    bg: "#C8C1B4",
  },
};

const PRESETS: Record<string, NeatPreset> = {
  "deepseek-v4-1-flash": OIL_SLICK,
  "glm-5-3-flash": NEAT,
  "kev-9b": TIME,
};

/* Domain-bound to gradiated.com (and localhost for dev) — public by
   design, useless elsewhere. Removes the NEAT watermark. */
const NEAT_LICENSE =
  "NEAT-eyJkb21haW4iOiJncmFkaWF0ZWQuY29tIiwiZW1haWwiOiJoZWxsb0BzYW11ZHJhZ3VwdGEuY29tIiwiaWF0IjoxNzkxMzQxMzg2fQ.9jvIzaNpbCRGyfwGVGrXBULGAYDm0--fQHtJ2DNbt4UYZ_xmhJUfRKqTw8ONvwyVsXwBR6LgwhY6dpqa1yOKqw";

const hashSeed = (s: string): number => {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) % 2147483646 || 11;
};

export const ModelArt = ({
  icon,
  name,
  slug,
  small = false,
}: {
  icon?: string;
  name: string;
  slug: string;
  /** Tile-sized: mark centred and shrunk, for the nav's model rows. */
  small?: boolean;
}): ReactElement => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    /* Imported here, not at the top: @firecms/neat is CommonJS, and a
       named import breaks the prerender's Node ESM pass. The gradient is
       client-only anyway — inside the effect, the server never loads it. */
    let gradient: { destroy(): void } | undefined;
    let cancelled = false;
    void import("@firecms/neat").then(({ NeatGradient }) => {
      if (cancelled) return;

      const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
      const preset = PRESETS[slug] ?? OIL_SLICK;
      const brand = BRAND[slug];

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      gradient = new NeatGradient({
        ref: canvas,
        ...(preset as any),
        ...(brand
          ? {
              colors: brand.colors.map((color) => ({ color, enabled: true })),
              backgroundColor: brand.bg,
            }
          : {}),
        /* Neat's seed is the time-accumulator's start: keep it SMALL.
           A raw 32-bit hash collapses mediump float precision and the
           field goes flat and motionless. */
        seed: hashSeed(slug) % 3600,
        ...(reduced ? { speed: 0 } : {}),
        licenseKey: NEAT_LICENSE,
      } as any);
    });

    return () => {
      cancelled = true;
      gradient?.destroy();
    };
  }, [slug]);

  return (
    <span
      aria-hidden
      className={`gr-models-card-art${small ? " gr-models-card-art--small" : ""}`}
    >
      <canvas className="gr-model-art-field" ref={canvasRef} />
      {icon ? (
        <img alt="" className="gr-model-art-mark" src={icon} />
      ) : (
        <span className="gr-model-art-mark gr-model-art-mark--letter">
          {name.charAt(0).toUpperCase()}
        </span>
      )}
      <span className="gr-visually-hidden">{name}</span>
    </span>
  );
};
