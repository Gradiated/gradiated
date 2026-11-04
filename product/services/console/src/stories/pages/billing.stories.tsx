import type { Meta } from "@storybook/react-vite";

import { Page, pageMeta, type PageStory } from "@/stories/page-story";
import {
  acmeMember,
  billingHandlers,
  billingLoadingHandlers,
  handlersFor,
} from "@/stories/handlers";

const meta = { ...pageMeta, title: "Pages/Billing" } satisfies Meta<
  typeof Page
>;

export default meta;

export const Default: PageStory = { args: { path: "/billing" } };
export const Loading: PageStory = {
  args: { path: "/billing" },
  parameters: { msw: billingLoadingHandlers },
};
export const WithoutCard: PageStory = {
  args: { path: "/billing" },
  parameters: {
    msw: billingHandlers({
      payment_method: null,
      auto_top_up: {
        enabled: false,
        threshold: null,
        amount: null,
        failure: null,
      },
    }),
  },
};
export const AutoTopUpOff: PageStory = {
  args: { path: "/billing" },
  parameters: {
    msw: billingHandlers({
      auto_top_up: {
        enabled: false,
        threshold: null,
        amount: null,
        failure: null,
      },
    }),
  },
};
export const Mastercard: PageStory = {
  args: { path: "/billing" },
  parameters: {
    msw: billingHandlers({
      payment_method: {
        brand: "mastercard",
        last4: "4444",
        exp_month: 3,
        exp_year: 2027,
      },
    }),
  },
};
export const AutoTopUpFailed: PageStory = {
  args: { path: "/billing" },
  parameters: {
    msw: billingHandlers({
      auto_top_up: {
        enabled: false,
        threshold: "10000000000",
        amount: "50000000000",
        failure: "Your card was declined.",
      },
    }),
  },
};
export const AsMember: PageStory = {
  args: { path: "/billing" },
  parameters: { msw: handlersFor(acmeMember) },
};
