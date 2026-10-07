import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/**
 * Programmatic artwork for a model card: a soft gradient field with the
 * provider's mark floating on it.
 *
 * The field is DOMAIN-WARPED noise: two fbm fields, one bending the
 * coordinates the other is read through, so the colour runs in currents
 * rather than pooling in blurred circles. The palette is a ramp the field
 * value indexes into, and the slug seeds everything — warp strength, flow
 * direction, scale, and the ramp's order — so each card differs in
 * STRUCTURE, not just hue, while staying identical across renders.
 * One low-res per-pixel pass at mount plus a blur on the way up; a live
 * shader would be paying per-frame for a static material.
 *
 * A model without a provider mark wears its initial in a square — the
 * same stand-in rule the data's `mark` field plays elsewhere.
 */

/** Each model's pools: anchored to the provider's brand colour. */
const PALETTES: Record<string, string[]> = {
  "deepseek-v4-1-flash": ["#4D6BFE", "#8FA5FF", "#DCE4FF", "#2B3FA8"],
  "glm-5-3-flash": ["#5E5CE6", "#9D8CFF", "#E4DEFF", "#3634A3"],
  "kev-9b": ["#E9B748", "#BE5E31", "#F6E7C8", "#5E6043"],
};

const FALLBACK = ["#C8C1B4", "#EFECE3", "#A9A192", "#6B6557"];

const hashSeed = (s: string): number => {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) % 2147483646 || 11;
};

/* field resolution: low, the blur upsamples it */
const W = 140;
const H = 176;

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
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let seed = hashSeed(slug);
    const rnd = (): number => {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };

    /* the ramp: palette entries as RGB stops, order shuffled by the seed */
    const hex = (c: string): [number, number, number] => [
      parseInt(c.slice(1, 3), 16),
      parseInt(c.slice(3, 5), 16),
      parseInt(c.slice(5, 7), 16),
    ];
    const ramp = (PALETTES[slug] ?? FALLBACK).map(hex);
    for (let i = ramp.length - 1; i > 0; i--) {
      const j = Math.floor(rnd() * (i + 1));
      [ramp[i], ramp[j]] = [ramp[j], ramp[i]];
    }

    /* cheap value noise + fbm, in the house's own idiom (HeroBeamRaw) */
    const hash2 = (x: number, y: number): number => {
      const v = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
      return v - Math.floor(v);
    };
    const noise = (x: number, y: number): number => {
      const ix = Math.floor(x), iy = Math.floor(y);
      const fx = x - ix, fy = y - iy;
      const ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
      const a = hash2(ix, iy), b = hash2(ix + 1, iy);
      const c = hash2(ix, iy + 1), d = hash2(ix + 1, iy + 1);
      return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy;
    };
    const fbm = (x: number, y: number): number =>
      0.55 * noise(x, y) + 0.3 * noise(x * 2.1, y * 2.1) + 0.15 * noise(x * 4.3, y * 4.3);

    /* the seed shapes the material, not just its placement */
    const ox = rnd() * 40, oy = rnd() * 40;        /* where in the field */
    const scale = 1.1 + rnd() * 1.4;               /* current width */
    const warp = 1.2 + rnd() * 2.2;                /* how hard it bends */
    const ang = rnd() * Math.PI;                   /* flow direction */
    const ca = Math.cos(ang), sa = Math.sin(ang);

    const img = ctx.createImageData(W, H);
    const px = img.data;
    const N = ramp.length - 1;
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        /* rotate into the flow direction, then warp the read */
        const u = ((x * ca - y * sa) / W) * scale + ox;
        const v = ((x * sa + y * ca) / H) * scale + oy;
        const qx = fbm(u + 1.7, v + 9.2);
        const qy = fbm(u + 8.3, v + 2.8);
        const t = fbm(u + warp * qx, v + warp * qy);
        /* index the ramp; a second, finer field breathes the lightness */
        const f = Math.min(0.999, Math.max(0, (t - 0.18) * 1.6)) * N;
        const i0 = Math.floor(f), fr = f - i0;
        const c0 = ramp[i0], c1 = ramp[Math.min(N, i0 + 1)];
        const light = 0.92 + 0.16 * fbm(u * 3 + 4.4, v * 3 + 6.1);
        const o = (y * W + x) * 4;
        px[o] = Math.min(255, (c0[0] + (c1[0] - c0[0]) * fr) * light);
        px[o + 1] = Math.min(255, (c0[1] + (c1[1] - c0[1]) * fr) * light);
        px[o + 2] = Math.min(255, (c0[2] + (c1[2] - c0[2]) * fr) * light);
        px[o + 3] = 255;
      }
    }

    const buf = document.createElement("canvas");
    buf.width = W;
    buf.height = H;
    buf.getContext("2d")?.putImageData(img, 0, 0);

    canvas.width = W * 2;
    canvas.height = H * 2;
    /* a soft pass, not a heavy one: enough to melt the noise grain while
       keeping the currents legible */
    ctx.filter = "blur(7px)";
    ctx.drawImage(buf, -8, -10, W * 2 + 16, H * 2 + 20);
    ctx.filter = "none";
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
