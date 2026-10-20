import type { ReactElement } from "react";

/**
 * The models marquee, between the loop fold and the chip fold: the open
 * model families Gradiated post-trains, as app-icon pillows drifting
 * left to right. Text tiles until the real logo set lands — each entry
 * takes a `src` when it does.
 */

const MODELS: { name: string; src?: string }[] = [
  { name: "Llama", src: "/assets/models/meta-color.svg" },
  { name: "Qwen", src: "/assets/models/qwen-color.svg" },
  { name: "DeepSeek", src: "/assets/models/deepseek-color.svg" },
  { name: "Mistral", src: "/assets/models/mistral-color.svg" },
  { name: "Gemma", src: "/assets/models/gemma-color.svg" },
  { name: "Kimi", src: "/assets/models/kimi.svg" },
  { name: "GLM", src: "/assets/models/zhipu-color.svg" },
  { name: "Phi", src: "/assets/models/microsoft-color.svg" },
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
      One API, all your favorite models
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
