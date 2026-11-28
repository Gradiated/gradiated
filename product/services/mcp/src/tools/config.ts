import type { OperationId } from "@gradiated/api/generated/operation-ids.js";

// Argument descriptions come from the OpenAPI document; the config only shapes arguments.
export interface ArgumentConfig {
  name?: string;
  // A hidden argument is not offered to the model; with a value, it is always sent.
  hidden?: true;
  value?: unknown;
  // For a field the API accepts in place of another, such as a task name for a content_ref.
  required?: true;
}

export type ToolConfig =
  | { enabled: false; reason: string }
  | {
      enabled: true;
      name: string;
      title: string;
      // Guidance that names other tools, which the API's own description cannot.
      description?: string;
      // Keyed by the API's path, query or JSON body field name.
      arguments?: Record<string, ArgumentConfig>;
      onlyConfiguredArguments?: true;
      // The component schema the response always has when the response is a union.
      output?: string;
      // Sent to the gateway with an inference key instead of to the management API.
      inference?: true;
    };

const TASK: ArgumentConfig = { name: "task_name" };
const VERSION: ArgumentConfig = { name: "version" };

const CONSOLE = "Console session flow, not a workspace operation.";
const ORGANIZATION =
  "Organization administration; workspace credentials cannot authorize it.";
const CREDENTIALS = "Credential management stays in the console.";
const TRAINING = "Training runs and evaluations are managed in the console.";
const STAFF = "Staff only.";
const UPLOAD = "Needs a direct file upload outside MCP.";
const ARTIFACTS =
  "Publishing grad artifacts belongs to the grad SDKs and the console.";
const DOWNLOAD =
  "Returns a signed download link for a file a model cannot read.";
const INFERENCE = "call_model covers inference.";
const SHARING = "Public report links are shared from the console.";
const PUBLIC_REPORT =
  "Unauthenticated public report link; the version file tools read the same report.";
const EXPLORER =
  "Feeds the console's 3D weight explorer; the per-block summary is not useful to a model.";

