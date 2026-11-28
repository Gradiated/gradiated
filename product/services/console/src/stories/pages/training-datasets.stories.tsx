import type { Meta } from "@storybook/react-vite";
import { userEvent, within } from "storybook/test";

import { gradStoryHandlers } from "@/stories/grad-handlers";
import { settle } from "@/stories/grad-story";
import { Page, pageMeta, type PageStory } from "@/stories/page-story";

const meta = {
  ...pageMeta,
  title: "Pages/Training datasets",
  parameters: { msw: gradStoryHandlers() },
  play: async ({ canvasElement }) => settle(canvasElement),
} satisfies Meta<typeof Page>;

export default meta;

const datasetPath = "/training/datasets/support-traces";

export const Datasets: PageStory = { args: { path: "/training/datasets" } };

export const Empty: PageStory = {
  args: { path: "/training/datasets" },
  parameters: { msw: gradStoryHandlers({ datasets: [] }) },
};

export const ImportFile: PageStory = {
  args: { path: "/training/datasets" },
  play: async ({ canvasElement }) => {
    await settle(canvasElement);
    await userEvent.click(
      await within(canvasElement).findByRole("button", { name: "Import file" }),
    );
    const body = within(canvasElement.ownerDocument.body);
    await userEvent.upload(
      await body.findByLabelText("File"),
      new File(['{"messages":[]}\n'], "Support Traces.jsonl", {
        type: "application/jsonl",
      }),
    );
    await body.findByDisplayValue("support-traces");
  },
};

export const Records: PageStory = { args: { path: datasetPath } };

export const Versions: PageStory = {
  args: { path: `${datasetPath}?tab=versions` },
};

export const Sources: PageStory = {
  args: { path: `${datasetPath}?tab=sources` },
  play: async ({ canvasElement }) => {
    await settle(canvasElement);
    await within(canvasElement).findByText(/personal API key was revoked/);
  },
};

export const Imports: PageStory = {
  args: { path: `${datasetPath}?tab=imports` },
};
