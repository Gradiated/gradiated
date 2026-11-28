import {
  clientOpenApiDocument,
  createApp,
  publicOpenApiDocument,
  type AppDependencies,
  type OpenApiDocument,
} from "./app.js";
import { ApiMetrics } from "./metrics.js";

const unserved = (name: string) => (): never => {
  throw new Error(`${name} is not served by this app`);
};

export const unservedDependencies = (): AppDependencies => ({
  allowedOrigins: [],
  auth: {
    handler: unserved("auth.handler"),
    authorizationServerMetadata: unserved("auth.authorizationServerMetadata"),
    resolveSession: unserved("auth.resolveSession"),
    signTrainingToken: unserved("auth.signTrainingToken"),
    signServiceToken: unserved("auth.signServiceToken"),
  },
  checkDependencies: unserved("checkDependencies"),
  consoleUrl: "https://console.gradiated.com",
  metrics: new ApiMetrics({ collectProcessMetrics: false }),
  sendInvitation: unserved("sendInvitation"),
  sendWaitlistWelcome: unserved("sendWaitlistWelcome"),
  notifyEngineerOnboarding: unserved("notifyEngineerOnboarding"),
  services: {
    waitlist: { join: unserved("waitlist.join") },
    billingPayments: {
      createTopUp: unserved("billingPayments.createTopUp"),
      createPaymentMethodSession: unserved(
        "billingPayments.createPaymentMethodSession",
      ),
      createCardSetup: unserved("billingPayments.createCardSetup"),
      saveCard: unserved("billingPayments.saveCard"),
      describeCard: unserved("billingPayments.describeCard"),
      handleWebhook: unserved("billingPayments.handleWebhook"),
    },
    catalogBilling: {
      listModels: unserved("catalogBilling.listModels"),
      getBillingAccount: unserved("catalogBilling.getBillingAccount"),
      topUpStatus: unserved("catalogBilling.topUpStatus"),
      getManagedBillingAccount: unserved(
        "catalogBilling.getManagedBillingAccount",
      ),
      listBalanceTransactions: unserved(
        "catalogBilling.listBalanceTransactions",
      ),
      updateAutoTopUp: unserved("catalogBilling.updateAutoTopUp"),
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
      getOnboarding: unserved("organizations.getOnboarding"),
      recordOnboardingNda: unserved("organizations.recordOnboardingNda"),
      submitOnboarding: unserved("organizations.submitOnboarding"),
      claimOnboardingSubmission: unserved(
        "organizations.claimOnboardingSubmission",
      ),
      releaseOnboardingSubmission: unserved(
        "organizations.releaseOnboardingSubmission",
      ),
      resetOnboardingSubmission: unserved(
        "organizations.resetOnboardingSubmission",
      ),
    },
    integrations: {
      list: unserved("integrations.list"),
      findSlackChannel: unserved("integrations.findSlackChannel"),
      recordSlackChannel: unserved("integrations.recordSlackChannel"),
      claimSlackInvitation: unserved("integrations.claimSlackInvitation"),
      releaseSlackInvitation: unserved("integrations.releaseSlackInvitation"),
      activate: unserved("integrations.activate"),
      revoke: unserved("integrations.revoke"),
      recordGithubInstallation: unserved(
        "integrations.recordGithubInstallation",
      ),
    },
    traces: {
      list: unserved("traces.list"),
      content: unserved("traces.content"),
    },
    training: {
      uploads: {
        configuration: unserved("training.uploads.configuration"),
        create: unserved("training.uploads.create"),
        complete: unserved("training.uploads.complete"),
      },
      files: {
        list: unserved("training.files.list"),
        create: unserved("training.files.create"),
        complete: unserved("training.files.complete"),
        content: unserved("training.files.content"),
        download: unserved("training.files.download"),
        remove: unserved("training.files.remove"),
      },
      artifacts: {
        publish: unserved("training.artifacts.publish"),
        publishAsService: unserved("training.artifacts.publishAsService"),
        deleteVersion: unserved("training.artifacts.deleteVersion"),
        releasePendingPins: unserved("training.artifacts.releasePendingPins"),
      },
      shares: {
        get: unserved("training.shares.get"),
        shared: unserved("training.shares.shared"),
        sharedContent: unserved("training.shares.sharedContent"),
        sharedDownload: unserved("training.shares.sharedDownload"),
      },
      startRun: unserved("training.startRun"),
      cancelRun: unserved("training.cancelRun"),
      listTasks: unserved("training.listTasks"),
      getTask: unserved("training.getTask"),
      updateTask: unserved("training.updateTask"),
      listRuns: unserved("training.listRuns"),
      getRun: unserved("training.getRun"),
      listRunEvents: unserved("training.listRunEvents"),
      listVersions: unserved("training.listVersions"),
      getVersion: unserved("training.getVersion"),
      listProductionChanges: unserved("training.listProductionChanges"),
      evaluationResults: unserved("training.evaluationResults"),
      downloadAdapter: unserved("training.downloadAdapter"),
      adapterWeights: unserved("training.adapterWeights"),
      sharedAdapterWeights: unserved("training.sharedAdapterWeights"),
      sharedAdapterConfiguration: unserved(
        "training.sharedAdapterConfiguration",
      ),
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
      createPlaygroundCredential: unserved(
        "workspaces.createPlaygroundCredential",
      ),
      revokeApiKey: unserved("workspaces.revokeApiKey"),
      authenticateCredential: unserved("workspaces.authenticateCredential"),
      describeCredential: unserved("workspaces.describeCredential"),
      createOAuthInferenceCredential: unserved(
        "workspaces.createOAuthInferenceCredential",
      ),
      selectOAuthWorkspace: unserved("workspaces.selectOAuthWorkspace"),
      requirePlaygroundAccess: unserved("workspaces.requirePlaygroundAccess"),
      describeTrainingMember: unserved("workspaces.describeTrainingMember"),
    },
  },
});

export const createOpenApiDocuments = (): {
  public: OpenApiDocument;
  client: OpenApiDocument;
} => {
  const app = createApp(unservedDependencies());

  return {
    public: publicOpenApiDocument(app),
    client: clientOpenApiDocument(app),
  };
};

export const createOpenApiDocument = (): OpenApiDocument =>
  createOpenApiDocuments().public;
