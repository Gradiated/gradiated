import type { Meta, StoryObj } from "@storybook/react-vite";

import { AutoTopUpDialog } from "./auto-top-up-dialog";
import { account, Providers } from "./billing-story";

const meta = {
  title: "Pages/Billing/Blocks/Auto top-up",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Edit: Story = {
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

export const SetUp: Story = {
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
