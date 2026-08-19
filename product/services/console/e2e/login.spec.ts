import { expect, test } from "./fixtures";

test("sign-in page validates credentials and opens the product", async ({
  account,
  context,
  page,
}) => {
  await context.clearCookies();
  await page.goto("/login");

  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Email").fill(account.email);

  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "That email and password do not match.",
  );

  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/api-keys$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "API keys", exact: true }),
  ).toBeVisible();
});
