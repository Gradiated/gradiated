import { randomUUID } from "node:crypto";

import {
  createCatalogBillingService,
  createControlDatabase,
  createValkeyServingProjector,
} from "@gradiated/control";
import { createValkeyClient } from "@gradiated/valkey";
import { expect, test as base } from "@playwright/test";

const apiUrl = "http://127.0.0.1:3001";
const databaseUrl =
  process.env.DATABASE_URL ??
  "postgresql://gradiated:gradiated@127.0.0.1:5432/gradiated";
const valkeyUrl = process.env.VALKEY_URL ?? "redis://127.0.0.1:6379";

export interface TestAccount {
  email: string;
  password: string;
  userName: string;
  organizationName: string;
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

export const test = base.extend<{ account: TestAccount }>({
  account: [
    async ({ context }, use) => {
      const suffix = randomUUID();
      const account: TestAccount = {
        email: `playwright-${suffix}@gradiated.test`,
        password: "1234",
        userName: `Playwright ${suffix.slice(0, 8)}`,
        organizationName: `Playwright Org ${suffix.slice(0, 8)}`,
      };

      const signUp = await context.request.post(
        `${apiUrl}/api/auth/sign-up/email`,
        {
          headers: { Origin: "http://127.0.0.1:3000" },
          data: {
            email: account.email,
            password: account.password,
            name: account.userName,
          },
        },
      );
      await requireOk(signUp);

      const organizationResponse = await context.request.post(
        `${apiUrl}/api/v1/organizations`,
        { data: { name: account.organizationName } },
      );
      await requireOk(organizationResponse);
      const organization = (await organizationResponse.json()) as {
        id: string;
      };

      const meResponse = await context.request.get(`${apiUrl}/api/v1/me`);
      await requireOk(meResponse);
      const currentUser = (await meResponse.json()) as { id: string };

      const { database, pool } = createControlDatabase(databaseUrl);
      const valkey = createValkeyClient({ VALKEY_URL: valkeyUrl });
      await valkey.connect();
      try {
        const billing = createCatalogBillingService(
          database,
          createValkeyServingProjector(valkey),
        );
        await billing.applyBalanceTransaction({
          organizationId: organization.id,
          type: "credit",
          amount: 100_000_000_000n,
          sourceType: "operator",
          sourceId: `playwright-credit-v1:${organization.id}`,
          createdBy: currentUser.id,
        });
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
