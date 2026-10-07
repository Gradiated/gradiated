import { useRef } from "react";
import type { ReactElement } from "react";
import { Link } from "react-router-dom";
import type { ModelPageData } from "../models";
import {
  Arrow,
  Band,
  Footer,
  ModelArt,
  Module,
  Nav,
  Substrate,
} from "../components/design";
import { models } from "../models";
import "../styles/index.css";

/**
 * The model listing: /models/.
 *
 * Set entirely in the system's own voice: the hero class for the title,
 * label/heading for the card captions, and the link-with-arrow for the
 * request line. One white portrait card per model, upper field reserved
 * for artwork (posters land per-model, as the Library's did).
 *
 * No category rail yet: with one category's worth of models, a filter is
 * furniture. It returns when the catalogue grows past LLMs.
 *
 * The cards tilt toward the cursor — a plate pivoting under the hand, the
 * same object-language as the chip fold's plates. Mouse only: a touch has
 * no hover, and reduced-motion readers get the flat card.
 */

/** Degrees of tilt at the card's edge. */
const TILT = 7;

const ModelCard = ({ model }: { model: ModelPageData }): ReactElement => {
  const ref = useRef<HTMLAnchorElement>(null);

  const onMove = (e: React.PointerEvent): void => {
    const el = ref.current;
    if (!el || e.pointerType !== "mouse") return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    el.style.setProperty("--ry", `${(px * TILT).toFixed(2)}deg`);
    el.style.setProperty("--rx", `${(-py * TILT).toFixed(2)}deg`);
  };

  const onLeave = (): void => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--ry", "0deg");
    el.style.setProperty("--rx", "0deg");
  };

  return (
    <Link
      className="gr-models-card"
      onPointerLeave={onLeave}
      onPointerMove={onMove}
      ref={ref}
      to={`/models/${model.slug}/`}
    >
      <ModelArt icon={model.icon} name={model.name} slug={model.slug} />
      <span className="gr-label">{model.maker}</span>
      <span className="gr-heading">{model.name}</span>
    </Link>
  );
};

export const ModelsPage = (): ReactElement => {
  return (
    <Substrate>
      <Nav />

      <Band>
        <Module index={0}>
          <div className="gr-models-head">
            <h1 className="gr-hero">Post training models</h1>
          </div>

          <div className="gr-models-grid">
            {models.map((model) => (
              <ModelCard key={model.slug} model={model} />
            ))}
          </div>

          <p className="gr-models-request">
            <span className="gr-muted">Don&apos;t see a model you want?</span>{" "}
            <a
              className="gr-link"
              href="mailto:hello@gradiated.com?subject=Model%20request"
            >
              Raise a model request
              <Arrow />
            </a>
          </p>
        </Module>
      </Band>

      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
