import type { Meta } from "@storybook/react-vite";
import { expect, userEvent, within } from "storybook/test";

import { Page, pageMeta, type PageStory } from "@/stories/page-story";
import {
  oauthConsentHandlers,
  oauthConsentQuery,
  oauthOrganizationsUser,
  oauthSameNameUser,
  oauthSuspendedUser,
} from "@/stories/handlers";

const meta = { ...pageMeta, title: "Pages/OAuth consent" } satisfies Meta<
  typeof Page
>;

export default meta;

const path = `/oauth/consent?${oauthConsentQuery}`;

export const Consent: PageStory = {
  args: { path },
  parameters: { msw: oauthConsentHandlers() },
};

export const WorkspacesAcrossOrganizations: PageStory = {
  args: { path },
  parameters: { msw: oauthConsentHandlers(oauthOrganizationsUser) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByRole("heading", { level: 1 }, { timeout: 10000 });
    await userEvent.click(
      await canvas.findByRole("combobox", { name: "Workspace" }),
    );

    const body = within(canvasElement.ownerDocument.body);
    const groups = await body.findAllByRole("group");
    await expect(groups).toHaveLength(2);
    await expect(
      within(groups[0]!).getByText("Example organization"),
    ).toBeVisible();
    await expect(within(groups[1]!).getByText("Acme")).toBeVisible();
  },
};

export const OrganizationsSharingAName: PageStory = {
  args: { path },
  parameters: { msw: oauthConsentHandlers(oauthSameNameUser) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByRole("heading", { level: 1 }, { timeout: 10000 });
    await userEvent.click(
      await canvas.findByRole("combobox", { name: "Workspace" }),
    );

    const groups = await within(canvasElement.ownerDocument.body).findAllByRole(
      "group",
    );
    await expect(
      groups.map((group) => group.firstElementChild?.textContent),
    ).toEqual(["Acme (acme)", "Acme (acme-labs)", "Acme (acme)"]);
  },
};

export const NoUsableWorkspace: PageStory = {
  args: { path },
  parameters: { msw: oauthConsentHandlers(oauthSuspendedUser) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(
      "You have no workspace this application can use.",
      {},
      { timeout: 10000 },
    );
    await expect(canvas.getByRole("button", { name: "Allow" })).toBeDisabled();
  },
};
