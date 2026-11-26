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
    id: "linden-1",
    category: "Decision model",
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
    id: "task-routing",
    category: "Model router",
    name: "Linden-2",
    status: "In progress",
    description:
      "Builds on Linden-1 to choose a model for each request. Send routine work to open models and reserve frontier calls for work that needs them.",
  },
  {
    id: "code-review",
    category: "Code review",
    description:
      "Review pull requests for regressions, missed edge cases, and gaps in test coverage.",
  },
  {
    id: "browser-automation",
    category: "Browser automation",
    description:
      "Navigate web apps, interact with page elements, and complete multi-step browser workflows reliably.",
  },
  {
    id: "test-selection",
    category: "Test selection",
    description:
      "Pick the minimal set of tests likely to catch regressions for a given diff.",
  },
  {
    id: "context-compaction",
    category: "Context compaction",
    description:
      "Compress long agent sessions while preserving decisions, constraints, and unfinished work.",
  },
  {
    id: "diff-merging",
    category: "Diff merging",
    description:
      "Reconcile conflicting edits and surface the decisions that still need a human.",
  },
];

export const canSuggestName = (entry: RoadmapEntry): boolean =>
  !entry.name && !entry.release;

export const MODEL_NAME_SUGGESTION_MAX_LENGTH = 600;
