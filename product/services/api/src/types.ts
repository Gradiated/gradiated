import type {
  CatalogBillingService,
  OrganizationService,
  WorkspaceApiKeyService,
} from "@gradiated/control";

import type { BillingPaymentsService } from "./billing/stripe.js";

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  emailVerified: boolean;
  image: string | null;
  createdAt: Date;
}

export interface ApiEnvironment {
  Variables: {
    requestId: string;
    user: SessionUser | null;
  };
}

export interface AuthService {
  handler(request: Request): Promise<Response>;
  resolveSession(headers: Headers): Promise<SessionUser | null>;
}

export interface ApiServices {
  billingPayments: BillingPaymentsService;
  catalogBilling: CatalogBillingService;
  organizations: OrganizationService;
  workspaces: WorkspaceApiKeyService;
}
