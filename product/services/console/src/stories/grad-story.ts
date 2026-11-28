import { expect, waitFor, within } from "storybook/test";

// Like the shared page play function, without its alert check (failure states
// show alerts), and also waiting for this feature's loading markers.
export const settle = async (canvasElement: HTMLElement) => {
  await within(canvasElement).findByRole(
    "heading",
    { level: 1 },
    { timeout: 10000 },
  );
  await waitFor(
    () => {
      const body = canvasElement.ownerDocument.body;

      expect(
        canvasElement.querySelector("[data-story-ready=true]"),
      ).not.toBeNull();
      expect(
        body.querySelector(
          '.animate-pulse, [aria-busy=true], [aria-label^="Loading"]',
        ),
      ).toBeNull();
    },
    { timeout: 10000 },
  );
};
