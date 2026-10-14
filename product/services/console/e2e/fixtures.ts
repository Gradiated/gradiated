import { randomUUID } from "node:crypto";

import {
  createCatalogBillingService,
  createControlDatabase,
} from "@gradiated/control";
import {
  expect,
  test as base,
  type APIRequestContext,
  type APIResponse,
  type BrowserContext,
} from "@playwright/test";
import { z } from "zod";

import { apiUrl, consoleUrl, databaseUrl } from "./env";

const TARGET_BALANCE_NANO_USD = 100_000_000_000n;

const MagicLinkSchema = z.object({ url: z.url() });
const CurrentUserSchema = z.object({
  id: z.string(),
  organizations: z.array(z.object({ id: z.string(), name: z.string() })),
});
const BillingSchema = z.object({ balance: z.string().regex(/^-?\d+$/) });

export interface TestAccount {
  readonly email: string;
  readonly userName: string;
  readonly organizationName: string;
  readonly organizationId: string;
  readonly creditUsd: string;
}

const requireOk = async (response: APIResponse) => {
  if (response.ok()) return;

  throw new Error(
    `Test-account setup failed with status ${response.status()}: ${await response.text()}`,
  );
};

export const readMagicLink = async (
  request: APIRequestContext,
  email: string,
): Promise<URL> => {
  const captured = await request.get(
    `${apiUrl}/api/auth/test/magic-link?email=${encodeURIComponent(email)}`,
  );
  await requireOk(captured);

  const { url } = MagicLinkSchema.parse(await captured.json());
  const verification = new URL(url);
  const apiOrigin = new URL(apiUrl);
  verification.protocol = apiOrigin.protocol;
  verification.host = apiOrigin.host;

  return verification;
};

const signInWithMagicLink = async (
  context: BrowserContext,
  email: string,
  name: string,
): Promise<void> => {
  const requested = await context.request.post(
    `${apiUrl}/api/auth/sign-in/magic-link`,
    {
      headers: { Origin: consoleUrl },
      data: {
        email,
        name,
        callbackURL: `${consoleUrl}/api-keys`,
        newUserCallbackURL: `${consoleUrl}/api-keys`,
        errorCallbackURL: `${consoleUrl}/login`,
      },
    },
  );
  await requireOk(requested);

  const verification = await readMagicLink(context.request, email);
  const verified = await context.request.get(verification.toString(), {
    maxRedirects: 0,
  });
  if (![302, 303, 307].includes(verified.status())) await requireOk(verified);
};

const formatNanoUsdCredit = (nanoUsd: bigint): string => {
  const cents = nanoUsd / 10_000_000n;
  const whole = cents / 100n;
  const fraction = (cents % 100n).toString().padStart(2, "0");

  return `+$${whole}.${fraction}`;
};

const creditToTargetBalance = async (
  organizationId: string,
  userId: string,
  balance: bigint,
): Promise<bigint> => {
  const creditAmount = TARGET_BALANCE_NANO_USD - balance;
  if (creditAmount <= 0n) {
    throw new Error(
      `Test-account setup expected a signup balance below ${TARGET_BALANCE_NANO_USD} nano-USD, got ${balance}.`,
    );
  }

  const { database, pool } = createControlDatabase(databaseUrl);
  try {
    await createCatalogBillingService(database).applyBalanceTransaction({
      organizationId,
      type: "credit",
      amount: creditAmount,
      sourceType: "operator",
      sourceId: `playwright-credit-v1:${organizationId}`,
      createdBy: userId,
    });
  } finally {
    await pool.end();
  }

  return creditAmount;
};

export const test = base.extend<{ account: TestAccount }>({
  account: [
    async ({ context }, use) => {
      const suffix = randomUUID();
      const email = `playwright-${suffix}@gradiated.test`;
      const userName = `Playwright ${suffix.slice(0, 8)}`;

      await signInWithMagicLink(context, email, userName);

      const meResponse = await context.request.get(`${apiUrl}/api/v1/me`);
      await requireOk(meResponse);

      const currentUser = CurrentUserSchema.parse(await meResponse.json());
      const organization = currentUser.organizations[0];
      if (!organization) throw new Error("Test account has no organization");

      await requireOk(
        await context.request.patch(
          `${apiUrl}/api/v1/organizations/${organization.id}`,
          {
            headers: { Origin: consoleUrl },
            data: { onboarding_completed: true },
          },
        ),
      );

      const billingResponse = await context.request.get(
        `${apiUrl}/api/v1/organizations/${organization.id}/billing`,
      );
      await requireOk(billingResponse);

      const billing = BillingSchema.parse(await billingResponse.json());

      const creditAmount = await creditToTargetBalance(
        organization.id,
        currentUser.id,
        BigInt(billing.balance),
      );

      await use({
        email,
        userName,
        organizationName: organization.name,
        organizationId: organization.id,
        creditUsd: formatNanoUsdCredit(creditAmount),
      });
    },
    { auto: true },
  ],
});

export { expect };
