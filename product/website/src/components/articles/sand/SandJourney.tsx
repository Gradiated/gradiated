import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import type { ArticleMetadata } from "../../../article-metadata";
import article from "../../../../content/articles/sand/script.md?sand-article";
import "./journey.css";

const stage = `<svg id="stage-svg" viewBox="0 0 440 440" aria-hidden="true">\n          <defs>\n            <clipPath id="crop"><rect id="crop-rect" x="0" y="0" width="440" height="440" /></clipPath>\n            <filter id="wobble" x="-10%" y="-10%" width="120%" height="120%">\n              <feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="7" result="n" />\n              <feDisplacementMap in="SourceGraphic" in2="n" scale="2.4" xChannelSelector="R" yChannelSelector="G" />\n            </filter>\n          </defs>\n          <g id="art">\n            <ellipse id="shadow" />\n            <path id="mesh" />\n            <g id="parts" clip-path="url(#crop)"></g>\n            <g id="d2"></g>\n          </g>\n        </svg>`;
const controls = `<details class="panel" hidden>\n    <summary>tweak</summary>\n    <label><span>spin</span><input type="range" data-ctl="spin" min="0" max="1.5" step="0.01" value="0.45" /></label>\n    <label><span>elevation</span><input type="range" data-ctl="elev" min="0" max="45" step="1" value="18" /></label>\n    <label><span>line</span><input type="range" data-ctl="weight" min="0.8" max="3" step="0.1" value="1.8" /></label>\n    <label><span>hold</span><input type="range" data-ctl="hold" min="0" max="0.45" step="0.01" value="0.18" /></label>\n    <label><span>light</span><input type="range" data-ctl="light" min="0" max="360" step="1" value="135" /></label>\n    <label class="check"><input type="checkbox" data-ctl="hatch" checked /><span>hatching</span></label>\n    <label class="check"><input type="checkbox" data-ctl="wobble" /><span>hand-drawn wobble</span></label>\n    <label class="check"><input type="checkbox" data-ctl="mesh" /><span>show mesh</span></label>\n    <output id="readout"></output>\n  </details>`;

export const SandJourney = ({
  article: metadata,
}: {
  article: ArticleMetadata;
}): ReactElement => {
  const hostRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    let cleanup = () => {};
    void import("./runtime/main.js").then(({ mountSandScenes }) => {
      if (disposed) return;
      cleanup = mountSandScenes(host);
      host.dataset.animationReady = "true";
    });
    return () => {
      disposed = true;
      cleanup();
    };
  }, []);

  return (
    <article className="sand-journey" ref={hostRef}>
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&display=swap"
        precedence="sand-diagrams"
      />
      <a className="sand-return gr-label" href="/library/?show=hardware">
        ← Hardware library
      </a>
      <p className="sand-byline">
        Hardware
        {metadata.status === "published" ? (
          <>
            {" · "}
            <time dateTime={metadata.publishedAt}>
              {new Date(metadata.publishedAt).toLocaleDateString("en-GB", {
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </time>
          </>
        ) : null}
      </p>
      <div className="post">
        <div className="stage-col">
          <div className="stage" dangerouslySetInnerHTML={{ __html: stage }} />
        </div>
        <div className="prose" dangerouslySetInnerHTML={{ __html: article }} />
      </div>
      <div dangerouslySetInnerHTML={{ __html: controls }} />
    </article>
  );
};
