import { randomUUID } from "node:crypto";

import {
  createCatalogBillingService,
  createControlDatabase,
  createValkeyServingProjector,
} from "@gradiated/control";
import { createValkeyClient } from "@gradiated/valkey";
import { expect, test as base, type BrowserContext } from "@playwright/test";

const apiPort = process.env.PLAYWRIGHT_API_PORT ?? "3001";
const consolePort = process.env.PLAYWRIGHT_CONSOLE_PORT ?? "3000";
export const apiUrl = `http://127.0.0.1:${apiPort}`;
const consoleUrl = `http://127.0.0.1:${consolePort}`;
const databaseUrl =
  process.env.DATABASE_URL ??
  "postgresql://gradiated:gradiated@127.0.0.1:5432/gradiated";
const valkeyUrl = process.env.VALKEY_URL ?? "redis://127.0.0.1:6379";

export interface TestAccount {
  email: string;
  userName: string;
  organizationName: string;
  organizationId: string;
  creditUsd: string;
}

const requireOk = async (response: {
  ok(): boolean;
  status(): number;
  text(): Promise<string>;
}) => {
  if (response.ok()) return;
  throw new Error(
    `Test-account setup failed with status ${response.status()}: ${await response.text()}`,
  );
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

  const captured = await context.request.get(
    `${apiUrl}/api/auth/test/magic-link?email=${encodeURIComponent(email)}`,
  );
  await requireOk(captured);
  const { url } = (await captured.json()) as { url: string };
  const verification = new URL(url);
  const apiOrigin = new URL(apiUrl);
  verification.protocol = apiOrigin.protocol;
  verification.host = apiOrigin.host;
  const verified = await context.request.get(verification.toString(), {
    maxRedirects: 0,
  });
  if (![302, 303, 307].includes(verified.status())) await requireOk(verified);
};

const formatSignedNanoUsd = (nanoUsd: bigint): string => {
  const cents = nanoUsd / 10_000_000n;
  const negative = cents < 0n;
  const absolute = negative ? -cents : cents;
  const whole = absolute / 100n;
  const fraction = absolute % 100n;
  return `${negative ? "-" : "+"}$${whole}.${fraction
    .toString()
    .padStart(2, "0")}`;
};

export const test = base.extend<{ account: TestAccount }>({
  account: [
    async ({ context }, use) => {
      const suffix = randomUUID();
      const account: TestAccount = {
        email: `playwright-${suffix}@gradiated.test`,
        userName: `Playwright ${suffix.slice(0, 8)}`,
        organizationName: "Personal",
        organizationId: "",
        creditUsd: "+$0.00",
      };

      await signInWithMagicLink(context, account.email, account.userName);

      const meResponse = await context.request.get(`${apiUrl}/api/v1/me`);
      await requireOk(meResponse);
      const currentUser = (await meResponse.json()) as {
        id: string;
        organizations: Array<{ id: string }>;
      };
      const organization = currentUser.organizations[0];
      if (!organization) throw new Error("Test account has no organization");
      account.organizationId = organization.id;

      const billingResponse = await context.request.get(
        `${apiUrl}/api/v1/organizations/${organization.id}/billing`,
      );
      await requireOk(billingResponse);
      const billing = (await billingResponse.json()) as { balance: string };

      const { database, pool } = createControlDatabase(databaseUrl);
      const valkey = createValkeyClient({ VALKEY_URL: valkeyUrl });
      await valkey.connect();
      try {
        const billingService = createCatalogBillingService(
          database,
          createValkeyServingProjector(valkey),
        );
        // New accounts start with the signup credit; top up to an exact
        // $100.00 so billing-page assertions stay stable.
        const targetBalance = 100_000_000_000n;
        const creditAmount = targetBalance - BigInt(billing.balance);
        if (creditAmount > 0n) {
          await billingService.applyBalanceTransaction({
            organizationId: organization.id,
            type: "credit",
            amount: creditAmount,
            sourceType: "operator",
            sourceId: `playwright-credit-v1:${organization.id}`,
            createdBy: currentUser.id,
          });
        }
        account.creditUsd = formatSignedNanoUsd(creditAmount);
      } finally {
        if (valkey.isOpen) await valkey.quit();
        await pool.end();
      }

      await use(account);
    },
    { auto: true },
  ],
});

export { expect };
