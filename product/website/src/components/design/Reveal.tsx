import { Fragment, useEffect, useRef, useState } from "react";
import type { CSSProperties, ElementType, ReactElement } from "react";

/**
 * Text that resolves out of a blur in pieces rather than as one block.
 *
 * `by="word"` staggers a word at a time — for titles, where each word is worth
 * landing on. `by="line"` staggers a line at a time, which suits body copy:
 * word-staggering a paragraph reads as a teleprinter, and the reader is left
 * chasing the text instead of receiving it.
 *
 * Both modes share one mechanism. The text is always split into words; the
 * only difference is what index drives the delay. Lines cannot be known ahead
 * of layout — they depend on the measure, the font and the viewport — so line
 * mode renders the words, reads back which ones share a vertical position, and
 * assigns each the index of the line it landed on. Re-measured on resize,
 * because a narrower column re-breaks the lines.
 */

type RevealProps = {
  /** Word for titles, line for body copy. */
  by: "line" | "word";
  children: string;
  className?: string;
  /** The element to render. Defaults to a span so it inherits its context. */
  as?: ElementType;
  /**
   * What delay index this piece of text starts counting from.
   *
   * For a heading split across several Reveals because the author chose where
   * it breaks: each one counts its words from zero, so a two-line title would
   * animate its two lines in lockstep — word one of both lines together, then
   * word two of both — which reads as a block fade rather than a reveal. The
   * caller carries the running total across the lines so the stagger is
   * continuous over the whole heading.
   */
  from?: number;
};

export const Reveal = ({
  as: Tag = "span",
  by,
  children,
  className,
  from = 0,
}: RevealProps): ReactElement => {
  const hostRef = useRef<HTMLElement>(null);
  const words = children.split(/\s+/).filter(Boolean);
  /** Per-word delay index: the word's own position, or its line's. */
  const [lineOf, setLineOf] = useState<number[] | null>(null);

  useEffect(() => {
    if (by !== "line") return;
    const host = hostRef.current;
    if (!host) return;

    const measure = () => {
      const parts = [...host.querySelectorAll<HTMLElement>(".gr-split-part")];
      let line = -1;
      let previousTop = Number.NaN;
      const indices = parts.map((part) => {
        // offsetTop is stable per line box; a new value means a new line.
        if (part.offsetTop !== previousTop) {
          previousTop = part.offsetTop;
          line += 1;
        }
        return line;
      });
      setLineOf((current) =>
        current !== null &&
        current.length === indices.length &&
        current.every((value, i) => value === indices[i])
          ? current
          : indices,
      );
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(host);
    return () => observer.disconnect();
  }, [by, children]);

  return (
    <Tag
      className={["gr-split", `gr-split--${by}`, className]
        .filter(Boolean)
        .join(" ")}
      ref={hostRef}
    >
      {words.map((word, index) => (
        <Fragment key={`${word}-${index}`}>
          <span
            className="gr-split-part"
            style={
              {
                "--i": from + (lineOf ? lineOf[index] : index),
              } as CSSProperties
            }
          >
            {word}
          </span>
          {index < words.length - 1 ? " " : null}
        </Fragment>
      ))}
    </Tag>
  );
};
