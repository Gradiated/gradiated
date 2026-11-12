export interface ArgumentConfig {
  // The tool argument name; defaults to the API field name.
  name?: string;
  description?: string;
}

export type ToolConfig =
  | { enabled: false; reason: string }
  | {
      enabled: true;
      name: string;
      title: string;
      // Replaces the OpenAPI summary and description.
      description?: string;
      // Keyed by the API's path, query or JSON body field name.
      arguments?: Record<string, ArgumentConfig>;
    };

const TASK: ArgumentConfig = {
  name: "task_name",
  description:
    "The task's name, as sent in the capture header or shown in the console.",
};

const VERSION: ArgumentConfig = {
  description: "A version ID from list_task_versions.",
};

const RUN: ArgumentConfig = {
  description: "A training run ID from list_training_runs.",
};

const TIME_RANGE: Record<string, ArgumentConfig> = {
  from: { description: "Start of the period, as an RFC 3339 timestamp." },
  to: { description: "End of the period, as an RFC 3339 timestamp." },
};

const CONSOLE = "Console session flow, not a workspace operation.";
const ORGANIZATION =
  "Organization administration; workspace API keys cannot authorize it.";
const CREDENTIALS = "Credential management stays in the console.";
const INFERENCE = "Inference goes to the gateway, not through MCP.";
const UPLOAD = "Needs a direct file upload outside MCP.";

