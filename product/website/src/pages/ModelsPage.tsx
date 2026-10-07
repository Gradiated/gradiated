import { useState } from "react";
import type { ReactElement } from "react";
import { Link } from "react-router-dom";
import {
  Arrow,
  Band,
  Footer,
  Module,
  Nav,
  Substrate,
  Tabs,
} from "../components/design";
import { models } from "../models";
import "../styles/index.css";

/**
 * The model listing: /models/.
 *
 * Set entirely in the system's own voice: the hero class for the title, the
 * segmented Tabs track for the category rail, label/heading for the card
 * captions, and the link-with-arrow for the request line. One white portrait
 * card per model, upper field reserved for artwork (posters land per-model,
 * as the Library's did).
 *
 * Categories: everything we serve today is an LLM. The other rails exist
 * because the catalogue will grow into them; empty, they say so and lean on
 * the request link.
 */

const CATEGORIES = ["LLMs", "Imagen", "World"] as const;

export const ModelsPage = (): ReactElement => {
  const [category, setCategory] = useState<string>(CATEGORIES[0]);
  const listed = category === "LLMs" ? models : [];

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module index={0}>
          <div className="gr-models-head">
            <h1 className="gr-hero">Post training models</h1>
            <Tabs
              label="Model categories"
              onChange={setCategory}
              options={[...CATEGORIES]}
              value={category}
            />
          </div>

          {listed.length > 0 ? (
            <div className="gr-models-grid">
              {listed.map((model) => (
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
          ) : (
            <p className="gr-body gr-muted gr-models-empty">
              Nothing here yet — the first{" "}
              {category === "Imagen" ? "image" : "world"} models are on their
              way.
            </p>
          )}

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
