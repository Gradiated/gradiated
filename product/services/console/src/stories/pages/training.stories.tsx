import type { Meta } from "@storybook/react-vite";

import { noTasksHandlers } from "@/stories/handlers";
import { Page, pageMeta, type PageStory } from "@/stories/page-story";

const meta = { ...pageMeta, title: "Pages/Training" } satisfies Meta<
  typeof Page
>;

export default meta;

export const Tasks: PageStory = { args: { path: "/tasks" } };
export const NoTasks: PageStory = {
  args: { path: "/tasks" },
  parameters: { msw: noTasksHandlers() },
};
export const NoTasksProjectStarted: PageStory = {
  args: { path: "/tasks" },
  parameters: { msw: noTasksHandlers(true) },
};
export const TaskModel: PageStory = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Model" },
};
export const TaskRuns: PageStory = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Training runs" },
};
export const TaskData: PageStory = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Data" },
};
export const TaskSettings: PageStory = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Settings" },
};
export const JudgeSelector: PageStory = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Settings", modelSelect: "Judge model" },
};
export const ComparisonSelector: PageStory = {
  args: { path: "/tasks/support-assistant" },
  parameters: {
    taskTab: "Settings",
    modelSelect: "Comparison model",
    modelSearch: "4.1",
  },
};
export const Trace: PageStory = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Data", taskDetail: "trace" },
};
export const TestResults: PageStory = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Model", taskDetail: "results" },
};
