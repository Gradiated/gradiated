export interface PromptArgument {
  name: string;
  description: string;
  required: boolean;
}

export interface PromptDefinition {
  name: string;
  title: string;
  description: string;
  arguments: PromptArgument[];
  text: (values: Record<string, string>) => string;
}

const TASK: PromptArgument = {
  name: "task_name",
  description: "The task's name, as shown in the console.",
  required: true,
};

const period = (values: Record<string, string>) =>
  values.from && values.to
    ? `from ${values.from} to ${values.to}`
    : "over the last 7 days";

export const PROMPTS: readonly PromptDefinition[] = [
  {
    name: "review_task_version",
    title: "Review a task version",
    description:
      "Reads a trained version's report and data files and says whether it is ready to promote.",
    arguments: [
      TASK,
      {
        name: "version",
        description:
          "The version's name. Without it, the newest version is reviewed.",
        required: false,
      },
    ],
    text: ({ task_name, version }) =>
      [
        `Review ${version ? `version ${version}` : "the newest version"} of the task ${task_name}.`,
        "1. Use get_task and list_task_versions to find the version, the production version and the comparison model.",
        "2. Use list_task_version_files, then read_task_version_file for report.md and the data files it references.",
        "3. Summarize what the version was trained on, how it compares with the comparison model and the production version on quality, cost and speed, and any failure patterns in the samples.",
        "4. Recommend whether to promote it, with the evidence. Do not call promote_task_version unless I confirm.",
      ].join("\n"),
  },
  {
    name: "compare_task_versions",
    title: "Compare two task versions",
    description:
      "Compares two versions of a task from their reports and by calling both on the same prompts.",
    arguments: [
      TASK,
      {
        name: "version_a",
        description: "The first version's name.",
        required: true,
      },
      {
        name: "version_b",
        description: "The second version's name.",
        required: true,
      },
    ],
    text: ({ task_name, version_a, version_b }) =>
      [
        `Compare versions ${version_a} and ${version_b} of the task ${task_name}.`,
        "1. Read each version's report.md with list_task_version_files and read_task_version_file, and compare their reported results.",
        "2. Use whoami for the organization slug. Take three to five recent requests from list_generations with task_name and get_generation, send each to both versions with call_model as <organization slug>/<task>/<version>, and compare the answers.",
        "3. Summarize where each version is better, with examples, and which you would serve.",
      ].join("\n"),
  },
  {
    name: "investigate_failed_generations",
    title: "Investigate failed generations",
    description:
      "Finds the workspace's failed inference requests in a period and groups their causes.",
    arguments: [
      {
        name: "from",
        description: "Start of the period, as an RFC 3339 timestamp.",
        required: false,
      },
      {
        name: "to",
        description: "End of the period, as an RFC 3339 timestamp.",
        required: false,
      },
    ],
    text: (values) =>
      [
        `Investigate failed and cancelled generations ${period(values)}.`,
        "1. Use list_generations with status failed, then cancelled, and page through the results.",
        "2. Group them by model, error code and finish reason, and note when each group started.",
        "3. For captured tasks, read a few examples with get_generation.",
        "4. Summarize the main causes, their share of traffic from get_usage, and what to change.",
      ].join("\n"),
  },
  {
    name: "summarize_usage",
    title: "Summarize usage",
    description: "Summarizes the workspace's inference spend and traffic.",
    arguments: [
      {
        name: "from",
        description: "Start of the period, as an RFC 3339 timestamp.",
        required: false,
      },
      {
        name: "to",
        description: "End of the period, as an RFC 3339 timestamp.",
        required: false,
      },
    ],
    text: (values) =>
      [
        `Summarize this workspace's inference usage ${period(values)} with get_usage.`,
        "Report total spend, requests and tokens, the models that account for most of the spend, and the daily trend. Charges are integer nano-USD; convert them to dollars.",
        "Point out models whose traffic a task's trained version could serve more cheaply, using list_tasks.",
      ].join("\n"),
  },
];
