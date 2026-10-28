import type { Meta, StoryObj } from "@storybook/react-vite";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { userEvent, within } from "storybook/test";
import { useState, type ReactNode } from "react";

import type { BillingAccount } from "@/api/queries";
import { Toaster } from "@/components/ui/sonner";
import { createStoryQueryClient } from "@/stories/query-client";
import { billing } from "@/stories/handlers";
import { AutoTopUpDialog } from "./auto-top-up-dialog";
import { CardBrandMark, cardBrandName } from "./card-brand-mark";
import { TopUpDialog } from "./top-up-dialog";

const BRANDS = [
  "visa",
  "mastercard",
  "amex",
  "discover",
  "jcb",
  "unionpay",
  "diners",
  "unknown",
];

const topUpsPath = "/api/v1/organizations/:organizationId/billing/top-ups";

const Providers = ({ children }: { children: ReactNode }) => {
  const [queryClient] = useState(() => createStoryQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-background">{children}</div>
      <Toaster />
    </QueryClientProvider>
  );
};

const account = (overrides: Partial<BillingAccount> = {}): BillingAccount => ({
  ...billing,
  mode: "prepaid",
  ...overrides,
});

const meta = {
  title: "Components/Billing",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const CardBrands: Story = {
  render: () => (
    <div className="grid w-fit grid-cols-2 gap-x-8 gap-y-3 p-8">
      {BRANDS.map((brand) => (
        <div key={brand} className="flex items-center gap-3 text-sm">
          <CardBrandMark brand={brand} />
          {cardBrandName(brand)}
        </div>
      ))}
    </div>
  ),
};

export const TopUpWithSavedCard: Story = {
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

export const TopUpWithoutCard: Story = {
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

export const TopUpDeclined: Story = {
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

export const AutoTopUpEdit: Story = {
  render: () => (
    <Providers>
      <AutoTopUpDialog
        account={account()}
        open
        onOpenChange={() => undefined}
      />
    </Providers>
  ),
};

export const AutoTopUpSetUp: Story = {
  render: () => (
    <Providers>
      <AutoTopUpDialog
        account={account({
          auto_top_up: {
            enabled: false,
            threshold: null,
            amount: null,
            failure: null,
          },
        })}
        open
        onOpenChange={() => undefined}
      />
    </Providers>
  ),
};
