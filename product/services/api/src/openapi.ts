import { createApp, openApiDocument, type AppDependencies } from "./app.js";
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
  metrics: new ApiMetrics({ collectProcessMetrics: false }),
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
      listBalanceTransactions: unserved(
        "catalogBilling.listBalanceTransactions",
      ),
    },
    organizations: {
      listForUser: unserved("organizations.listForUser"),
      createForUser: unserved("organizations.createForUser"),
    },
    usage: {
      getSummary: unserved("usage.getSummary"),
      listGenerations: unserved("usage.listGenerations"),
    },
    workspaces: {
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
  createApp(unservedDependencies()).getOpenAPI31Document(openApiDocument);
