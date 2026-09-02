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

  const modelCard = page
    .locator("article")
    .filter({ hasText: "mlx-community/qwen3-0.6b-4bit" })
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
  ).toHaveText(["Input", "$0.0700", "$0.100", "$0.150"]);
  await expect(
    table.getByRole("row", { name: /^Cached input / }).getByRole("cell"),
  ).toHaveText(["Cached input", "$0.0350", "$0.0500", "$0.0750"]);
  await expect(
    table.getByRole("row", { name: /^Output / }).getByRole("cell"),
  ).toHaveText(["Output", "$0.210", "$0.300", "$0.450"]);

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
