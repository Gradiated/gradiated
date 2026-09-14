import { useEffect, useState } from "react";
import type { CSSProperties, ReactElement } from "react";

/**
 * The chip, and what is inside it.
 *
 * At rest this is one photograph of a package. On hover the layers it is made
 * of fan out from behind it — underfill, metal, die, substrate, solder — and
 * the casing stays put on top, so the gesture reads as looking INTO the object
 * rather than as five pictures being shuffled.
 *
 * The layers drop STRAIGHT DOWN, in the order they physically sit. A cross
 * section is what this is, and a cross section reads vertically — fanning them
 * sideways made the reader rebuild the stacking order themselves. It also
 * gives the hero a tall, narrow object to put a column of type beside.
 *
 * It opens itself, once, shortly after it arrives, and stays open. The closed
 * state is a chip; the open one is the argument, so waiting for a hover would
 * mean most readers never see the point being made.
 */

/** Deepest first, so the DOM paints them in the order they physically sit. */
const LAYERS = [
  { file: "6-solder-balls", name: "Solder balls" },
  { file: "5-substrate", name: "Substrate" },
  { file: "4-silicon-die", name: "Silicon die" },
  { file: "3-metal-layer", name: "Metal layer" },
  { file: "2-underfill", name: "Underfill" },
] as const;

export const ChipStack = (): ReactElement => {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    /* Reduced motion gets the opened state with no travel: the information is
       in the layers being visible, not in the moving. */
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setOpen(true);
      return;
    }
    /* Next frame, not on a timer. The WAIT lives in CSS, as a transition delay
       measured off the same token the chip's own entrance uses — so the two
       cannot drift apart if either is retimed. This only has to give the
       transition a frame to start from rather than collapsing it into the
       initial render. */
    const frame = requestAnimationFrame(() => setOpen(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
  <div className={`gr-chipstack${open ? " gr-chipstack--open" : ""}`}>
    {/* The layers are placed against THIS box, not the outer one. The outer
        box reserves the room the opened stack hangs into, and anything
        positioned against it would have its centre moved by that reservation
        — the chip would drift as the drop distance changed. */}
    <div className="gr-chipstack-frame">
    {/* First in the DOM but lifted over the rest, because it is the only
        layer that does not move and everything else emerges from under it. */}
    <img
      alt="A Gradiated inference package, shown from above."
      className="gr-chipstack-casing"
      height={887}
      src="/brand/hardware/chip/1-casing.webp"
      width={900}
    />

    {LAYERS.map((layer, index) => (
      <img
        alt=""
        className="gr-chipstack-layer"
        height={686}
        key={layer.file}
        /* Decorative until the fan opens, and never the thing a reader is
           waiting on — the casing above is what has to arrive with the fold. */
        loading="lazy"
        src={`/brand/hardware/chip/${layer.file}.webp`}
        style={{ "--layer": LAYERS.length - index } as CSSProperties}
        width={686}
      />
    ))}
    </div>
  </div>
  );
};
