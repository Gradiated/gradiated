import { memo, useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import { SectionFab } from "../../design";
import { SandCircuitArtwork } from "../../design/SandCircuitArtwork";
import article, {
  contents,
} from "../../../../content/articles/sand/script.md?sand-article";
import "./journey.css";

const stage = `<svg id="stage-svg" viewBox="0 0 440 440" aria-hidden="true">\n          <defs>\n            <clipPath id="crop"><rect id="crop-rect" x="0" y="0" width="440" height="440" /></clipPath>\n            <filter id="wobble" x="-10%" y="-10%" width="120%" height="120%">\n              <feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="7" result="n" />\n              <feDisplacementMap in="SourceGraphic" in2="n" scale="2.4" xChannelSelector="R" yChannelSelector="G" />\n            </filter>\n          </defs>\n          <g id="art">\n            <ellipse id="shadow" />\n            <path id="mesh" />\n            <g id="parts" clip-path="url(#crop)"></g>\n            <g id="d2"></g>\n          </g>\n        </svg>`;
const controls = `<details class="panel" hidden>\n    <summary>tweak</summary>\n    <label><span>spin</span><input type="range" data-ctl="spin" min="0" max="1.5" step="0.01" value="0.45" /></label>\n    <label><span>elevation</span><input type="range" data-ctl="elev" min="0" max="45" step="1" value="18" /></label>\n    <label><span>line</span><input type="range" data-ctl="weight" min="0.8" max="3" step="0.1" value="1.8" /></label>\n    <label><span>hold</span><input type="range" data-ctl="hold" min="0" max="0.45" step="0.01" value="0.18" /></label>\n    <label><span>light</span><input type="range" data-ctl="light" min="0" max="360" step="1" value="135" /></label>\n    <label class="check"><input type="checkbox" data-ctl="hatch" checked /><span>hatching</span></label>\n    <label class="check"><input type="checkbox" data-ctl="wobble" /><span>hand-drawn wobble</span></label>\n    <label class="check"><input type="checkbox" data-ctl="mesh" /><span>show mesh</span></label>\n    <output id="readout"></output>\n  </details>`;

// The animation mutates this markup, so contents updates must preserve its nodes.
const SandMarkup = memo(
  ({ className, html }: { className: string; html: string }) => (
    <div className={className} dangerouslySetInnerHTML={{ __html: html }} />
  ),
);

const introductionEnd = article.indexOf("</header>") + "</header>".length;
const introduction = article.slice(0, introductionEnd);
const body = article.slice(introductionEnd);
const chapters = [
  { id: "sand-introduction", label: "Introduction" },
  ...contents,
];

export const SandJourney = (): ReactElement => {
  const hostRef = useRef<HTMLElement>(null);
  const [active, setActive] = useState(chapters[0].id);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    let cleanup = () => {};
    void import("./runtime/main.js").then(({ mountSandScenes }) => {
      if (disposed) return;

      cleanup = mountSandScenes(host);
      host.dataset.animationReady = "true";
      const target = document.getElementById(window.location.hash.slice(1));
      if (target && host.contains(target)) {
        target.scrollIntoView({ behavior: "instant", block: "start" });
      }
    });

    return () => {
      disposed = true;
      cleanup();
    };
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let frame = 0;
    const measure = () => {
      frame = 0;
      const line = window.innerHeight * (window.innerWidth <= 640 ? 0.72 : 0.5);
      let current = chapters[0].id;

      chapters.forEach(({ id }) => {
        const target = host.querySelector<HTMLElement>(`#${id}`);
        if (!target) return;

        if (target.getBoundingClientRect().top <= line + 2) current = id;
      });
      setActive(current);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };

    measure();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, []);

  return (
    <article className="sand-journey" ref={hostRef}>
      <div className="sand-layout">
        <aside className="sand-side gr-doc-side">
          <nav aria-label="Guide contents" className="gr-doc-nav">
            <div className="gr-doc-nav-group">
              <p className="gr-doc-nav-heading gr-label">Sand to Thought</p>
              {chapters.map(({ id, label }) => (
                <a
                  aria-current={active === id ? "location" : undefined}
                  className="gr-doc-nav-link"
                  href={`#${id}`}
                  key={id}
                >
                  {label}
                </a>
              ))}
            </div>
          </nav>
        </aside>
        <SectionFab label="Guide contents">
          {chapters.map(({ id, label }) => (
            <a
              aria-current={active === id ? "location" : undefined}
              className="gr-fab-link"
              href={`#${id}`}
              key={id}
            >
              {label}
            </a>
          ))}
        </SectionFab>
        <div className="sand-main">
          <figure
            aria-label="Sand grains form a dune and rearrange into a logic circuit on hover or keyboard focus."
            className="sand-cover"
            tabIndex={0}
          >
            <SandCircuitArtwork />
          </figure>
          <SandMarkup className="sand-intro" html={introduction} />
          <div className="post">
            <div className="stage-col">
              <SandMarkup className="stage" html={stage} />
            </div>
            <SandMarkup className="prose" html={body} />
          </div>
        </div>
      </div>
      <SandMarkup className="sand-controls" html={controls} />
    </article>
  );
};
