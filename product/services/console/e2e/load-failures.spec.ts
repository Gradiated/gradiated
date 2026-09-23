import { expect, test } from "./fixtures";
import { fulfillProblem, apiPathEndsWith } from "./routes";

const RETRIES_EXHAUSTED = { timeout: 15_000 };

const pages = [
  {
    path: "/api-keys",
    route: apiPathEndsWith("/api-keys"),
    failure: "Could not load API keys.",
    empty: "No active API keys",
    recovered: "No active API keys",
  },
  {
    path: "/models",
    route: apiPathEndsWith("/api/v1/models"),
    failure: "Could not load models.",
    empty: "No models are currently available.",
    recovered: "Price per 1M tokens",
  },
  {
    path: "/billing",
    route: apiPathEndsWith("/billing"),
    failure: "Could not load the balance.",
    empty: "Available balance",
    recovered: "$100.00",
  },
  {
    path: "/logs",
    route: apiPathEndsWith("/generations"),
    failure: "Could not load logs.",
    empty: "No logs found",
    recovered: "No logs found",
  },
] as const;

for (const { path, route, failure, empty, recovered } of pages) {
  test(`${path} shows a retryable failure instead of an empty state`, async ({
    page,
  }) => {
    await page.route(route, (request) =>
      fulfillProblem(request, 500, "The server failed."),
    );
    await page.goto(path);

    await expect(page.getByText(failure)).toBeVisible(RETRIES_EXHAUSTED);
    await expect(page.getByText(empty)).toHaveCount(0);

    await page.unroute(route);
    await page.getByRole("button", { name: "Retry" }).click();

    await expect(page.getByText(recovered).first()).toBeVisible();
    await expect(page.getByText(failure)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Retry" })).toHaveCount(0);
  });
}
