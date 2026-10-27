import type { ComponentType } from "react";
import BrandContent from "./method/brand.mdx";
import GoToMarketContent from "./method/getting-out-the-gate.mdx";
import InPersonContent from "./method/in-person.mdx";
import MissionContent from "./method/mission.mdx";
import PrioritiesContent from "./method/priorities.mdx";
import ProductContent from "./method/product.mdx";
import SequencingContent from "./method/sequencing-and-depth.mdx";
import SpendingCompanyMoneyContent from "./method/spending-company-money.mdx";
import ValuesContent from "./method/values.mdx";
import PeopleContent from "./method/what-we-look-for.mdx";
import WorkingWithPostHogContent from "./method/working-with-posthog.mdx";

export type MethodSlug =
  | "mission"
  | "product"
  | "sequencing-and-depth"
  | "priorities"
  | "in-person"
  | "what-we-look-for"
  | "spending-company-money"
  | "getting-out-the-gate"
  | "values"
  | "brand"
  | "working-with-posthog";

export type MethodPageDefinition = {
  Content: ComponentType<{ components?: Record<string, unknown> }>;
  description: string;
  pageTitle: string;
  section: string;
  slug: MethodSlug;
  title: string;
};

export const methodPages: MethodPageDefinition[] = [
  {
    slug: "mission",
    section: "Foundations",
    title: "Affordable and open intelligence",
    pageTitle: "Mission",
    description: "The mission of Gradiated.",
    Content: MissionContent,
  },
  {
    slug: "product",
    section: "Product and engineering",
    title: "What we’re building",
    pageTitle: "What we’re building",
    description: "What Gradiated is building and who it is for.",
    Content: ProductContent,
  },
  {
    slug: "sequencing-and-depth",
    section: "Product and engineering",
    title: "Sequencing and depth",
    pageTitle: "Sequencing and depth",
    description: "How Gradiated sequences product development and goes deep.",
    Content: SequencingContent,
  },
  {
    slug: "priorities",
    section: "Product and engineering",
    title: "Priorities",
    pageTitle: "Priorities",
    description: "How Gradiated prioritizes engineering changes.",
    Content: PrioritiesContent,
  },
  {
    slug: "in-person",
    section: "How we work",
    title: "In person",
    pageTitle: "In person",
    description: "Why Gradiated works in person.",
    Content: InPersonContent,
  },
  {
    slug: "what-we-look-for",
    section: "How we work",
    title: "What we look for",
    pageTitle: "What we look for",
    description: "What Gradiated looks for in people.",
    Content: PeopleContent,
  },
  {
    slug: "working-with-posthog",
    section: "How we work",
    title: "Working with PostHog",
    pageTitle: "Working with PostHog",
    description: "How Gradiated and PostHog work together.",
    Content: WorkingWithPostHogContent,
  },
  {
    slug: "spending-company-money",
    section: "How we work",
    title: "Spending company money",
    pageTitle: "Spending company money",
    description: "How Gradiated handles expenses and company spending.",
    Content: SpendingCompanyMoneyContent,
  },
  {
    slug: "getting-out-the-gate",
    section: "Going to market",
    title: "Getting out the gate",
    pageTitle: "Getting out the gate",
    description: "How Gradiated gets out the gate.",
    Content: GoToMarketContent,
  },
  {
    slug: "values",
    section: "Foundations",
    title: "Values",
    pageTitle: "Values",
    description: "The values of Gradiated.",
    Content: ValuesContent,
  },
  {
    slug: "brand",
    section: "Going to market",
    title: "Brand",
    pageTitle: "Brand",
    description: "The Gradiated brand principles.",
    Content: BrandContent,
  },
];

const methodSectionOrder: Array<{
  artSlug: MethodSlug;
  label: string;
  slugs: MethodSlug[];
}> = [
  {
    artSlug: "mission",
    label: "Foundations",
    slugs: ["mission", "values"],
  },
  {
    artSlug: "sequencing-and-depth",
    label: "Product and engineering",
    slugs: ["product", "sequencing-and-depth", "priorities"],
  },
  {
    artSlug: "in-person",
    label: "How we work",
    slugs: [
      "in-person",
      "what-we-look-for",
      "working-with-posthog",
      "spending-company-money",
    ],
  },
  {
    artSlug: "getting-out-the-gate",
    label: "Going to market",
    slugs: ["getting-out-the-gate", "brand"],
  },
];

export const methodSections = methodSectionOrder.map((section) => ({
  artSlug: section.artSlug,
  label: section.label,
  pages: section.slugs.map((slug) =>
    methodPages.find((page) => page.slug === slug)!,
  ),
}));
