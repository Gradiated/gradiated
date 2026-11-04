import type { Meta, StoryObj } from "@storybook/react-vite";
import { http, HttpResponse } from "msw";
import { userEvent, within } from "storybook/test";

import type { components } from "@/api/schema";
import { Page } from "@/stories/page-story";
import { handlers, version } from "@/stories/handlers";

const meta = {
  title: "Pages/Training/Blocks/Download adapter",
  component: Page,
  args: { path: "/tasks/support-assistant" },
  render: (args, { id }) => <Page key={id} {...args} />,
  play: async ({ canvasElement }) => {
    await userEvent.click(
      await within(canvasElement).findByRole(
        "button",
        { name: "Download" },
        { timeout: 10000 },
      ),
    );
    await within(canvasElement.ownerDocument.body).findByRole("dialog");
  },
} satisfies Meta<typeof Page>;

export default meta;
type Story = StoryObj<typeof meta>;

const withAdapter = (
  adapter: Partial<components["schemas"]["TaskVersion"]["adapter"]>,
) => [
  http.get("/api/v1/workspaces/:workspaceId/tasks/:task/versions", () =>
    HttpResponse.json({
      data: [{ ...version, adapter: { ...version.adapter, ...adapter } }],
      next_cursor: null,
    }),
  ),
  ...handlers,
];

export const KnownCheckpoint: Story = {
  parameters: {
    msw: withAdapter({
      base_model_revision: "c1899de289a04d12100db370d81485cdf75e47ca",
      validated_base_model_revision: "c1899de289a04d12100db370d81485cdf75e47ca",
    }),
  },
};
export const UnknownCheckpoint: Story = {};
export const SmallAdapter: Story = {
  parameters: { msw: withAdapter({ size_bytes: 31_520, rank: 1 }) },
};
export const Mobile: Story = { ...KnownCheckpoint, tags: ["mobile"] };
