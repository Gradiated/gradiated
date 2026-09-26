import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/**
 * The value proposition, on its own fold (new-homepage-layout, fold 2).
 *
 * The hero states the claim; this fold explains the mechanism, and the
 * explanation STREAMS in — each word sharpens from a blur, autoplaying
 * once the fold enters view. The base-URL line stands alone at the end.
 */

const SENTENCES = [
  "We turn your traces into an RL environment, build the evals, and post-train an open model automatically.",
  "You just change your base URL.",
];

export const ValueFold = (): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const words = Array.from(host.querySelectorAll<HTMLElement>(".gr-value-word"));
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      words.forEach((w) => w.classList.add("gr-value-word--on"));
      return;
    }
    let played = false;
    const timers: number[] = [];
    const seen = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting || played) return;
        played = true;
        words.forEach((w, i) => {
          timers.push(
            window.setTimeout(() => w.classList.add("gr-value-word--on"), 300 + i * 85),
          );
        });
      },
      { threshold: 0.55 },
    );
    seen.observe(host);
    return () => {
      seen.disconnect();
      timers.forEach(clearTimeout);
    };
  }, []);

  return (
    <div className="gr-value" ref={hostRef}>
      <div className="gr-value-stage">
        <p className="gr-value-text">
          {SENTENCES.map((sentence, si) => (
            <span className="gr-value-sentence" key={si}>
              {sentence.split(" ").map((word, wi) => (
                <span className="gr-value-word" key={wi}>
                  {word}{" "}
                </span>
              ))}
            </span>
          ))}
        </p>
      </div>
    </div>
  );
};
