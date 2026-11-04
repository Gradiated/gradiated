import type { Meta, StoryObj } from "@storybook/react-vite";
import { http, HttpResponse } from "msw";
import { userEvent, within } from "storybook/test";

import { account, Providers } from "./billing-story";
import { TopUpDialog } from "./top-up-dialog";

const topUpsPath = "/api/v1/organizations/:organizationId/billing/top-ups";

const meta = {
  title: "Pages/Billing/Blocks/Top up",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const WithSavedCard: Story = {
  render: () => (
    <Providers>
      <TopUpDialog
        account={account()}
        open
        onOpenChange={() => undefined}
        onChangeCard={() => undefined}
      />
    </Providers>
  ),
};

export const WithoutCard: Story = {
  render: () => (
    <Providers>
      <TopUpDialog
        account={account({ payment_method: null })}
        open
        onOpenChange={() => undefined}
        onChangeCard={() => undefined}
      />
    </Providers>
  ),
};

export const Declined: Story = {
  tags: ["request-failure"],
  parameters: {
    msw: [
      http.post(topUpsPath, () =>
        HttpResponse.json(
          {
            type: "https://gradiated.com/problems/payment-failed",
            title: "Payment failed",
            status: 402,
            detail: "Your card was declined.",
            code: "payment_failed",
          },
          { status: 402 },
        ),
      ),
    ],
  },
  render: () => (
    <Providers>
      <TopUpDialog
        account={account()}
        open
        onOpenChange={() => undefined}
        onChangeCard={() => undefined}
      />
    </Providers>
  ),
  // Submits so the decline toast, with its retry action, is on screen.
  play: async () => {
    const body = within(document.body);
    await userEvent.click(
      await body.findByRole("button", { name: /^Pay \$50\.00$/ }),
    );
    await body.findByText("Payment declined");
  },
};
