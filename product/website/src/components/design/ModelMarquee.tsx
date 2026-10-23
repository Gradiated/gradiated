import type { ReactElement } from "react";

/**
 * The model families Gradiated post-trains, as one static row of app-icon
 * pillows closing the products section. It drifted as a marquee for a
 * while, but eight logos fit the band — motion added a vanishing edge and
 * nothing else. Text tiles until the real logo set lands — each entry
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
    <div className="gr-marquee-row">
      <Tiles />
    </div>
  </section>
);
