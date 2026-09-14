import { useEffect, useState } from "react";
import type { ReactElement } from "react";

/**
 * TEMPORARY exploration control — remove with the rest of the reference-page
 * scaffolding.
 *
 * Steps the whole system through the radius scale. Sets --radius on .gr-root,
 * which every component reads, so nothing needs a variant: buttons, fields,
 * tabs, badges, tables and code blocks all follow at once.
 *
 * Circles are unaffected — they set 50% explicitly because they are marks
 * rather than containers, and `full` on a container is a different thing from
 * a circle regardless.
 */

const STEPS = [
  { id: "none", label: "0", token: "--radius-none" },
  { id: "sm", label: "sm", token: "--radius-sm" },
  { id: "md", label: "md", token: "--radius-md" },
  { id: "lg", label: "lg", token: "--radius-lg" },
  { id: "xl", label: "xl", token: "--radius-xl" },
  { id: "2xl", label: "2xl", token: "--radius-2xl" },
  { id: "3xl", label: "3xl", token: "--radius-3xl" },
  { id: "full", label: "full", token: "--radius-full" },
] as const;

export const RadiusSwitcher = (): ReactElement => {
  const [step, setStep] = useState<string>("none");
  const index = STEPS.findIndex(({ id }) => id === step);

  useEffect(() => {
    const root = document.querySelector<HTMLElement>(".gr-root");
    if (!root) return;
    const chosen = STEPS.find(({ id }) => id === step);
    root.style.setProperty("--radius", `var(${chosen?.token ?? "--radius-none"})`);
  }, [step]);

  return (
    <div className="gr-radius-control">
      {/* A range, not eight buttons: the point is to move ALONG the scale and
          watch the system change, which a slider does in one gesture. */}
      <input
        aria-label="Corner radius"
        aria-valuetext={STEPS[index]?.label}
        className="gr-radius-range"
        max={STEPS.length - 1}
        min={0}
        onChange={(event) => setStep(STEPS[Number(event.target.value)].id)}
        step={1}
        type="range"
        value={index}
      />
      <span className="gr-radius-value">{STEPS[index]?.label}</span>
    </div>
  );
};
