import type { Meta, StoryObj } from "@storybook/react-vite";
import { toast } from "sonner";
import { userEvent, within } from "storybook/test";

import { Canvas } from "@/stories/states";
import { Button } from "./button";
import { Toaster } from "./sonner";

const meta = { title: "Components/Toast" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const story = (show: () => void, text: string): Story => ({
  render: () => (
    <Canvas>
      <Button variant="outline" onClick={show}>
        Show toast
      </Button>
      <Toaster />
    </Canvas>
  ),
  play: async ({ canvasElement }) => {
    await userEvent.click(
      within(canvasElement).getByRole("button", { name: "Show toast" }),
    );
    await within(document.body).findByText(text);
  },
});

export const Success = story(
  () => toast.success("Auto top-up updated."),
  "Auto top-up updated.",
);
export const SuccessWithDescription = story(
  () =>
    toast.success("Model version uploaded", {
      description:
        "Adapter compatibility checks passed. Your model version is saved.",
    }),
  "Model version uploaded",
);
export const Error = story(
  () => toast.error("The version could not be promoted."),
  "The version could not be promoted.",
);
export const ErrorWithAction = story(
  () =>
    toast.error("Payment declined", {
      description: "Your card was declined.",
      action: { label: "Use another card", onClick: () => undefined },
    }),
  "Payment declined",
);
export const Info = story(
  () =>
    toast.info(
      "Payment is processing. Your balance updates when it completes.",
    ),
  "Payment is processing. Your balance updates when it completes.",
);
export const Warning = story(
  () => toast.warning("Your balance is below $5."),
  "Your balance is below $5.",
);
export const Loading = story(
  () => toast.loading("Uploading adapter…"),
  "Uploading adapter…",
);
export const Stacked = story(() => {
  toast.success("API key created.");
  toast.error("The request failed.");
  toast.info("Invitation sent to sam@acme.com.");
}, "Invitation sent to sam@acme.com.");
