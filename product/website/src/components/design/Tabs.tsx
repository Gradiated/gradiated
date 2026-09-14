import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties, ReactElement } from "react";

/**
 * A segmented control: one indicator that travels, not one filled button per
 * option.
 *
 * The difference matters for more than motion. Three separately filled cells
 * are three shapes butted together, so applying a radius rounds each of them
 * and the control reads as a row of pills fused at the edges. Here the TRACK
 * carries the shape and the indicator slides inside it, clipped to the track's
 * own corners — so the control is one object at every radius, and the movement
 * says which option was chosen rather than leaving the reader to compare
 * fills.
 *
 * Cells are equal width so the indicator can be positioned arithmetically from
 * the index, with no measuring and nothing to resynchronise when a label's
 * text or the font changes.
 *
 * Controlled if given `value` and `onChange`, uncontrolled otherwise — the
 * reference page needs a working demo without a stateful wrapper around it.
 *
 * BELOW THE WIDE TIER THE SEGMENTED VARIANT IS A SELECT. Equal cells are what
 * make the indicator arithmetic, and equal cells inside 432px are what make
 * "Intent classification" three truncated words — the control's whole premise
 * fails at that width. A native select shows one option at a time, opens the
 * platform's own picker, and needs no room for the choices it is not showing.
 *
 * The QUIET variant keeps its tabs. Its cells are max-content, so short
 * labels take only the room they need — "Python / Node" fits a phone with
 * space to spare, and it is usually nested under a segmented control that has
 * already become a select. Two selects stacked would read as a form.
 *
 * Both are rendered and CSS picks one, rather than measuring the viewport in
 * JS: the choice is a layout question, the stylesheet already knows the tier,
 * and a `display: none` control is out of the accessibility tree too, so a
 * screen reader meets one control rather than two.
 */

export const Tabs = ({
  label,
  onChange,
  options,
  quiet = false,
  value,
}: {
  /** Names the group for a screen reader — "Scheme family", not "Tabs". */
  label: string;
  onChange?: (option: string) => void;
  options: string[];
  /** A rule under the label instead of a block behind it — see nav.css. */
  quiet?: boolean;
  value?: string;
}): ReactElement => {
  const [inner, setInner] = useState(options[0]);
  const listRef = useRef<HTMLDivElement>(null);
  const current = value ?? inner;
  const index = Math.max(0, options.indexOf(current));

  /* The quiet variant's cells are max-content, so its indicator cannot be
     placed arithmetically the way the segmented one is — it has to be
     measured. Kept to that variant: the segmented one has equal cells and
     needs no layout read at all.

     useLayoutEffect so the rule is in position on the frame the tab changes,
     rather than one frame late and visibly catching up. */
  const [bar, setBar] = useState({ left: 0, width: 0 });
  useLayoutEffect(() => {
    if (!quiet) return;
    const list = listRef.current;
    const active = list?.querySelectorAll("button")[index];
    if (!list || !active) return;
    const measure = () =>
      setBar({ left: active.offsetLeft, width: active.offsetWidth });
    measure();
    // Labels change width when the font loads and when the box is resized.
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    return () => observer.disconnect();
  }, [index, quiet, options]);

  const select = (option: string) => {
    setInner(option);
    onChange?.(option);
  };

  /* Arrow keys move between tabs, which is the ARIA pattern for a tablist:
     the group is one tab stop and the arrows choose within it. Focus follows
     selection, so a keyboard reader sees the same panel a mouse reader does. */
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const step =
      event.key === "ArrowRight" || event.key === "ArrowDown"
        ? 1
        : event.key === "ArrowLeft" || event.key === "ArrowUp"
          ? -1
          : 0;
    let next = index;
    if (step !== 0) next = (index + step + options.length) % options.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = options.length - 1;
    else return;

    event.preventDefault();
    select(options[next]);
    listRef.current?.querySelectorAll("button")[next]?.focus();
  };

  return (
    <>
      {/* The same options, the same select() — so whichever control the tier
          shows, the state it drives is identical. Absent entirely for the
          quiet variant rather than hidden: there is no width problem to solve
          there, and nothing should be in the tree that no tier will show. */}
      {quiet ? null : (
      <div className="gr-tabselect">
        <select
          aria-label={label}
          className="gr-tabselect-input"
          onChange={(event) => select(event.target.value)}
          value={current}
        >
          {options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <span aria-hidden className="gr-tabselect-chevron" />
      </div>
      )}

      <div
        aria-label={label}
        className={`gr-tabs${quiet ? " gr-tabs--quiet" : ""}`}
        onKeyDown={onKeyDown}
        ref={listRef}
        role="tablist"
        style={
          {
            "--gr-tabs": options.length,
            "--active": index,
            ...(quiet
              ? { "--bar-w": `${bar.width}px`, "--bar-x": `${bar.left}px` }
              : null),
          } as CSSProperties
        }
      >
        {/* Behind the labels, so the ink flip and the movement are one
            gesture. */}
        <span aria-hidden className="gr-tab-indicator" />
        {options.map((option) => (
          <button
            aria-selected={option === current}
            className="gr-tab"
            key={option}
            onClick={() => select(option)}
            role="tab"
            // One tab stop for the group; the arrows do the rest.
            tabIndex={option === current ? 0 : -1}
            type="button"
          >
            {option}
          </button>
        ))}
      </div>
    </>
  );
};
