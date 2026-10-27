import type { StoryArt, StoryCover } from "./components/design";
import type { MethodSlug } from "./method";
import { artworkPresets } from "./lib/artwork";

/* One source of truth for Method artwork. The index, Library cards and any
   future Method surfaces should all pick up the same delivered art and wafer
   fallback. */
export const methodArt: Partial<Record<MethodSlug, StoryArt>> = {
  mission: {
    tall: "/brand/library/mission.webp",
    wide: "/brand/library/mission-wide.webp",
  },
  "sequencing-and-depth": {
    tall: "/brand/library/sequencing.webp",
    wide: "/brand/library/sequencing-wide.webp",
  },
  "in-person": {
    tall: "/brand/library/in-person.webp",
  },
};

export const methodCovers: Record<MethodSlug, StoryCover> = {
  mission: artworkPresets.mission,
  product: artworkPresets.product,
  "sequencing-and-depth": artworkPresets.sequencing,
  priorities: artworkPresets.product,
  "in-person": artworkPresets.people,
  "what-we-look-for": artworkPresets.judgement,
  "working-with-posthog": artworkPresets.people,
  "spending-company-money": artworkPresets.people,
  "getting-out-the-gate": artworkPresets.gate,
  values: artworkPresets.values,
  brand: artworkPresets.brand,
};
