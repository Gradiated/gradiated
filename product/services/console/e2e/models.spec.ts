import { apiPathEndsWith, fulfillJson } from "./routes";
import { expect, test } from "./fixtures";

test("models page shows the available model and pricing", async ({ page }) => {
  await page.goto("/models");

  await expect(page).toHaveURL(/\/models$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Models" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "DeepSeek V4.1 Flash" }),
  ).toBeVisible();
  await expect(page.getByText("deepseek/deepseek-v4.1-flash")).toBeVisible();

  const modelCard = page
    .locator("article")
    .filter({ hasText: "deepseek/deepseek-v4.1-flash" })
    .first();
  const table = modelCard.getByRole("table");
  await expect(table.getByRole("columnheader")).toHaveText([
    "Token type",
    "Flex (-30%)",
    "Default",
    "Fast (+50%)",
  ]);
  await expect(
    table.getByRole("row", { name: /^Input / }).getByRole("cell"),
  ).toHaveText(["Input", "$0.210", "$0.300", "$0.450"]);
  await expect(
    table.getByRole("row", { name: /^Cached input / }).getByRole("cell"),
  ).toHaveText(["Cached input", "$0.00400", "$0.00600", "$0.00900"]);
  await expect(
    table.getByRole("row", { name: /^Output / }).getByRole("cell"),
  ).toHaveText(["Output", "$0.840", "$1.20", "$1.80"]);

  const layout = await table.evaluate((element) => {
    const tableWidth = element.getBoundingClientRect().width;
    const containerWidth = element.parentElement?.getBoundingClientRect().width;
    const columnWidths = Array.from(element.querySelectorAll("th")).map(
      (header) => header.getBoundingClientRect().width,
    );
    return { tableWidth, containerWidth, columnWidths };
  });
  expect(layout.tableWidth).toBeCloseTo(layout.containerWidth ?? 0, 0);
  expect(
    Math.max(...layout.columnWidths) - Math.min(...layout.columnWidths),
  ).toBeLessThan(2);
});

test("models page keeps unavailable hosted models and hides training-only bases", async ({
  page,
}) => {
  await page.route(apiPathEndsWith("/models"), async (route) => {
    const response = await route.fetch();
    const catalog = await response.json();
    const model = catalog.data[0];
    return fulfillJson(route, {
      ...catalog,
      data: [
        { ...model, status: "unavailable" },
        {
          ...model,
          id: "Qwen/Qwen3-0.6B",
          name: "Qwen training only",
          status: "unavailable",
        },
      ],
    });
  });
  await page.goto("/models");
  await expect(page.locator("article")).toHaveCount(1);
  await expect(page.locator("article")).toContainText("Unavailable");
  await expect(page.getByText("Qwen training only")).toHaveCount(0);
});
