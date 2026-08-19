import { expect, test } from "./fixtures";

test("billing page shows the organization balance and ledger", async ({
  page,
}) => {
  await page.goto("/billing");

  await expect(page).toHaveURL(/\/billing$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Billing" }),
  ).toBeVisible();
  await expect(page.getByText("$100.00", { exact: true })).toBeVisible();
  await expect(page.getByText("Credit", { exact: true })).toBeVisible();
  await expect(page.getByText("+$100.00", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Add funds" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Continue to Stripe" }),
  ).toBeVisible();

  await page.route(
    "**/api/v1/organizations/*/billing/top-ups",
    async (route) => {
      expect(route.request().postDataJSON()).toEqual({ amount: "50000000000" });
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          checkout_url: "http://127.0.0.1:3000/billing?topup=cancelled",
        }),
      });
    },
  );
  await page.getByRole("button", { name: "Continue to Stripe" }).click();
  await expect(page.getByText(/Checkout was cancelled/)).toBeVisible();
});
