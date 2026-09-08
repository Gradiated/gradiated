import type { ComponentType } from "react";
import BrandContent from "./method/brand.mdx";
import GoToMarketContent from "./method/getting-out-the-gate.mdx";
import InPersonContent from "./method/in-person.mdx";
import MissionContent from "./method/mission.mdx";
import ProductContent from "./method/product.mdx";
import SequencingContent from "./method/sequencing-and-depth.mdx";
import ValuesContent from "./method/values.mdx";
import PeopleContent from "./method/what-we-look-for.mdx";

export type MethodSlug =
  | "mission"
  | "product"
  | "sequencing-and-depth"
  | "in-person"
  | "what-we-look-for"
  | "getting-out-the-gate"
  | "values"
  | "brand";

export type MethodPageDefinition = {
  Content: ComponentType;
  description: string;
  indexDescription: string;
  pageTitle: string;
  section: string;
  slug: MethodSlug;
  title: string;
};

export const methodPages: MethodPageDefinition[] = [
  {
    slug: "mission",
    section: "Mission",
    title: "Affordable and open intelligence",
    pageTitle: "Mission",
    description: "The mission of Gradiated.",
    indexDescription: "More intelligence for less energy, open to everyone.",
    Content: MissionContent,
  },
  {
    slug: "product",
    section: "Product",
    title: "What we’re building",
    pageTitle: "What we’re building",
    description: "What Gradiated is building and who it is for.",
    indexDescription: "Inference for long-running work.",
    Content: ProductContent,
  },
  {
    slug: "sequencing-and-depth",
    section: "Product",
    title: "Sequencing and depth",
    pageTitle: "Sequencing and depth",
    description: "How Gradiated sequences product development and goes deep.",
    indexDescription: "Start in software. Go down the stack.",
    Content: SequencingContent,
  },
  {
    slug: "in-person",
    section: "People",
    title: "In person",
    pageTitle: "In person",
    description: "Why Gradiated works in person.",
    indexDescription: "Hard problems benefit from shared context.",
    Content: InPersonContent,
  },
  {
    slug: "what-we-look-for",
    section: "People",
    title: "What we look for",
    pageTitle: "What we look for",
    description: "What Gradiated looks for in people.",
    indexDescription: "Agency, optimism, and exceptional ability.",
    Content: PeopleContent,
  },
  {
    slug: "getting-out-the-gate",
    section: "Go to market",
    title: "Getting out the gate",
    pageTitle: "Getting out the gate",
    description: "How Gradiated gets out the gate.",
    indexDescription: "Win the first users by being meaningfully better.",
    Content: GoToMarketContent,
  },
  {
    slug: "values",
    section: "Values",
    title: "Values",
    pageTitle: "Values",
    description: "The values of Gradiated.",
    indexDescription: "Figure it out. Do the hard thing. Primitive first.",
    Content: ValuesContent,
  },
  {
    slug: "brand",
    section: "Market",
    title: "Brand",
    pageTitle: "Brand",
    description: "The Gradiated brand principles.",
    indexDescription: "Everything is considered.",
    Content: BrandContent,
  },
];

export const methodSections = methodPages.reduce<
  Array<{ label: string; pages: MethodPageDefinition[] }>
>((sections, page) => {
  const current = sections.at(-1);
  if (current?.label === page.section) current.pages.push(page);
  else sections.push({ label: page.section, pages: [page] });
  return sections;
}, []);
