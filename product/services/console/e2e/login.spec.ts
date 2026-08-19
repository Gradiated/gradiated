import { expect, test } from "./fixtures";

test("sign-in page sends and consumes a magic link", async ({
  account,
  context,
  page,
}) => {
  await context.clearCookies();
  await page.goto("/login");

  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Email").fill(account.email);
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  await expect(page.getByText("Check your email")).toBeVisible();

  const captured = await context.request.get(
    `http://127.0.0.1:3001/api/auth/test/magic-link?email=${encodeURIComponent(account.email)}`,
  );
  expect(captured.ok()).toBe(true);
  const { url } = (await captured.json()) as { url: string };
  const verification = new URL(url);
  verification.hostname = "127.0.0.1";
  verification.port = "3001";
  await page.goto(verification.toString());

  await expect(page).toHaveURL(/\/api-keys$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "API keys", exact: true }),
  ).toBeVisible();
});
