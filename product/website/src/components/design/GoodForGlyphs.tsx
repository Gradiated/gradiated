import type { ReactElement } from "react";

/**
 * The spot icons for a model page's good-for tiles: one small line drawing
 * per claim, drawn here rather than embedded — the site redraws its icons
 * from Lucide's grammar (24-box, stroked, currentColor) so they take the
 * theme like any glyph. Nine claims, nine glyphs; models share them where
 * the claims are kin.
 */

const FRAME = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  viewBox: "0 0 24 24",
} as const;

const GLYPHS: Record<string, ReactElement> = {
  /** A terminal mid-command: the agent typing for itself. */
  terminal: (
    <svg {...FRAME}>
      <rect height="16" rx="2.5" width="20" x="2" y="4" />
      <path d="m6.5 9.5 3 2.5-3 2.5" />
      <path d="M12.5 15h5" />
    </svg>
  ),
  /** A long document, the middle line running past its fellows. */
  context: (
    <svg {...FRAME}>
      <path d="M5 5h11" />
      <path d="M5 9.5h14" />
      <path d="M5 14.5h14" />
      <path d="M5 19h8" />
    </svg>
  ),
  /** A speech bubble holding a line of thought. */
  chat: (
    <svg {...FRAME}>
      <path d="M21 14.5a2.5 2.5 0 0 1-2.5 2.5H9l-5 4V6.5A2.5 2.5 0 0 1 6.5 4h12A2.5 2.5 0 0 1 21 6.5Z" />
      <path d="M8 10.5h8" />
    </svg>
  ),
  /** One node reaching two tools: the agent and its hands. */
  agents: (
    <svg {...FRAME}>
      <circle cx="12" cy="6" r="2.6" />
      <circle cx="5.5" cy="18" r="2.6" />
      <circle cx="18.5" cy="18" r="2.6" />
      <path d="M10.7 8.3 6.8 15.7" />
      <path d="m13.3 8.3 3.9 7.4" />
    </svg>
  ),
  /** A loop that keeps going round: work that runs itself. */
  automation: (
    <svg {...FRAME}>
      <path d="M20 12a8 8 0 1 1-2.3-5.6" />
      <path d="M18 2.5v4h-4" />
    </svg>
  ),
  /** A gauge well into its sweep: volume at speed. */
  throughput: (
    <svg {...FRAME}>
      <path d="M4 17a9 9 0 1 1 16 0" />
      <path d="m12 15 5-5" />
    </svg>
  ),
  /** One line in, a chosen branch out. */
  routing: (
    <svg {...FRAME}>
      <path d="M3 12h6" />
      <path d="M9 12c3 0 3-5 6-5h5" />
      <path d="M9 12c3 0 3 5 6 5h5" />
      <path d="m17.5 4.5 2.5 2.5-2.5 2.5" />
    </svg>
  ),
  /** A shield with its check: the gate that holds. */
  guardrails: (
    <svg {...FRAME}>
      <path d="M12 21c-5-2-8-5.5-8-10V6l8-3 8 3v5c0 4.5-3 8-8 10Z" />
      <path d="m8.8 11.5 2.3 2.3 4.1-4.1" />
    </svg>
  ),
  /** Three marks on a scale: the rubric, scored. */
  scoring: (
    <svg {...FRAME}>
      <path d="M5 20V10" />
      <path d="M12 20V4" />
      <path d="M19 20v-8" />
      <path d="M3 20h18" />
    </svg>
  ),
};

export type GoodForGlyphName = keyof typeof GLYPHS & string;

export const GoodForGlyph = ({
  name,
}: {
  name: GoodForGlyphName;
}): ReactElement | null => GLYPHS[name] ?? null;
