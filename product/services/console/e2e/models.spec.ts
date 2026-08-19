import { expect, test } from "./fixtures";

test("models page shows the available model and pricing", async ({ page }) => {
  await page.goto("/models");

  await expect(page).toHaveURL(/\/models$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Models" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Qwen3 0.6B 4-bit" }),
  ).toBeVisible();
  await expect(page.getByText("mlx-community/qwen3-0.6b-4bit")).toBeVisible();
  await expect(page.getByText("$0.00 / 1M")).toHaveCount(2);
});
