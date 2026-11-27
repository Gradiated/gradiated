import { jobs } from "./careers";
import { handbookPages } from "./handbook";
import { models } from "./models";
import { papers } from "./papers";
import { articles, authorOf } from "./articles";
import { team } from "./team";

export const siteOrigin = "https://gradiated.com";

export type PageKind = "article" | "documentation" | "job" | "website";

export type PageMetadata = {
  author?: string;
  authorTitle?: string;
  description: string;
  image: string;
  index: boolean;
  kind: PageKind;
  publishedAt?: string;
  updatedAt?: string;
  title: string;
};

type PageMetadataContent = Pick<PageMetadata, "description" | "title"> & {
  index?: boolean;
};

export const formatPageTitle = (title: string): string =>
  `${title} | Gradiated`;

const pageMetadata: Record<string, PageMetadataContent> = {
  "/": {
    title: "Run open models",
    description:
      "Gradiated trains a router for your workload, using open models where they meet your quality requirements and frontier models where they’re needed.",
  },
  "/about/": {
    title: "About",
    description:
      "Learn how Gradiated began inside PostHog and why PostHog created a dedicated brand for inference research and infrastructure.",
  },
  "/team/": {
    title: "Team",
    description:
      "Meet the people at Gradiated: who they are, what they are working on, and where in the world they are based.",
  },
  ...Object.fromEntries(
    team.map((member) => [
      member.path,
      {
        title: member.name,
        description: `${member.name} is ${member.role} at Gradiated.${
          member.summary ? ` ${member.summary}` : ""
        }`,
      },
    ]),
  ),
  "/training/": {
    title: "Training",
    description:
      "Automatically fine-tune open models for better quality, speed, and cost.",
  },
  "/inference/": {
    title: "Inference",
    description:
      "Open-model inference priced for the latency your workload requires.",
  },
  "/hardware/": {
    title: "Hardware",
    description:
      "Inference hardware designed for efficient, long-running cloud workloads.",
  },
  "/artwork-generator/": {
    title: "Artwork generator",
    description: "Create Gradiated wafer-field artwork from a motif or image.",
    index: false,
  },
  "/library/sand-to-thought/": {
    title: "Sand to Thought",
    description:
      "Explore the semiconductor stack through an illustrated journey from silicon to computers and deeper articles about how chips are made.",
  },
  "/library/": {
    title: "Library",
    description:
      "The Gradiated magazine: interactive journeys, essays, and films on how machine intelligence gets made, from sand to thought.",
  },
  "/design/": {
    title: "Design system",
    description:
      "The Gradiated design system: palette, roles, spacing, layout, type, and components, rendered live from the site's own tokens.",
    index: false,
  },
  "/style/": {
    title: "Style guide",
    description: "The Gradiated brand style guide.",
    index: false,
  },
  "/careers/": {
    title: "Careers",
    description:
      "Join Gradiated to make open-model inference more efficient across models, software, systems, and silicon.",
  },
  "/handbook/": {
    title: "Handbook",
    description:
      "How Gradiated works, makes decisions, and builds the company.",
  },
  ...Object.fromEntries(
    handbookPages.map((page) => [
      `/handbook/${page.slug}/`,
      { title: page.pageTitle, description: page.description },
    ]),
  ),
  "/models/": {
    title: "Models",
    description:
      "The open models Gradiated serves and post-trains: catalogue, benchmarks, and pricing.",
  },
  ...Object.fromEntries(
    models.map((model) => [
      `/models/${model.slug}/`,
      {
        title: `${model.name} on Gradiated`,
        description: model.oneLiner,
      },
    ]),
  ),
  "/papers/": {
    title: "Paper reproductions",
    description:
      "Reproduce landmark post-training papers (SDFT, DAPO, Cartridges, RouteLLM) on public datasets in one click or one grad CLI command.",
  },
  ...Object.fromEntries(
    papers.map((paper) => [
      `/papers/${paper.slug}/`,
      {
        title: `${paper.shortTitle} reproduction on Gradiated`,
        description: `${paper.title} (arXiv:${paper.arxivId}) in ${paper.linesOfCode} lines of grad. ${paper.oneLiner}`,
      },
    ]),
  ),
  "/docs/": {
    title: "Developer docs",
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
  "/docs/openai-sdk/": {
    title: "OpenAI SDK",
    description: "Use the OpenAI SDK with the Gradiated API.",
  },
  "/docs/anthropic-sdk/": {
    title: "Anthropic SDK",
    description: "Use the Anthropic SDK with the Gradiated API.",
  },
  "/docs/systemone-sdk/": {
    title: "SystemOne SDK",
    description:
      "Use linden-1 with the TypeSafe SystemOne SDK on Gradiated. Copy Python, Node, and cURL examples for choices, probabilities, and scores.",
  },
  "/docs/service-tiers/": {
    title: "Service tiers",
    description:
      "Choose a Gradiated service tier for your latency and cost requirements.",
  },
  "/docs/errors/": {
    title: "Errors, limits, and retries",
    description: "Handle Gradiated API errors, limits, and retries.",
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
  "/docs/training/": {
    title: "Training overview",
    description:
      "Train routers, decision models, and fine-tuned models from your production logs or test environments.",
  },
  "/docs/training/trajectories/": {
    title: "Trajectories",
    description:
      "Store production logs, labeled examples, and agent runs in a Gradiated Dataset from files, code, or observability tools.",
  },
  "/docs/training/recipes/": {
    title: "Training recipes",
    description:
      "Pick a recipe, check the cost with a dry run, and train routers, decision models, fine-tunes, cartridges and embedding models.",
  },
  "/docs/training/rubrics/": {
    title: "Rubrics",
    description:
      "Score model outputs with Python checks, validators, or an LLM judge.",
  },
  "/docs/training/environments/": {
    title: "Environments",
    description:
      "Run your agent against your own tools, databases, Harbor tasks, or Docker containers during reinforcement learning.",
  },
  "/docs/training/evaluations/": {
    title: "Evaluations",
    description:
      "Compare base models and trained artifacts side by side on the same dataset and Rubric before you ship.",
  },
  "/docs/training/artifacts/": {
    title: "Artifacts",
    description:
      "Inspect, download, and deploy versioned .grad model artifacts saved by training runs.",
  },
  "/docs/training/deploying/": {
    title: "Deploying",
    description:
      "Host trained artifacts on Gradiated Cloud, or download standard weights to run on your own vLLM or SGLang servers.",
  },
  "/docs/training/models/": {
    title: "Supported training models",
    description:
      "See which base models you can fine-tune, what each size is best at, and how token-based training billing works.",
  },
  "/docs/training/custom-loops/": {
    title: "Custom training loops",
    description:
      "Write your own Python training loop on Gradiated Trainer and Artifact when a built-in recipe isn't flexible enough.",
  },
  "/docs/training/advanced-objectives/": {
    title: "Advanced objectives",
    description:
      "Custom PyTorch losses and specialized training patterns built on Trainer and CustomLoss.",
  },
  "/docs/training/tuning-troubleshooting/": {
    title: "Tuning & troubleshooting",
    description:
      "Practical defaults for learning rates, LoRA rank, spend caps, crash recovery, and fixing common SFT and DPO failure modes.",
  },
  "/docs/training/self-hosting/": {
    title: "Self-hosting grad",
    description:
      "Run Gradiated on your laptop with Docker Compose or in your own Kubernetes cluster with Helm.",
  },
  "/docs/training/recipes/router/": {
    title: "Model router guide",
    description:
      "Send each request to the cheapest model that still meets your quality bar.",
  },
  "/docs/training/recipes/decision-model/": {
    title: "Decision models guide",
    description:
      "Train your own fast decision model for categories, yes/no checks, or ordered ratings.",
  },
  "/docs/training/recipes/sft/": {
    title: "Supervised fine-tuning (SFT) guide",
    description:
      "Fine-tune an open model on examples of the exact outputs you want with SFTRecipe.",
  },
  "/docs/training/recipes/dpo/": {
    title: "Preference tuning (DPO) guide",
    description:
      "Teach a model which answers you prefer using pairs of good and bad examples with DPORecipe.",
  },
  "/docs/training/recipes/rl-agents/": {
    title: "RL for agents guide",
    description:
      "Train a model with reinforcement learning by grading its answers with code or another model.",
  },
  "/docs/training/recipes/traces-to-environments/": {
    title: "Traces to environments guide",
    description:
      "Turn existing production logs into an RL environment, starting simple and adding containers only when you need them.",
  },
  "/docs/training/recipes/distillation/": {
    title: "Model distillation guide",
    description:
      "Train a small, fast model to copy a larger one using your own prompts with DistillRecipe.",
  },
  "/docs/training/recipes/cartridges/": {
    title: "Context Cartridges guide",
    description:
      "Turn a long, repeated prompt or doc set into a small add-on you don't have to resend on every request.",
  },
  "/docs/training/recipes/reward-models/": {
    title: "Reward models guide",
    description:
      "Train a small model to score how good another model's answers are with RewardModelRecipe.",
  },
  "/docs/training/recipes/embeddings/": {
    title: "Embeddings guide",
    description:
      "Fine-tune an embedding model on your own docs and codebase for better search.",
  },
  "/docs/training/integrations/": {
    title: "Trace integrations",
    description:
      "Sync traces, scores and corrections from Langfuse, LangSmith, Braintrust, PostHog, Arize Phoenix or the Gradiated gateway into versioned datasets.",
  },
  "/docs/training/integrations/langfuse/": {
    title: "Langfuse integration",
    description:
      "Sync Langfuse traces and scores into a Gradiated dataset, and send production feedback with Langfuse scores.",
  },
  "/docs/training/integrations/langsmith/": {
    title: "LangSmith integration",
    description:
      "Sync LangSmith runs, feedback and corrections into a Gradiated dataset.",
  },
  "/docs/training/integrations/braintrust/": {
    title: "Braintrust integration",
    description:
      "Sync Braintrust logs, scores and expected answers into a Gradiated dataset.",
  },
  "/docs/training/integrations/posthog/": {
    title: "PostHog integration",
    description:
      "Sync PostHog LLM analytics traces and user feedback into a Gradiated dataset.",
  },
  "/docs/training/integrations/phoenix/": {
    title: "Arize Phoenix integration",
    description:
      "Sync Arize Phoenix (OpenInference) traces and span annotations into a Gradiated dataset.",
  },
  "/docs/api-reference/": {
    title: "API reference",
    description:
      "Review Gradiated API endpoints, request fields, and response formats.",
  },
  "/docs/reference/primitives/": {
    title: "Primitives reference",
    description:
      "Reference for the core objects and JSON schemas used across the Gradiated SDKs and API.",
  },
  "/docs/reference/training-parameters/": {
    title: "Training parameters reference",
    description:
      'Every training setting, its default, and how the "auto" defaults are chosen. You rarely need to set any of them.',
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
  "/sla/": {
    title: "Service Level Agreement",
    description:
      "Read Gradiated’s 99.5% inference uptime commitment, service credits and claims process.",
  },
  "/acceptable-use/": {
    title: "Acceptable use",
    description: "Read the rules for acceptable use of Gradiated services.",
  },
  "/dpa/": {
    title: "DPA",
    description: "Read the Gradiated data processing agreement.",
  },
  "/subprocessors/": {
    title: "Subprocessors",
    description:
      "See the subprocessors that process Gradiated request content, where they process it, and how we announce changes.",
  },
};

const notFoundMetadata: PageMetadataContent = {
  title: "Page not found",
  description:
    "The requested page does not exist. Find another page on the Gradiated website.",
};

const normalizePath = (pathname: string): string => {
  if (pathname === "/") return pathname;
  return pathname.endsWith("/") ? pathname : `${pathname}/`;
};

const defaultImage = "/brand/png/gradiated-mark-dark-1024.png";

const metadataDetailsFor = (
  pathname: string,
): Pick<PageMetadata, "image" | "kind" | "publishedAt"> => {
  if (pathname.startsWith("/docs/")) {
    return { image: defaultImage, kind: "documentation" };
  }
  if (pathname !== "/careers/" && pathname.startsWith("/careers/")) {
    return {
      image: "/assets/editorial/working-with-us-v2.png",
      kind: "job",
      publishedAt: "2026-08-28",
    };
  }
  return { image: defaultImage, kind: "website" };
};

export const getPageMetadata = (pathname: string): PageMetadata => {
  const normalizedPath = normalizePath(pathname);
  const article = articles.find((entry) => entry.path === normalizedPath);
  if (article) {
    return {
      title: article.title,
      description: article.description ?? article.title,
      image: article.image,
      publishedAt: article.publishedAt,
      updatedAt: article.updatedAt,
      author: article.author,
      authorTitle: article.authorTitle ?? authorOf(article)?.role,
      index: article.status === "published",
      kind: "article",
    };
  }
  const exactMetadata = pageMetadata[normalizedPath];
  if (exactMetadata) {
    return {
      ...exactMetadata,
      ...metadataDetailsFor(normalizedPath),
      index: exactMetadata.index ?? true,
    };
  }

  const job = jobs.find(({ slug }) => normalizedPath === `/careers/${slug}/`);
  if (job) {
    return {
      title: job.title,
      description: job.summary,
      image: "/assets/editorial/working-with-us-v2.png",
      index: true,
      kind: "job",
      publishedAt: job.datePosted ?? "2026-08-28",
    };
  }

  return {
    ...notFoundMetadata,
    image: defaultImage,
    index: false,
    kind: "website",
  };
};

export const getIndexablePaths = (): string[] => [
  ...Object.entries(pageMetadata)
    .filter(([, metadata]) => metadata.index !== false)
    .map(([path]) => path),
  ...articles
    .filter((article) => article.status === "published")
    .map((article) => article.path),
  ...jobs.map(({ slug }) => `/careers/${slug}/`),
];

/* Every page that has metadata, indexed or not. The prerender writes a
   static document for each so a noindex page still answers with its
   own title instead of the 404 page. */
export const getAllPagePaths = (): string[] => [
  ...new Set([
    ...Object.keys(pageMetadata),
    ...articles.map((article) => article.path),
    ...jobs.map(({ slug }) => `/careers/${slug}/`),
  ]),
];

export const absoluteUrl = (path: string): string =>
  new URL(path, siteOrigin).toString();

const organization = {
  "@type": "Organization",
  "@id": `${siteOrigin}/#organization`,
  name: "Gradiated",
  url: siteOrigin,
  logo: absoluteUrl(defaultImage),
};

const breadcrumbFor = (pathname: string, title: string): object | null => {
  const parts: Array<{ name: string; path: string }> = [
    { name: "Home", path: "/" },
  ];

  if (pathname.startsWith("/docs/")) {
    parts.push({ name: "Developer docs", path: "/docs/" });
  } else if (pathname.startsWith("/careers/")) {
    parts.push({ name: "Careers", path: "/careers/" });
  } else if (pathname.startsWith("/handbook/")) {
    parts.push({ name: "Handbook", path: "/handbook/" });
  } else if (pathname.startsWith("/team/")) {
    parts.push({ name: "Team", path: "/team/" });
  } else if (pathname.startsWith("/library/")) {
    parts.push({ name: "Library", path: "/library/" });
  } else {
    return null;
  }

  if (parts.at(-1)?.path !== pathname) {
    parts.push({ name: title, path: pathname });
  }

  return {
    "@type": "BreadcrumbList",
    itemListElement: parts.map((part, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: part.name,
      item: absoluteUrl(part.path),
    })),
  };
};

const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const htmlList = (items: string[]): string =>
  `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;

const jobDescription = (job: (typeof jobs)[number]): string =>
  [
    `<p>${escapeHtml(job.summary)}</p>`,
    "<h2>Why this role exists</h2>",
    ...job.purpose.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`),
    "<h2>What you will do</h2>",
    htmlList(job.responsibilities),
    ...(job.problems.length > 0
      ? ["<h2>Problems you may work on</h2>", htmlList(job.problems)]
      : []),
    "<h2>What we are looking for</h2>",
    htmlList(job.requirements),
    "<h2>This role is not for you if</h2>",
    htmlList(job.notFor),
  ].join("");

