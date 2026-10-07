import { useState } from "react";
import type { ReactElement } from "react";
import { Link } from "react-router-dom";
import { Band, Footer, Module, Nav, Substrate } from "../components/design";
import { models } from "../models";
import "../styles/index.css";

/**
 * The model listing: /models/.
 *
 * A title, a category rail, and one portrait card per model — white panels
 * on the substrate, like the news grid's media wells, each leading to the
 * model's own page. The card's upper field is reserved for artwork (the
 * posters land per-model, as the Library's did); until then the panel
 * carries itself.
 *
 * Categories: every model we serve today is an LLM. The other two rails
 * exist because the catalogue will grow into them; empty, they show the
 * request line, which is the honest answer and also the call to action.
 */

const CATEGORIES = [
  { id: "llms", label: "LLMs" },
  { id: "imagen", label: "Imagen" },
  { id: "world", label: "World" },
] as const;

type CategoryId = (typeof CATEGORIES)[number]["id"];

export const ModelsPage = (): ReactElement => {
  const [category, setCategory] = useState<CategoryId>("llms");
  const listed = category === "llms" ? models : [];

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module index={0}>
          <div className="gr-models-head">
            <h1 className="gr-models-title">Post training models</h1>
            <div aria-label="Model categories" className="gr-models-rail" role="tablist">
              {CATEGORIES.map((c) => (
                <button
                  aria-selected={category === c.id}
                  className={`gr-models-pill${category === c.id ? " gr-models-pill--on" : ""}`}
                  key={c.id}
                  onClick={() => setCategory(c.id)}
                  role="tab"
                  type="button"
                >
                  {c.label}
                </button>
              ))}
            </div>
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
                  <span className="gr-models-card-maker">{model.maker}</span>
                  <span className="gr-models-card-name">{model.name}</span>
                </Link>
              ))}
            </div>
          ) : (
            <p className="gr-models-empty">
              Nothing here yet — the first {category === "imagen" ? "image" : "world"}{" "}
              models are on their way.
            </p>
          )}

          <p className="gr-models-request">
            Don&apos;t see a model you want?{" "}
            <a href="mailto:hello@gradiated.com?subject=Model%20request">
              Raise a model request &gt;
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
