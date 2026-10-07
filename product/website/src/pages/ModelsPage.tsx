import type { ReactElement } from "react";
import { Link } from "react-router-dom";
import {
  Arrow,
  Band,
  Footer,
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
 */

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
              <Link
                className="gr-models-card"
                key={model.slug}
                to={`/models/${model.slug}/`}
              >
                <span className="gr-models-card-art" />
                <span className="gr-label">{model.maker}</span>
                <span className="gr-heading">{model.name}</span>
              </Link>
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