export const getStructuredData = (pathname: string): object[] => {
  const normalizedPath = normalizePath(pathname);
  const metadata = getPageMetadata(normalizedPath);
  if (!metadata.index) return [];

  const url = absoluteUrl(normalizedPath);
  const data: object[] = [organization];
  const breadcrumb = breadcrumbFor(normalizedPath, metadata.title);
  if (breadcrumb) data.push(breadcrumb);

  const job = jobs.find(({ slug }) => normalizedPath === `/careers/${slug}/`);
  if (job) {
    data.push({
      "@type": "JobPosting",
      title: job.title,
      description: jobDescription(job),
      datePosted: job.datePosted ?? "2026-08-28",
      employmentType: job.employmentType ?? "FULL_TIME",
      hiringOrganization: organization,
      identifier: {
        "@type": "PropertyValue",
        name: "Gradiated",
        value: job.slug,
      },
      jobLocation: job.location.split(",").map((city) => ({
        "@type": "Place",
        address: {
          "@type": "PostalAddress",
          addressCountry: "GB",
          addressLocality: city.trim(),
        },
      })),
      // Google's JobPosting name for a remote role.
      ...(job.workplace === "REMOTE" && {
        jobLocationType: "TELECOMMUTE",
        applicantLocationRequirements: { "@type": "Country", name: "GB" },
      }),
      url,
    });
    return data;
  }

  if (metadata.kind === "article") {
    data.push({
      "@type": "Article",
      headline: metadata.title,
      description: metadata.description,
      datePublished: metadata.publishedAt,
      dateModified: metadata.updatedAt ?? metadata.publishedAt,
      image: absoluteUrl(metadata.image),
      mainEntityOfPage: url,
      author: metadata.author
        ? {
            "@type": "Person",
            name: metadata.author,
            ...(metadata.authorTitle && { jobTitle: metadata.authorTitle }),
          }
        : organization,
      publisher: organization,
    });
    return data;
  }

  if (metadata.kind === "documentation") {
    data.push({
      "@type": "TechArticle",
      headline: metadata.title,
      description: metadata.description,
      mainEntityOfPage: url,
      author: organization,
      publisher: organization,
    });
    return data;
  }

  const member = team.find(({ path }) => path === normalizedPath);
  if (member) {
    data.push({
      "@type": "ProfilePage",
      url,
      mainEntity: {
        "@type": "Person",
        name: member.name,
        jobTitle: member.role,
        worksFor: { "@id": organization["@id"] },
        ...(member.summary && { description: member.summary }),
        ...(member.photo && { image: absoluteUrl(member.photo.src) }),
        ...(member.location && {
          homeLocation: {
            "@type": "Place",
            name: `${member.location.city}, ${member.location.country}`,
          },
        }),
        ...(Object.values(member.links).length > 0 && {
          sameAs: Object.values(member.links),
        }),
      },
    });
    return data;
  }

  if (normalizedPath === "/") {
    data.push({
      "@type": "WebSite",
      "@id": `${siteOrigin}/#website`,
      name: "Gradiated",
      description: metadata.description,
      url: siteOrigin,
      publisher: organization,
    });
  } else {
    data.push({
      "@type": "WebPage",
      name: metadata.title,
      description: metadata.description,
      url,
      isPartOf: { "@id": `${siteOrigin}/#website` },
    });
  }

  return data;
};
