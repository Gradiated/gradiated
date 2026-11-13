import type { Meta } from "@storybook/react-vite";

import { Page, pageMeta, type PageStory } from "@/stories/page-story";
import {
  playgroundHandlers,
  playgroundUnavailableHandlers,
} from "@/stories/handlers";

const meta = { ...pageMeta, title: "Pages/Playground" } satisfies Meta<
  typeof Page
>;

export default meta;

export const Default: PageStory = {
  args: { path: "/playground" },
  parameters: { msw: playgroundHandlers },
};
export const Conversation: PageStory = {
  args: { path: "/playground" },
  parameters: { playground: "conversation", msw: playgroundHandlers },
};
export const Unavailable: PageStory = {
  args: { path: "/playground" },
  tags: ["request-failure"],
  parameters: { playground: "unavailable", msw: playgroundUnavailableHandlers },
};
export const ModelPicker: PageStory = {
  args: { path: "/playground" },
  parameters: { playground: "models", msw: playgroundHandlers },
};
export const McpServers: PageStory = {
  args: { path: "/playground" },
  parameters: { playground: "mcp", msw: playgroundHandlers },
};
