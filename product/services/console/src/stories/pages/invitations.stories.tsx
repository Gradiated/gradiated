import type { Meta } from "@storybook/react-vite";

import { Page, pageMeta, type PageStory } from "@/stories/page-story";
import {
  acmeMember,
  invitationHandlers,
  invitationPreview,
  invitee,
  otherAccount,
} from "@/stories/handlers";

const meta = { ...pageMeta, title: "Pages/Invitations" } satisfies Meta<
  typeof Page
>;

export default meta;

const invitationStory = (
  preview: Parameters<typeof invitationHandlers>[0],
  currentUser: Parameters<typeof invitationHandlers>[1],
): PageStory => ({
  args: { path: `/invitations/accept?token=${"a".repeat(43)}` },
  parameters: { msw: invitationHandlers(preview, currentUser) },
});
export const Accept = invitationStory(invitationPreview, invitee);
export const SignedOut = invitationStory(invitationPreview, null);
export const WrongAccount = invitationStory(invitationPreview, otherAccount);
export const Expired = invitationStory(
  { ...invitationPreview, status: "expired" },
  invitee,
);
export const Invalid = invitationStory({ status: "invalid" }, null);
export const AlreadyMember = invitationStory(
  { ...invitationPreview, email: "priya@acme.com" },
  acmeMember,
);
export const Error: PageStory = {
  ...invitationStory("error", invitee),
  tags: ["request-failure"],
};
