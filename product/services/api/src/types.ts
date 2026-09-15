import type {
  CatalogBillingService,
  OrganizationService,
  UsageService,
  WaitlistService,
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
  takeTestMagicLink?(email: string): string | null;
  takeTestOtp?(email: string): string | null;
}

export interface ApiServices {
  waitlist: WaitlistService;
  billingPayments: BillingPaymentsService;
  catalogBilling: CatalogBillingService;
  organizations: OrganizationService;
  usage: UsageService;
  workspaces: WorkspaceApiKeyService;
}
