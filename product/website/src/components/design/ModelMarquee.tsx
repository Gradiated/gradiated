import type { ReactElement } from "react";

/**
 * The models marquee, between the loop fold and the chip fold: the open
 * model families Gradiated post-trains, as app-icon pillows drifting
 * left to right. Text tiles until the real logo set lands — each entry
 * takes a `src` when it does.
 */

const MODELS: { name: string; src?: string }[] = [
  { name: "Llama" },
  { name: "Qwen" },
  { name: "DeepSeek" },
  { name: "Mistral" },
  { name: "Gemma" },
  { name: "Kimi" },
  { name: "GLM" },
  { name: "Phi" },
];

const Tiles = (): ReactElement => (
  <>
    {MODELS.map(({ name, src }) => (
      <div className="gr-marquee-tile" key={name}>
        {src ? <img alt={name} src={src} /> : <span>{name}</span>}
      </div>
    ))}
  </>
);

export const ModelMarquee = (): ReactElement => (
  <section className="gr-marquee">
    <h2 className="gr-heading gr-marquee-title">
      Available on your favourite models
    </h2>
    <div className="gr-marquee-lane">
      {/* two copies; the animation walks one copy's width, so the loop
          is seamless */}
      <div className="gr-marquee-track">
        <Tiles />
        <Tiles />
      </div>
    </div>
  </section>
);
