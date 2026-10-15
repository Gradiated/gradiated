import { randomUUID } from "node:crypto";

import { apiUrl } from "./env";
import { expect, readMagicLink, test } from "./fixtures";

test("an admin invites someone who joins from the emailed link", async ({
  account,
  browser,
  page,
}) => {
  const email = `invitee-${randomUUID()}@gradiated.test`;

  await page.goto("/settings/members");
  await page.getByRole("button", { name: "Invite members" }).click();
  await page.getByRole("textbox", { name: "Email addresses" }).fill(email);
  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByText(email)).toBeVisible();

  const captured = await page.request.get(
    `${apiUrl}/api/auth/test/invitation?email=${encodeURIComponent(email)}`,
  );
  expect(captured.ok()).toBe(true);
  const { url } = (await captured.json()) as { url: string };
  const link = new URL(url);

  const context = await browser.newContext();
  const invitee = await context.newPage();
  await invitee.goto(`${link.pathname}${link.search}`);
  await expect(
    invitee.getByRole("heading", {
      name: `Sign in to join ${account.organizationName}`,
    }),
  ).toBeVisible();
  await expect(invitee.getByLabel("Email")).toHaveValue(email);
  await invitee
    .getByRole("button", { name: "Email me a sign-in link" })
    .click();
  await invitee.goto((await readMagicLink(context.request, email)).toString());

  await expect(
    invitee.getByRole("heading", {
      name: `You're already in ${account.organizationName}`,
    }),
  ).toBeVisible();
  await invitee
    .getByRole("button", { name: `Open ${account.organizationName}` })
    .click();
  await expect(invitee).toHaveURL(/\/models$/);
  await context.close();

  await page.reload();
  await expect(page.getByText(email)).toBeVisible();
  await expect(page.getByText(`Invited · Member`)).toHaveCount(0);
});
