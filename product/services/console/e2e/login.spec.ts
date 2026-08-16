import { expect, test } from "@playwright/test";

test("sign-in page validates credentials and opens the product", async ({
  page,
}) => {
  await page.goto("/login");

  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByLabel("Email")).toHaveValue("dev@gradiated.com");

  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "That email and password do not match.",
  );

  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/api-keys$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "API keys", exact: true }),
  ).toBeVisible();
});
