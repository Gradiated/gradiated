import { jobs } from "./careers";

export type PageMetadata = {
  description: string;
  title: string;
};

export const formatPageTitle = (title: string): string =>
  `${title} | Gradiated`;

const pageMetadata: Record<string, PageMetadata> = {
  "/": {
    title: "Home",
    description:
      "Gradiated builds software and hardware that makes open-model inference more efficient.",
  },
  "/products/": {
    title: "Products",
    description:
      "Explore Gradiated products for efficient open-model inference.",
  },
  "/library/": {
    title: "Library",
    description:
      "Read Gradiated research notes and learn how we work across inference software and hardware.",
  },
  "/careers/": {
    title: "Careers",
    description:
      "Explore open roles in inference software and silicon at Gradiated.",
  },
  "/notes/": {
    title: "Notes",
    description:
      "Read Gradiated notes about inference research, systems, hardware, and company building.",
  },
  "/notes/our-thesis/": {
    title: "Thesis",
    description:
      "Read why Gradiated believes inference should be a choice, not a constraint.",
  },
  "/notes/working-with-us/": {
    title: "Working with us",
    description:
      "Learn how Gradiated works and what we look for in founding engineers.",
  },
  "/library/handbook/brand/": {
    title: "Brand",
    description: "Read the principles that define the Gradiated brand.",
  },
  "/library/handbook/values/": {
    title: "Values",
    description: "Read the values that guide how Gradiated works.",
  },
  "/docs/": {
    title: "Docs",
    description: "Learn how to use the Gradiated API for open-model inference.",
  },
  "/docs/quickstart/": {
    title: "Use Gradiated",
    description:
      "Create an API key and send your first inference request to Gradiated.",
  },
  "/docs/models-pricing/": {
    title: "Models and pricing",
    description:
      "Compare the models, prices, and capabilities available through Gradiated.",
  },
  "/docs/api-keys/": {
    title: "API keys and workspaces",
    description: "Create and manage Gradiated API keys and workspaces.",
  },
  "/docs/migrate/": {
    title: "Migrate to Gradiated",
    description:
      "Move an existing OpenAI-compatible application to the Gradiated API.",
  },
  "/docs/openai-sdk/": {
    title: "OpenAI SDK",
    description: "Use the OpenAI SDK with the Gradiated API.",
  },
  "/docs/anthropic-sdk/": {
    title: "Anthropic SDK",
    description: "Use the Anthropic SDK with the Gradiated API.",
  },
  "/docs/service-tiers/": {
    title: "Service tiers",
    description:
      "Choose a Gradiated service tier for your latency and cost requirements.",
  },
  "/docs/streaming/": {
    title: "Streaming",
    description: "Stream inference responses from the Gradiated API.",
  },
  "/docs/tool-calling/": {
    title: "Tool calling",
    description: "Use model tool calls through the Gradiated API.",
  },
  "/docs/parameters/": {
    title: "Parameters and model support",
    description:
      "Review the request parameters and model behavior that Gradiated supports.",
  },
  "/docs/errors/": {
    title: "Errors, limits, and retries",
    description: "Handle Gradiated API errors, limits, and retries.",
  },
  "/docs/usage/": {
    title: "Usage and request logs",
    description: "Review inference usage and request logs in Gradiated.",
  },
  "/docs/billing/": {
    title: "Billing and credits",
    description: "Manage Gradiated billing, credits, and usage costs.",
  },
  "/docs/opencode/": {
    title: "OpenCode",
    description: "Connect OpenCode to the Gradiated API.",
  },
  "/docs/codex/": {
    title: "Codex",
    description: "Connect Codex to the Gradiated API.",
  },
  "/docs/claude-code/": {
    title: "Claude Code",
    description: "Connect Claude Code to the Gradiated API.",
  },
  "/docs/api-reference/": {
    title: "API reference",
    description:
      "Review Gradiated API endpoints, request fields, and response formats.",
  },
  "/privacy/": {
    title: "Privacy",
    description:
      "Read how Gradiated collects, uses, stores, and protects personal data.",
  },
  "/terms/": {
    title: "Terms",
    description: "Read the terms that govern use of Gradiated services.",
  },
  "/acceptable-use/": {
    title: "Acceptable use",
    description: "Read the rules for acceptable use of Gradiated services.",
  },
  "/dpa/": {
    title: "DPA",
    description: "Read the Gradiated data processing agreement.",
  },
  "/subprocessors-security/": {
    title: "Security",
    description: "Review Gradiated security practices and subprocessors.",
  },
};

const notFoundMetadata: PageMetadata = {
  title: "Page not found",
  description:
    "The requested page does not exist. Find another page on the Gradiated website.",
};

const normalizePath = (pathname: string): string => {
  if (pathname === "/") return pathname;
  return pathname.endsWith("/") ? pathname : `${pathname}/`;
};

export const getPageMetadata = (pathname: string): PageMetadata => {
  const normalizedPath = normalizePath(pathname);
  const exactMetadata = pageMetadata[normalizedPath];
  if (exactMetadata) return exactMetadata;

  const job = jobs.find(({ slug }) => normalizedPath === `/careers/${slug}/`);
  if (job) {
    return { title: job.title, description: job.summary };
  }

  if (normalizedPath.startsWith("/products/")) {
    return pageMetadata["/products/"];
  }

  return notFoundMetadata;
};
