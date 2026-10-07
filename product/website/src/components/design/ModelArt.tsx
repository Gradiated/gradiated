import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { NeatGradient } from "@firecms/neat";

/**
 * Programmatic artwork for a model card: a Neat gradient in the
 * provider's colours, the mark floating white on it.
 *
 * Neat (neat.firecms.co) drives the material — a 3D animated gradient
 * with real body, saturation intact. Each model brings its palette; the
 * slug seeds the wave character (frequencies, amplitude), so cards share
 * one material but no two move alike.
 *
 * Reduced motion pins speed to zero — Neat renders one still frame's
 * worth of gradient and sits.
 */

const PALETTES: Record<string, string[]> = {
  "deepseek-v4-1-flash": ["#4D6BFE", "#8FA5FF", "#DCE4FF", "#2B3FA8"],
  "glm-5-3-flash": ["#5E5CE6", "#9D8CFF", "#E4DEFF", "#3634A3"],
  "kev-9b": ["#E9B748", "#BE5E31", "#F6E7C8", "#5E6043"],
};

const FALLBACK = ["#C8C1B4", "#EFECE3", "#A9A192", "#6B6557"];

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
}: {
  icon?: string;
  name: string;
  slug: string;
}): ReactElement => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

    let seed = hashSeed(slug);
    const rnd = (): number => {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };
    const palette = PALETTES[slug] ?? FALLBACK;

    const gradient = new NeatGradient({
      ref: canvas,
      colors: palette.map((color) => ({ color, enabled: true })),
      /* slow enough to be calm, fast enough to be seen */
      speed: reduced ? 0 : 2,
      horizontalPressure: 2 + Math.round(rnd() * 3),
      verticalPressure: 2 + Math.round(rnd() * 3),
      waveFrequencyX: 1 + Math.round(rnd() * 3),
      waveFrequencyY: 2 + Math.round(rnd() * 3),
      waveAmplitude: 4 + Math.round(rnd() * 3),
      shadows: 2,
      highlights: 4,
      colorBrightness: 1,
      colorSaturation: 0,
      wireframe: false,
      colorBlending: 6,
      backgroundColor: palette[2],
      backgroundAlpha: 1,
      resolution: 0.5,
      licenseKey: NEAT_LICENSE,
    });

    return () => {
      gradient.destroy();
    };
  }, [slug]);

  return (
    <span aria-hidden className="gr-models-card-art">
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
