import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { Logo } from "./Logo";

/**
 * Programmatic artwork for a model card: a soft gradient field with the
 * provider's mark floating on it.
 *
 * The field is a handful of colour pools from the model's own palette,
 * placed by a seeded RNG (the slug is the seed, so every render of a card
 * is identical and no two cards agree), then blurred into one wash — the
 * Apple-Card material, in each provider's colours. Canvas2D with a blur
 * pass rather than a shader: the wash is static, so there is nothing for
 * a per-frame GPU program to do, and one 320x400 paint at mount costs
 * nothing.
 *
 * Kev carries the Gradiated mark — it is ours.
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

const W = 320;
const H = 400;

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
    const palette = PALETTES[slug] ?? FALLBACK;

    /* pools on an offscreen buffer, blurred on the way to the card */
    const buf = document.createElement("canvas");
    buf.width = W;
    buf.height = H;
    const bctx = buf.getContext("2d");
    if (!bctx) return;

    bctx.fillStyle = palette[2];
    bctx.fillRect(0, 0, W, H);
    for (let i = 0; i < 7; i++) {
      const colour = palette[Math.floor(rnd() * palette.length)];
      const x = rnd() * W;
      const y = rnd() * H;
      const r = 90 + rnd() * 150;
      const pool = bctx.createRadialGradient(x, y, 0, x, y, r);
      pool.addColorStop(0, colour);
      pool.addColorStop(1, `${colour}00`);
      bctx.fillStyle = pool;
      bctx.globalAlpha = 0.65 + rnd() * 0.35;
      bctx.beginPath();
      bctx.arc(x, y, r, 0, Math.PI * 2);
      bctx.fill();
    }
    bctx.globalAlpha = 1;

    canvas.width = W;
    canvas.height = H;
    ctx.filter = "blur(34px)";
    /* oversized draw, so the blur never samples past the edge into
       transparency and dims the border */
    ctx.drawImage(buf, -40, -50, W + 80, H + 100);
    ctx.filter = "none";
  }, [slug]);

  return (
    <span aria-hidden className="gr-models-card-art">
      <canvas className="gr-model-art-field" ref={canvasRef} />
      {icon ? (
        <img alt="" className="gr-model-art-mark" src={icon} />
      ) : (
        <span className="gr-model-art-mark gr-model-art-mark--own">
          <Logo mark />
        </span>
      )}
      <span className="gr-visually-hidden">{name}</span>
    </span>
  );
};
