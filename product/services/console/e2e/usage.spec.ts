import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { apiPathEndsWith, fulfillJson, fulfillProblem } from "./routes";

const today = new Date().toISOString().slice(0, 10);
const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);

const usage = {
  charge: "3500000000",
  input_tokens: "1000",
  output_tokens: "500",
  generation_count: "8",
  succeeded_count: "6",
  daily: [
    {
      date: yesterday,
      charge: "1500000000",
      input_tokens: "400",
      output_tokens: "200",
      generation_count: "3",
    },
    {
      date: today,
      charge: "2000000000",
      input_tokens: "600",
      output_tokens: "300",
      generation_count: "5",
    },
  ],
  models: [
    {
      model_id: "deepseek/deepseek-v4.1-flash",
      charge: "3500000000",
      input_tokens: "1000",
      output_tokens: "500",
      generation_count: "8",
    },
  ],
};

const summary = (page: Page, label: string) =>
  page.getByRole("group", { name: label, exact: true });

test("usage page summarizes spend, requests and success rate", async ({
  page,
}) => {
  await page.route(apiPathEndsWith("/usage"), (route) =>
    fulfillJson(route, usage),
  );
  await page.goto("/usage");

  await expect(summary(page, "Total spend")).toContainText("$3.50");
  await expect(summary(page, "Requests")).toContainText("8");
  await expect(page.getByText("75.0% succeeded")).toBeVisible();
});

test("usage page shows a retryable failure", async ({ page }) => {
  await page.route(apiPathEndsWith("/usage"), (route) =>
    fulfillProblem(route, 500, "The usage store failed."),
  );
  await page.goto("/usage");

  await expect(page.getByText("Could not load usage.")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText("Total spend")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});
