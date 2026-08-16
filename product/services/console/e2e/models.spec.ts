import { expect, test } from "@playwright/test";

test("models page shows the available model and pricing", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("link", { name: "Models" }).click();

  await expect(page).toHaveURL(/\/models$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Models" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Kimi K3" })).toBeVisible();
  await expect(page.getByText("moonshotai/kimi-k3")).toBeVisible();
  await expect(page.getByText("$2.80 / 1M")).toBeVisible();
  await expect(page.getByText("$14.00 / 1M")).toBeVisible();
});
