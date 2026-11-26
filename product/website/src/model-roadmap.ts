export type RoadmapEntry = {
  id: string;
  category: string;
  name?: string;
  description: string;
  status?: "In progress";
  release?: {
    date: string;
    links: readonly { label: string; href: string }[];
  };
};

export const roadmapEntries: readonly RoadmapEntry[] = [
  {
    id: "task-routing",
    category: "Model router",
    name: "Linden-2",
    status: "In progress",
    description:
      "Builds on Linden-1 to choose a model for each request. Send routine work to open models and reserve frontier calls for work that needs them.",
  },
  {
    id: "linden-1",
    category: "Model router",
    name: "Linden-1",
    description:
      "An open-weight decision model for tasks like ticket triage. It returns choices, probabilities, or scores from text or structured data.",
    release: {
      date: "2026-11-18",
      links: [
        { label: "API", href: "/docs/systemone-sdk/" },
        { label: "Weights", href: "https://huggingface.co/gradiated/linden-1" },
      ],
    },
  },
  {
    id: "carat",
    category: "Inference engine",
    name: "Carat",
    description:
      "A C++ and CUDA engine for Gemma 4 on NVIDIA Hopper GPUs. In our benchmark it delivered 67% more output tokens per second than SGLang.",
    release: {
      date: "2026-10-07",
      links: [
        { label: "Source", href: "https://github.com/Gradiated/carat" },
        { label: "Benchmark", href: "/library/gemma-inference-engine/" },
      ],
    },
  },
  {
    id: "security-review",
    category: "Security review",
    description:
      "Flag likely vulnerabilities in first-party diffs and point reviewers to the code that needs attention.",
  },
  {
    id: "code-review",
    category: "Code review",
    description:
      "Review pull requests for regressions, missed edge cases, and gaps in test coverage.",
  },
  {
    id: "diff-merging",
    category: "Diff merging",
    description:
      "Reconcile conflicting edits and surface the decisions that still need a human.",
  },
  {
    id: "context-compaction",
    category: "Context compaction",
    description:
      "Compress long agent sessions while preserving decisions, constraints, and unfinished work.",
  },
  {
    id: "ci-triage",
    category: "CI failure triage",
    description:
      "Find the first meaningful failure in noisy CI logs and distinguish flakes from likely regressions.",
  },
  {
    id: "error-triage",
    category: "Production error triage",
    description:
      "Group related errors and use traces, stack frames, and release context to suggest where to look first.",
  },
  {
    id: "product-analytics",
    category: "Product analytics queries",
    description:
      "Turn questions about funnels, retention, and feature adoption into queries against your event schema.",
  },
];

export const canSuggestName = (entry: RoadmapEntry): boolean =>
  !entry.name && !entry.release;

export const MODEL_NAME_SUGGESTION_MAX_LENGTH = 600;
