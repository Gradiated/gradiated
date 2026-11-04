import type { HttpBindings } from "@hono/node-server";

import type {
  CatalogBillingService,
  MemberService,
  OrganizationService,
  UsageService,
  TraceService,
  TrainingService,
  WaitlistService,
  WorkspaceApiKeyService,
} from "@gradiated/control";

import type { BillingPaymentsService } from "./billing/payments.js";
import type { ApiAnalytics } from "./analytics.js";

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  emailVerified: boolean;
  isStaff: boolean;
  impersonatedBy?: string | null;
  impersonationExpiresAt?: Date | null;
  image: string | null;
  createdAt: Date;
}

export interface ApiEnvironment {
  Bindings: Partial<HttpBindings>;
  Variables: {
    requestId: string;
    analytics?: ApiAnalytics;
    resolveUser: () => Promise<SessionUser | null>;
    sessionUser?: SessionUser;
    logResourceIds?: { workspace_id?: string; api_key_id?: string };
  };
}

export interface AuthService {
  handler(request: Request): Promise<Response>;
  resolveSession(headers: Headers): Promise<SessionUser | null>;
}

export interface ApiServices {
  waitlist: Pick<WaitlistService, "join">;
  billingPayments: BillingPaymentsService;
  catalogBilling: Pick<
    CatalogBillingService,
    | "listModels"
    | "getBillingAccount"
    | "getManagedBillingAccount"
    | "listBalanceTransactions"
    | "updateAutoTopUp"
    | "topUpStatus"
  >;
  organizations: Pick<
    OrganizationService,
    "listForUser" | "createForUser" | "updateForUser"
  >;
  members: MemberService;
  usage: UsageService;
  traces: TraceService;
  training: TrainingService;
  workspaces: WorkspaceApiKeyService;
}
