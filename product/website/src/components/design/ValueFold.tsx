import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/**
 * The value proposition, on its own fold (new-homepage-layout, fold 2).
 *
 * The hero states the claim; this fold explains the mechanism, and the
 * explanation STREAMS in — each word sharpens from a blur as the reader
 * scrolls, so the sentence is read at the pace it is revealed. Scrubbed,
 * not timed: scrolling back re-blurs it.
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
    let raf = 0;
    const frame = (): void => {
      raf = requestAnimationFrame(frame);
      const rect = host.getBoundingClientRect();
      const span = rect.height - innerHeight;
      const p = span > 0 ? Math.max(0, Math.min(1, -rect.top / span)) : 1;
      const n = words.length;
      words.forEach((w, i) => {
        /* each word turns on slightly after the previous; the tail of the
           runway holds the finished sentence */
        w.classList.toggle("gr-value-word--on", p * (n + 2) > i + 0.5);
      });
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
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