export const TOOL_CONFIG: Record<OperationId, ToolConfig> = {
  getCurrentCredential: {
    enabled: true,
    name: "whoami",
    title: "Who am I",
    description:
      "Identifies the connection: the member it acts as, its one workspace, and its organization, whose slug prefixes private model names.",
  },
  listModels: {
    enabled: true,
    name: "list_models",
    title: "List models",
    arguments: { external: { hidden: true } },
    output: "ModelList",
  },
  chatCompletions: {
    enabled: true,
    name: "call_model",
    title: "Call model",
    description:
      "Sends messages to a model and returns its reply. The model is a catalog ID from list_models, or a private task model: <organization slug>/<task> for the task's production version or <organization slug>/<task>/<version> for one version, with the slug from whoami.",
    inference: true,
    onlyConfiguredArguments: true,
    arguments: {
      model: {},
      messages: {},
      max_completion_tokens: {},
      temperature: {},
      top_p: {},
      seed: {},
      stop: {},
      reasoning_effort: {},
      response_format: {},
      stream: { hidden: true, value: false },
    },
  },
  getUsageSummary: { enabled: true, name: "get_usage", title: "Get usage" },
  listGenerations: {
    enabled: true,
    name: "list_generations",
    title: "List generations",
    arguments: { task_id: TASK },
  },
  getGeneration: {
    enabled: true,
    name: "get_generation",
    title: "Get generation",
    description:
      "Gets a generation's stored request and response. Content is stored only for generations captured for a task, so pass the task's name.",
    arguments: {
      task_id: { ...TASK, required: true },
      content_ref: { hidden: true },
    },
  },
  listTasks: { enabled: true, name: "list_tasks", title: "List tasks" },
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
    arguments: { task: TASK },
  },
  listTaskVersions: {
    enabled: true,
    name: "list_task_versions",
    title: "List task versions",
    arguments: { task: TASK },
  },
  getTaskVersion: {
    enabled: true,
    name: "get_task_version",
    title: "Get task version",
    arguments: { task: TASK, version_id: VERSION },
  },
  promoteTaskVersion: {
    enabled: true,
    name: "promote_task_version",
    title: "Promote task version",
    arguments: { task: TASK, version_id: VERSION },
  },
  publishTaskVersion: { enabled: false, reason: ARTIFACTS },
  listProductionChanges: { enabled: false, reason: ARTIFACTS },
  deleteTaskVersion: { enabled: false, reason: ARTIFACTS },
  listTaskVersionFiles: {
    enabled: true,
    name: "list_task_version_files",
    title: "List task version files",
    description:
      "Lists the files delivered with a task version: its training report, report.md, and the data files the report references. Read them with read_task_version_file.",
    arguments: { task: TASK, version_id: VERSION },
  },
  getTaskVersionFileContent: {
    enabled: true,
    name: "read_task_version_file",
    title: "Read task version file",
    arguments: { task: TASK, version_id: VERSION, file_id: { name: "file" } },
  },
  getAdapterConfiguration: {
    enabled: true,
    name: "get_adapter_configuration",
    title: "Get adapter configuration",
  },
  getTaskVersionFileDownload: { enabled: false, reason: DOWNLOAD },
  getAdapterDownload: { enabled: false, reason: DOWNLOAD },
  getTaskVersionShare: { enabled: false, reason: SHARING },
  getSharedReport: { enabled: false, reason: PUBLIC_REPORT },
  getSharedReportFileContent: { enabled: false, reason: PUBLIC_REPORT },
  getSharedReportFileDownload: { enabled: false, reason: PUBLIC_REPORT },
  getAdapterWeights: { enabled: false, reason: EXPLORER },
  getSharedAdapterWeights: { enabled: false, reason: PUBLIC_REPORT },
  getSharedAdapterConfiguration: { enabled: false, reason: PUBLIC_REPORT },
  createTaskVersionFile: { enabled: false, reason: STAFF },
  completeTaskVersionFile: { enabled: false, reason: STAFF },
  deleteTaskVersionFile: { enabled: false, reason: STAFF },
  getEvaluationResults: { enabled: false, reason: TRAINING },
  listTrainingRuns: { enabled: false, reason: TRAINING },
  getTrainingRun: { enabled: false, reason: TRAINING },
  listTrainingRunEvents: { enabled: false, reason: TRAINING },
  startTrainingRun: { enabled: false, reason: TRAINING },
  cancelTrainingRun: { enabled: false, reason: TRAINING },
  createModelUpload: { enabled: false, reason: UPLOAD },
  completeModelUpload: { enabled: false, reason: UPLOAD },
  updateWorkspace: {
    enabled: false,
    reason: "Workspace credentials cannot change their workspace.",
  },
  deleteWorkspace: {
    enabled: false,
    reason: "Workspace credentials cannot archive their workspace.",
  },
  createCredentialInferenceKey: {
    enabled: false,
    reason: "The server calls it so OAuth connections can call models.",
  },
  selectOAuthWorkspace: { enabled: false, reason: CONSOLE },
  listPlaygroundMcpTools: { enabled: false, reason: CONSOLE },
  callPlaygroundMcpTool: { enabled: false, reason: CONSOLE },
  listApiKeys: { enabled: false, reason: CREDENTIALS },
  createApiKey: { enabled: false, reason: CREDENTIALS },
  createPlaygroundCredential: { enabled: false, reason: CREDENTIALS },
  createTrainingToken: { enabled: false, reason: CREDENTIALS },
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
  createMessage: { enabled: false, reason: INFERENCE },
  createResponse: { enabled: false, reason: INFERENCE },
  countMessageTokens: { enabled: false, reason: INFERENCE },
  listInferenceModels: {
    enabled: false,
    reason: "list_models covers the same catalog.",
  },
};
