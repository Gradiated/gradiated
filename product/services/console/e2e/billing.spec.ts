import {
  createCatalogBillingService,
  createControlDatabase,
} from "@gradiated/control";

import { consoleUrl, databaseUrl } from "./env";
import { expect, test } from "./fixtures";

test("billing page shows the organization balance and ledger", async ({
  page,
  account,
}) => {
  await page.goto("/billing");

  await expect(page).toHaveURL(/\/billing$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Billing" }),
  ).toBeVisible();
  await expect(page.getByText("$100.00", { exact: true })).toBeVisible();
  await expect(page.getByText("Credit", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText(account.creditUsd, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Balance history" }).getByRole("row"),
  ).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "Previous", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Next", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Add funds" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Continue to Stripe" }),
  ).toBeVisible();

  const topUpsRoute = "**/api/v1/organizations/*/billing/top-ups";
  const amount = page.getByLabel("Amount (USD)");
  const continueToStripe = page.getByRole("button", {
    name: "Continue to Stripe",
  });

  let topUpRequests = 0;
  await page.route(topUpsRoute, async (route) => {
    topUpRequests += 1;
    await route.fulfill({
      status: 502,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Stripe is unavailable." }),
    });
  });

  await amount.fill("4");
  await continueToStripe.click();
  const rangeError = page.getByText("Enter an amount between $5 and $10,000.");
  await expect(rangeError).toBeVisible();
  await page.getByRole("button", { name: "$100", exact: true }).click();
  await expect(amount).toHaveValue("100");
  await expect(rangeError).toHaveCount(0);

  await amount.fill("abc");
  await continueToStripe.click();
  await expect(page.getByText("Enter a valid USD amount.")).toBeVisible();
  expect(topUpRequests).toBe(0);

  await amount.fill("50");
  await continueToStripe.click();
  await expect(page.getByText("Stripe is unavailable.")).toBeVisible();
  await expect(page).toHaveURL(/\/billing$/);
  expect(topUpRequests).toBe(1);
  await page.unroute(topUpsRoute);

  await page.route(topUpsRoute, async (route) => {
    expect(route.request().postDataJSON()).toEqual({ amount: "50000000000" });
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        checkout_url: `${consoleUrl}/billing?topup=cancelled`,
      }),
    });
  });
  await continueToStripe.click();
  await expect(page.getByText(/Checkout was cancelled/)).toBeVisible();
});

test("balance history paginates the full ledger and recovers from page errors", async ({
  page,
  account,
}) => {
  const { database, pool } = createControlDatabase(databaseUrl);
  try {
    const billing = createCatalogBillingService(database);
    for (let amount = 1; amount <= 23; amount += 1) {
      await billing.applyBalanceTransaction({
        organizationId: account.organizationId,
        type: "credit",
        amount: BigInt(amount) * 1_000_000_000n,
        sourceType: "operator",
        sourceId: `pagination:${account.organizationId}:${amount}`,
        createdBy: null,
      });
    }
  } finally {
    await pool.end();
  }

  await page.goto("/billing");
  const history = page.getByRole("table", { name: "Balance history" });
  const previous = page.getByRole("button", { name: "Previous", exact: true });
  const next = page.getByRole("button", { name: "Next", exact: true });

  await expect(history.getByRole("row")).toHaveCount(10);
  await expect(history.getByText("+$23.00", { exact: true })).toBeVisible();
  await expect(previous).toBeDisabled();
  await next.click();
  await expect(history.getByText("+$13.00", { exact: true })).toBeVisible();
  await expect(history.getByRole("row")).toHaveCount(10);
  await next.click();
  await expect(history.getByText("+$3.00", { exact: true })).toBeVisible();
  await expect(history.getByRole("row")).toHaveCount(5);
  await expect(next).toBeDisabled();
  await previous.click();
  await expect(history.getByText("+$13.00", { exact: true })).toBeVisible();
  await previous.click();
  await expect(history.getByText("+$23.00", { exact: true })).toBeVisible();
  await expect(previous).toBeDisabled();

  await page.reload();
  await expect(history.getByText("+$23.00", { exact: true })).toBeVisible();

  let fail = true;
  let releasePage: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    releasePage = resolve;
  });
  await page.route("**/balance-transactions?*", async (route) => {
    if (!new URL(route.request().url()).searchParams.has("cursor"))
      return route.continue();
    await held;
    if (fail)
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Unavailable" }),
      });

    return route.continue();
  });
  await next.click();
  await expect(history).toHaveCount(0);
  await expect(previous).toBeDisabled();
  releasePage?.();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Could not load balance history." }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(next).toBeDisabled();
  fail = false;
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(history.getByText("+$13.00", { exact: true })).toBeVisible();
});
