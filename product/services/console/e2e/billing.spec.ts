import { consoleUrl } from "./env";
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
  await page.getByRole("button", { name: "Top up" }).click();
  const dialog = page.getByRole("dialog", { name: "Top up" });
  const amount = dialog.getByLabel("Amount");
  const continueToStripe = dialog.getByRole("button", {
    name: "Continue to Stripe",
  });
  await expect(continueToStripe).toBeVisible();

  const topUpsRoute = "**/api/v1/organizations/*/billing/top-ups";
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
  const rangeError = dialog.getByText(
    "Enter an amount between $5 and $10,000.",
  );
  await expect(rangeError).toBeVisible();
  await dialog.getByRole("button", { name: "$100", exact: true }).click();
  await expect(amount).toHaveValue("100");
  await expect(rangeError).toHaveCount(0);
  expect(topUpRequests).toBe(0);

  await amount.fill("50");
  await continueToStripe.click();
  // Errors are toasts, which render outside the dialog.
  await expect(page.getByText("Stripe is unavailable.")).toBeVisible();
  expect(topUpRequests).toBe(1);
  await page.unroute(topUpsRoute);

  await page.route(topUpsRoute, async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      amount: "50000000000",
      method: "checkout",
      idempotency_key: expect.stringMatching(/^[0-9a-f-]{36}$/),
    });
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        status: "checkout",
        checkout_url: `${consoleUrl}/billing?topup=cancelled`,
      }),
    });
  });
  await continueToStripe.click();
  await expect(page.getByText("Checkout cancelled")).toBeVisible();
});

test("balance history loads older rows automatically and recovers from page errors", async ({
  page,
}) => {
  let fail = true;
  let releasePage!: () => void;
  const held = new Promise<void>((resolve) => {
    releasePage = resolve;
  });
  const requests: (string | null)[] = [];
  await page.route("**/balance-transactions?*", async (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get("limit")).toBe("100");
    const cursor = url.searchParams.get("cursor");
    requests.push(cursor);
    if (cursor) {
      await held;
      if (fail)
        return route.fulfill({ status: 503, json: { detail: "Unavailable" } });
    }
    return route.fulfill({
      json: {
        data: Array.from({ length: cursor ? 3 : 100 }, (_, index) => ({
          id: `transaction-${cursor ? 100 + index : index}`,
          type: "credit",
          amount: "1000000000",
          balance_after: "100000000000",
          created_at: "2026-10-01T12:00:00Z",
        })),
        next_cursor: cursor ? null : "older",
      },
    });
  });
  await page.goto("/billing");
  const history = page.getByRole("table", { name: "Balance history" });
  await expect(history.getByRole("row")).toHaveCount(100);
  expect(requests).toEqual([null]);
  await history.getByRole("row").last().scrollIntoViewIfNeeded();
  await expect(
    page.getByRole("status", { name: "Loading older transactions" }),
  ).toBeVisible();
  await expect(history.getByRole("row", { includeHidden: true })).toHaveCount(
    103,
  );
  expect(requests).toEqual([null, "older"]);
  releasePage();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Could not load balance history." }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(history.getByRole("row")).toHaveCount(100);
  fail = false;
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(history.getByRole("row")).toHaveCount(103);
  await expect(
    page.getByRole("status", { name: "Loading older transactions" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Next", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Previous", exact: true }),
  ).toHaveCount(0);
});

test("auto top-up needs a saved card before it can be set up", async ({
  page,
}) => {
  // Card entry runs in Stripe's iframe; here it is unavailable, so the dialog
  // offers a retry and reports why.
  let setups = 0;
  await page.route("**/api/v1/organizations/*/billing/card-setups", (route) => {
    setups += 1;

    return route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Card entry is not configured." }),
    });
  });

  await page.goto("/billing");

  await expect(page.getByText("No card saved")).toBeVisible();
  await expect(page.getByRole("button", { name: "Set up" })).toBeDisabled();

  await page.getByRole("button", { name: "Add card" }).click();
  const dialog = page.getByRole("dialog", { name: "Add card" });
  await expect(dialog).toBeVisible();
  await expect(page.getByText("Card entry is not configured.")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Try again" })).toBeVisible();
  expect(setups).toBe(1);
});
