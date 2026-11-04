import type { Meta } from "@storybook/react-vite";

import { Page, pageMeta, type PageStory } from "@/stories/page-story";
import { acmeAdmin, acmeMember, handlersFor } from "@/stories/handlers";

const meta = { ...pageMeta, title: "Pages/Settings" } satisfies Meta<
  typeof Page
>;

export default meta;

export const Workspace: PageStory = {
  args: { path: "/settings/workspace" },
  parameters: { nameField: "Workspace name" },
};
export const Organization: PageStory = {
  args: { path: "/settings/organization" },
  parameters: { nameField: "Organization name", msw: handlersFor(acmeAdmin) },
};
export const OrganizationMobile: PageStory = {
  args: { path: "/settings/organization" },
  parameters: { nameField: "Organization name", msw: handlersFor(acmeAdmin) },
  tags: ["mobile"],
};
export const Members: PageStory = {
  args: { path: "/settings/members" },
  parameters: { members: true, msw: handlersFor(acmeAdmin) },
};
export const MembersMobile: PageStory = {
  args: { path: "/settings/members" },
  parameters: { members: true, msw: handlersFor(acmeAdmin) },
  tags: ["mobile"],
};
export const MembersAsMember: PageStory = {
  args: { path: "/settings/members" },
  parameters: { members: true, msw: handlersFor(acmeMember) },
};
export const MemberActions: PageStory = {
  args: { path: "/settings/members" },
  parameters: {
    members: true,
    memberActions: "sam@acme.com",
    msw: handlersFor(acmeAdmin),
  },
};
export const InviteMembers: PageStory = {
  args: { path: "/settings/members" },
  parameters: { members: true, invite: true, msw: handlersFor(acmeAdmin) },
};
