import type { ComponentType } from "react";
import BrandContent from "./handbook/brand.mdx";
import CompensationContent from "./handbook/compensation.mdx";
import FeedbackContent from "./handbook/feedback.mdx";
import GoToMarketContent from "./handbook/getting-out-the-gate.mdx";
import HiringContent from "./handbook/hiring.mdx";
import InPersonContent from "./handbook/in-person.mdx";
import MissionContent from "./handbook/mission.mdx";
import OnboardingContent from "./handbook/onboarding.mdx";
import PrioritiesContent from "./handbook/priorities.mdx";
import ProductContent from "./handbook/product.mdx";
import SequencingContent from "./handbook/sequencing-and-depth.mdx";
import ShareOptionsContent from "./handbook/share-options.mdx";
import SideGigsContent from "./handbook/side-gigs.mdx";
import SpendingCompanyMoneyContent from "./handbook/spending-company-money.mdx";
import ValuesContent from "./handbook/values.mdx";
import PeopleContent from "./handbook/what-we-look-for.mdx";
import WorkingWithPostHogContent from "./handbook/working-with-posthog.mdx";

export type HandbookSlug =
  | "mission"
  | "product"
  | "sequencing-and-depth"
  | "priorities"
  | "in-person"
  | "what-we-look-for"
  | "spending-company-money"
  | "hiring"
  | "onboarding"
  | "compensation"
  | "share-options"
  | "feedback"
  | "side-gigs"
  | "getting-out-the-gate"
  | "values"
  | "brand"
  | "working-with-posthog";

export type HandbookPageDefinition = {
  Content: ComponentType<{ components?: Record<string, unknown> }>;
  description: string;
  pageTitle: string;
  section: string;
  slug: HandbookSlug;
  title: string;
};

export const handbookPages: HandbookPageDefinition[] = [
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
    slug: "hiring",
    section: "People",
    title: "Hiring",
    pageTitle: "Hiring",
    description: "How Gradiated hires.",
    Content: HiringContent,
  },
  {
    slug: "onboarding",
    section: "People",
    title: "Onboarding",
    pageTitle: "Onboarding",
    description: "How new people start at Gradiated.",
    Content: OnboardingContent,
  },
  {
    slug: "compensation",
    section: "People",
    title: "Compensation",
    pageTitle: "Compensation",
    description: "How Gradiated sets pay.",
    Content: CompensationContent,
  },
  {
    slug: "share-options",
    section: "People",
    title: "Share options",
    pageTitle: "Share options",
    description: "How share options work for Gradiated people.",
    Content: ShareOptionsContent,
  },
  {
    slug: "feedback",
    section: "People",
    title: "Feedback",
    pageTitle: "Feedback",
    description: "How Gradiated gives and receives feedback.",
    Content: FeedbackContent,
  },
  {
    slug: "side-gigs",
    section: "People",
    title: "Side gigs",
    pageTitle: "Side gigs",
    description: "How Gradiated thinks about side gigs and side projects.",
    Content: SideGigsContent,
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

const handbookSectionOrder: Array<{
  artSlug: HandbookSlug;
  label: string;
  slugs: HandbookSlug[];
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
    artSlug: "in-person",
    label: "People",
    slugs: [
      "hiring",
      "onboarding",
      "compensation",
      "share-options",
      "feedback",
      "side-gigs",
    ],
  },
  {
    artSlug: "getting-out-the-gate",
    label: "Going to market",
    slugs: ["getting-out-the-gate", "brand"],
  },
];

export const handbookSections = handbookSectionOrder.map((section) => ({
  artSlug: section.artSlug,
  label: section.label,
  pages: section.slugs.map((slug) =>
    handbookPages.find((page) => page.slug === slug)!,
  ),
}));
