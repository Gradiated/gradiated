import type { Preview } from "@storybook/react-vite";
import { setupWorker } from "msw/browser";
import { mswLoader } from "msw-storybook-addon/csf3";

import "../src/styles.css";
import { handlers } from "../src/stories/handlers";

const preview: Preview = {
  parameters: { layout: "fullscreen", msw: handlers },
  // Screenshot capture waits for this marker, set after any play function.
  afterEach: ({ canvasElement }) => {
    canvasElement.dataset.storyPlayed = "true";
  },
  loaders: [
    mswLoader(async () => {
      const worker = setupWorker();
      await worker.start({ onUnhandledRequest: "error", quiet: true });

      return worker;
    }),
  ],
};

export default preview;