// Every operation in the API's OpenAPI document has an entry; a test fails when one is missing.
export const TOOL_CONFIG: Record<string, ToolConfig> = {
  listModels: {
    enabled: true,
    name: "list_models",
    title: "List models",
    description:
      "Lists the hosted models this workspace can call, with prices, context lengths and supported parameters.",
    arguments: {
      external: {
        name: "external_catalog",
        description:
          'Set to "true" for estimated prices of supported external models instead of hosted ones.',
      },
    },
  },
  getUsageSummary: {
    enabled: true,
    name: "get_usage",
    title: "Get usage",
    description:
      "Gets the workspace's inference usage and spend over a period, by model and API key.",
    arguments: TIME_RANGE,
  },
  listGenerations: {
    enabled: true,
    name: "list_generations",
    title: "List generations",
    description:
      "Lists the workspace's inference requests, newest first unless sorted by cost. Page with the returned cursor.",
    arguments: {
      ...TIME_RANGE,
      cursor: { description: "The next_cursor from the previous page." },
      limit: { description: "Generations per page, up to 100." },
      api_key_id: { description: "Only requests made with this API key." },
      model: { description: "Only requests to this exact model ID." },
      search: { description: "Text to search for in request metadata." },
      task_id: {
        name: "task_name",
        description:
          "Only requests captured for this task. With it, results come from captured traces.",
      },
    },
  },
  getGeneration: {
    enabled: true,
    name: "get_generation",
    title: "Get generation",
    description: "Gets one inference request with its prompt and response.",
    arguments: {
      generation_id: { description: "A generation ID from list_generations." },
      content_ref: {
        description:
          "The content_ref returned with the generation by list_generations.",
      },
    },
  },
  listTasks: {
    enabled: true,
    name: "list_tasks",
    title: "List tasks",
    description:
      "Lists the workspace's tasks with their latest training run and production version.",
  },
  getTask: {
    enabled: true,
    name: "get_task",
    title: "Get task",
    arguments: { task: TASK },
  },
  updateTask: {
    enabled: true,
    name: "update_task",
    title: "Update task",
    description:
      "Changes a task's base model, comparison model, judge model or training schedule. Omitted settings are unchanged.",
    arguments: {
      task: TASK,
      base_model_id: {
        description: "The base model ID to train, from list_models.",
      },
      comparison_model_id: {
        description:
          "The model ID evaluations compare trained versions against.",
      },
      judge_model_id: { description: "The model ID that judges evaluations." },
    },
  },
  listTaskVersions: {
    enabled: true,
    name: "list_task_versions",
    title: "List task versions",
    arguments: { task: TASK },
  },
  getEvaluationResults: {
    enabled: true,
    name: "get_evaluation_results",
    title: "Get evaluation results",
    description:
      "Gets a task version's held-out evaluation: the answers and the judge's decisions against the comparison model.",
    arguments: { task: TASK, version_id: VERSION },
  },
  promoteTaskVersion: {
    enabled: true,
    name: "promote_task_version",
    title: "Promote task version",
    description:
      "Makes a trained version serve the task's production model name.",
    arguments: { task: TASK, version_id: VERSION },
  },
  getAdapterDownload: {
    enabled: false,
    reason: "Returns a signed download link for a file a model cannot use.",
  },
  listTaskVersionFiles: { enabled: false, reason: "Not yet exposed." },
  getTaskVersionFileContent: { enabled: false, reason: "Not yet exposed." },
  getTaskVersionFileDownload: {
    enabled: false,
    reason: "Returns a signed download link for a file a model cannot use.",
  },
  createTaskVersionFile: { enabled: false, reason: "Staff only." },
  completeTaskVersionFile: { enabled: false, reason: "Staff only." },
  deleteTaskVersionFile: { enabled: false, reason: "Staff only." },
  listTrainingRuns: {
    enabled: true,
    name: "list_training_runs",
    title: "List training runs",
    arguments: {
      task_id: { description: "Only runs for this task ID, from list_tasks." },
    },
  },
  getTrainingRun: {
    enabled: true,
    name: "get_training_run",
    title: "Get training run",
    arguments: { run_id: RUN },
  },
  listTrainingRunEvents: {
    enabled: true,
    name: "list_training_run_events",
    title: "List training run events",
    arguments: {
      run_id: RUN,
      after: { description: "Only events after this sequence number." },
      limit: { description: "Events per page, up to 1000." },
    },
  },
  startTrainingRun: {
    enabled: true,
    name: "start_training_run",
    title: "Start training run",
    description:
      "Starts training a new version of a task from its captured data. Training is billed to the organization.",
    arguments: {
      task_id: { description: "The task ID to train, from list_tasks." },
    },
  },
  cancelTrainingRun: {
    enabled: true,
    name: "cancel_training_run",
    title: "Cancel training run",
    arguments: { run_id: RUN },
  },
  getAdapterConfiguration: {
    enabled: true,
    name: "get_adapter_configuration",
    title: "Get adapter configuration",
    description:
      "Gets the base checkpoint dimensions an uploaded LoRA adapter must match.",
    arguments: {
      model_id: { description: "A base model ID from list_models." },
    },
  },
  createModelUpload: { enabled: false, reason: UPLOAD },
  completeModelUpload: { enabled: false, reason: UPLOAD },
  updateWorkspace: {
    enabled: false,
    reason: "Workspace keys cannot change their workspace.",
  },
  deleteWorkspace: {
    enabled: false,
    reason: "Workspace keys cannot archive their workspace.",
  },
  getCurrentApiKey: {
    enabled: false,
    reason: "The server calls it to find the key's workspace.",
  },
  listApiKeys: { enabled: false, reason: CREDENTIALS },
  createApiKey: { enabled: false, reason: CREDENTIALS },
  createPlaygroundCredential: { enabled: false, reason: CREDENTIALS },
  revokeApiKey: { enabled: false, reason: CREDENTIALS },
  getBillingAccount: { enabled: false, reason: ORGANIZATION },
  updateBillingAccount: { enabled: false, reason: ORGANIZATION },
  createPaymentMethodSession: { enabled: false, reason: CONSOLE },
  createCardSetup: { enabled: false, reason: CONSOLE },
  saveCard: { enabled: false, reason: CONSOLE },
  listBalanceTransactions: { enabled: false, reason: ORGANIZATION },
  createTopUp: { enabled: false, reason: CONSOLE },
  getCurrentUser: { enabled: false, reason: CONSOLE },
  startImpersonation: { enabled: false, reason: CONSOLE },
  stopImpersonation: { enabled: false, reason: CONSOLE },
  updateOrganization: { enabled: false, reason: ORGANIZATION },
  listStaffOrganizations: { enabled: false, reason: CONSOLE },
  createStaffOrganization: { enabled: false, reason: CONSOLE },
  getStaffOrganization: { enabled: false, reason: CONSOLE },
  createOrganization: { enabled: false, reason: ORGANIZATION },
  listMembers: { enabled: false, reason: ORGANIZATION },
  updateMember: { enabled: false, reason: ORGANIZATION },
  removeMember: { enabled: false, reason: ORGANIZATION },
  listInvitations: { enabled: false, reason: ORGANIZATION },
  createInvitations: { enabled: false, reason: ORGANIZATION },
  resendInvitation: { enabled: false, reason: ORGANIZATION },
  revokeInvitation: { enabled: false, reason: ORGANIZATION },
  previewInvitation: { enabled: false, reason: CONSOLE },
  acceptInvitation: { enabled: false, reason: CONSOLE },
  createNdaDocument: { enabled: false, reason: CONSOLE },
  getNdaDocument: { enabled: false, reason: CONSOLE },
  createNdaSigningSession: { enabled: false, reason: CONSOLE },
  getGithubInstallations: { enabled: false, reason: CONSOLE },
  createSlackInvitation: { enabled: false, reason: CONSOLE },
  getEngineerOnboarding: { enabled: false, reason: CONSOLE },
  submitEngineerOnboarding: { enabled: false, reason: CONSOLE },
  listWorkspaces: { enabled: false, reason: ORGANIZATION },
  createWorkspace: { enabled: false, reason: ORGANIZATION },
  systemOne: { enabled: false, reason: INFERENCE },
  chatCompletions: { enabled: false, reason: INFERENCE },
  createMessage: { enabled: false, reason: INFERENCE },
  createResponse: { enabled: false, reason: INFERENCE },
  countMessageTokens: { enabled: false, reason: INFERENCE },
  listInferenceModels: {
    enabled: false,
    reason: "list_models covers the same catalog.",
  },
};
