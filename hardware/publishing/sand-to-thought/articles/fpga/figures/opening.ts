import type { Bit, Rule } from "./model";

export type MapHighlight = "blank" | "io" | "logic" | "tracks" | "junctions";

type OpeningView =
  | { highlight: MapHighlight; title: string }
  | { rule: Rule; inputs: readonly [Bit, Bit]; title: string };

export const openingViews = {
  reconfigure: {
    highlight: "blank",
    title:
      "A simplified FPGA map before we choose a user circuit. Nine logic blocks, available routing tracks and sixteen I/O blocks have no assigned function or signal values.",
  },
  "map-io": {
    highlight: "io",
    title:
      "The I/O blocks and package pins are highlighted. These connect the internal circuit to equipment outside the chip; general-purpose pins can be configured to receive, send or do both at different times.",
  },
  "map-logic": {
    highlight: "logic",
    title:
      "The nine configurable logic blocks are highlighted. Stored settings choose their functions; several blocks can work at the same time.",
  },
  "map-routing": {
    highlight: "tracks",
    title:
      "The available routing tracks are highlighted. They carry signals between blocks and I/O; this highlight does not mean that all tracks are connected together.",
  },
  "map-junctions": {
    highlight: "junctions",
    title:
      "Outlined routing junctions represent groups of configurable switches and selectors that choose paths between existing wire segments. A crossing alone is not a connection.",
  },
  "first-circuit": {
    rule: "AND",
    inputs: [1, 1],
    title:
      "Our first configured circuit follows two input paths through the upper-left CLB to an output. With AND stored, A = 1 and B = 1 produce output 1.",
  },
  "input-change": {
    rule: "AND",
    inputs: [1, 0],
    title:
      "The AND rule and routing stay fixed. B changes from 1 to 0. With A = 1, the output becomes 0.",
  },
  "rule-change": {
    rule: "OR",
    inputs: [1, 0],
    title:
      "The same paths and input values remain, but the stored rule changes from AND to OR. With A = 1 and B = 0, the output becomes 1.",
  },
} as const satisfies Record<string, OpeningView>;

export const openingSceneKeys = Object.keys(
  openingViews,
) as (keyof typeof openingViews)[];

export const openingViewFor = (scene: string): OpeningView => {
  if (!Object.hasOwn(openingViews, scene)) {
    throw new Error(`Missing FPGA opening view for ${scene}`);
  }

  return openingViews[scene as keyof typeof openingViews];
};
