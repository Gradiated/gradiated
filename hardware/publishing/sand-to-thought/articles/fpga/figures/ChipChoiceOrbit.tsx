import { Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties, FocusEvent } from "react";
import { chipChoiceIcons } from "../../../shared/figures/ChipChoiceIcons";
import "./chip-choice-orbit.css";

const chips = [
  {
    name: "FPGA",
    strength:
      "Build a circuit around a model’s arithmetic and choose how much to run in parallel.",
    tradeOff:
      "Design and testing take time. The circuit must fit the chip, and slow weight reads can stall the calculations. Programmable wiring can use extra energy.",
  },
  {
    name: "CPU",
    strength: "Can run inference in software. On our KV260, the CPU chooses the next token.",
    tradeOff: "Usually does less parallel maths per second than a GPU.",
  },
  {
    name: "GPU",
    strength:
      "Runs many of a model’s calculations at once. Grouping requests can keep more computing units busy.",
    tradeOff:
      "Small requests can leave computing units idle. Waiting to group requests can delay a reply.",
  },
  {
    name: "ASIC",
    strength: "A chip built specifically for inference can be fast and energy efficient.",
    tradeOff: "Costs time and money up front. Changing the circuit means making a new chip.",
  },
] as const;

const ComparisonPoint = ({
  kind,
  selected,
}: {
  kind: "strength" | "tradeOff";
  selected: number;
}) => (
  <div className={`fpga-orbit-point fpga-orbit-point--${kind}`}>
    <strong>{kind === "strength" ? "Strengths" : "Trade-offs"}</strong>
    <div className="fpga-orbit-point-copy">
      {chips.map((chip, index) => (
        <p
          key={chip.name}
          aria-hidden={index !== selected}
          data-current={index === selected}
        >
          {chip[kind]}
        </p>
      ))}
    </div>
  </div>
);

export const ChipChoiceOrbit = () => {
  const root = useRef<HTMLElement>(null);
  const [selection, setSelection] = useState({ index: 0, slots: [0, 0, 1, 2] });
  const [visible, setVisible] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [paused, setPaused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [keyboardFocus, setKeyboardFocus] = useState(false);

  useEffect(() => {
    const element = root.current;
    if (!element) return;

    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let intersecting = false;
    const updateVisibility = () => setVisible(intersecting && !document.hidden);
    const updateMotion = () => setReducedMotion(motion.matches);
    const observer = new IntersectionObserver(([entry]) => {
      intersecting = entry.isIntersecting;
      updateVisibility();
    });

    observer.observe(element);
    updateMotion();
    motion.addEventListener("change", updateMotion);
    document.addEventListener("visibilitychange", updateVisibility);

    return () => {
      observer.disconnect();
      motion.removeEventListener("change", updateMotion);
      document.removeEventListener("visibilitychange", updateVisibility);
    };
  }, []);

  const running =
    visible && !reducedMotion && !paused && !hovered && !keyboardFocus;
  const select = (index: number) =>
    setSelection((previous) => {
      if (previous.index === index) return previous;

      const slots = [...previous.slots];
      slots[previous.index] = slots[index];

      return { index, slots };
    });

  useEffect(() => {
    if (!running) return;

    const timer = window.setTimeout(
      () => select((selection.index + 1) % chips.length),
      10_000,
    );

    return () => window.clearTimeout(timer);
  }, [running, selection.index]);

  const handleFocus = (event: FocusEvent<HTMLDivElement>) =>
    setKeyboardFocus(event.target.matches(":focus-visible"));
  const handleBlur = (event: FocusEvent<HTMLDivElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget)) setKeyboardFocus(false);
  };

  return (
    <section
      ref={root}
      className="fpga-chip-orbit"
      aria-label="Chip strengths and trade-offs for inference"
      data-running={running}
    >
      <ComparisonPoint kind="strength" selected={selection.index} />
      <div
        className="fpga-orbit-track"
        role="group"
        aria-label="Choose a chip"
        onPointerEnter={(event) => {
          if (event.pointerType === "mouse") setHovered(true);
        }}
        onPointerLeave={() => setHovered(false)}
        onFocus={handleFocus}
        onBlur={handleBlur}
      >
        <svg
          className="fpga-orbit-guide"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <ellipse cx="50" cy="50" rx="37" ry="36" vectorEffect="non-scaling-stroke" />
        </svg>
        {chips.map(({ name }, index) => {
          const Icon = chipChoiceIcons[name];
          const selected = selection.index === index;

          return (
            <div
              key={name}
              className="fpga-orbit-position"
              data-centred={selected}
              style={{
                "--fpga-chip-slot": `${selection.slots[index] * 120 - 25}deg`,
              } as CSSProperties}
            >
              <button
                type="button"
                className="fpga-orbit-chip"
                aria-pressed={selected}
                onClick={() => select(index)}
              >
                <Icon aria-hidden="true" strokeWidth={1.6} />
                <span>{name}</span>
              </button>
            </div>
          );
        })}
      </div>
      <ComparisonPoint kind="tradeOff" selected={selection.index} />
      <button
        type="button"
        className="fpga-orbit-pause"
        onClick={() => setPaused((previous) => !previous)}
      >
        {paused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />}
        {paused ? "Resume rotation" : "Pause rotation"}
      </button>
    </section>
  );
};
