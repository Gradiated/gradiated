import type { Meta } from "@storybook/react-vite";

import { Page, pageMeta, type PageStory } from "@/stories/page-story";
import {
  handlersFor,
  onboardingCompanyUser,
  onboardingPersonalUser,
} from "@/stories/handlers";

const meta = { ...pageMeta, title: "Pages/Onboarding" } satisfies Meta<
  typeof Page
>;

export default meta;

export const Company: PageStory = {
  args: { path: "/onboarding" },
  parameters: { msw: handlersFor(onboardingCompanyUser) },
};
export const PersonalEmail: PageStory = {
  args: { path: "/onboarding" },
  parameters: { msw: handlersFor(onboardingPersonalUser) },
};
