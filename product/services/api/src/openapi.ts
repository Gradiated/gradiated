import {
  createApp,
  publicOpenApiDocument,
  type AppDependencies,
} from "./app.js";
import { ApiMetrics } from "./metrics.js";

const unserved = (name: string) => (): never => {
  throw new Error(`${name} is not served by this app`);
};

export const unservedDependencies = (): AppDependencies => ({
  allowedOrigins: [],
  auth: {
    handler: unserved("auth.handler"),
    resolveSession: unserved("auth.resolveSession"),
  },
  checkDependencies: unserved("checkDependencies"),
  consoleUrl: "https://console.gradiated.com",
  metrics: new ApiMetrics({ collectProcessMetrics: false }),
  sendInvitation: unserved("sendInvitation"),
  sendWaitlistWelcome: unserved("sendWaitlistWelcome"),
  services: {
    waitlist: { join: unserved("waitlist.join") },
    billingPayments: {
      createTopUpCheckout: unserved("billingPayments.createTopUpCheckout"),
      handleWebhook: unserved("billingPayments.handleWebhook"),
    },
    catalogBilling: {
      listModels: unserved("catalogBilling.listModels"),
      getBillingAccount: unserved("catalogBilling.getBillingAccount"),
      getManagedBillingAccount: unserved(
        "catalogBilling.getManagedBillingAccount",
      ),
      listBalanceTransactions: unserved(
        "catalogBilling.listBalanceTransactions",
      ),
    },
    members: {
      listMembers: unserved("members.listMembers"),
      updateMember: unserved("members.updateMember"),
      removeMember: unserved("members.removeMember"),
      listInvitations: unserved("members.listInvitations"),
      createInvitations: unserved("members.createInvitations"),
      resendInvitation: unserved("members.resendInvitation"),
      revokeInvitation: unserved("members.revokeInvitation"),
      previewInvitation: unserved("members.previewInvitation"),
      acceptInvitation: unserved("members.acceptInvitation"),
    },
    organizations: {
      listForUser: unserved("organizations.listForUser"),
      updateForUser: unserved("organizations.updateForUser"),
      createForUser: unserved("organizations.createForUser"),
    },
    traces: {
      list: unserved("traces.list"),
      content: unserved("traces.content"),
    },
    training: {
      startRun: unserved("training.startRun"),
      cancelRun: unserved("training.cancelRun"),
      listTasks: unserved("training.listTasks"),
      getTask: unserved("training.getTask"),
      updateTask: unserved("training.updateTask"),
      listRuns: unserved("training.listRuns"),
      getRun: unserved("training.getRun"),
      listRunEvents: unserved("training.listRunEvents"),
      listVersions: unserved("training.listVersions"),
      evaluationResults: unserved("training.evaluationResults"),
      downloadAdapter: unserved("training.downloadAdapter"),
      promote: unserved("training.promote"),
    },
    usage: {
      getSummary: unserved("usage.getSummary"),
      listGenerations: unserved("usage.listGenerations"),
    },
    workspaces: {
      updateWorkspace: unserved("workspaces.updateWorkspace"),
      archiveWorkspace: unserved("workspaces.archiveWorkspace"),
      listWorkspaces: unserved("workspaces.listWorkspaces"),
      createWorkspace: unserved("workspaces.createWorkspace"),
      listApiKeys: unserved("workspaces.listApiKeys"),
      createApiKey: unserved("workspaces.createApiKey"),
      revokeApiKey: unserved("workspaces.revokeApiKey"),
    },
  },
});

type OpenApiDocument = ReturnType<
  ReturnType<typeof createApp>["getOpenAPI31Document"]
>;

export const createOpenApiDocument = (): OpenApiDocument =>
  publicOpenApiDocument(createApp(unservedDependencies()));
