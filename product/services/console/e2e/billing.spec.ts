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
        checkout_url: "http://127.0.0.1:3000/billing?topup=cancelled",
      }),
    });
  });
  await continueToStripe.click();
  await expect(page.getByText(/Checkout was cancelled/)).toBeVisible();
});
