import NiceModal from "@ebay/nice-modal-react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { userEvent, within } from "storybook/test";

import { CreateNameDialog } from "./create-name-dialog";

const meta = {
  title: "Pages/General/Blocks/Create name dialog",
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const story = (submit: (name: string) => Promise<void>): Story => ({
  render: () => (
    <NiceModal.Provider>
      <CreateNameDialog
        id="create-name"
        defaultVisible
        title="Create a workspace"
        label="Workspace name"
        placeholder="Production"
        submitLabel="Create workspace"
        emptyMessage="Enter a workspace name."
        submit={submit}
      />
    </NiceModal.Provider>
  ),
});

const submitWith = async (name: string) => {
  const body = within(document.body);
  if (name)
    await userEvent.type(await body.findByLabelText("Workspace name"), name);
  await userEvent.click(
    await body.findByRole("button", { name: "Create workspace" }),
  );
};

export const Empty = story(async () => undefined);

export const ValidationError: Story = {
  ...story(async () => undefined),
  play: async () => {
    await submitWith("");
    await within(document.body).findByText("Enter a workspace name.");
  },
};

export const Submitting: Story = {
  ...story(() => new Promise(() => undefined)),
  play: async () => submitWith("Staging"),
};

export const RequestFailed: Story = {
  ...story(async () => {
    throw new globalThis.Error("A workspace with this name already exists.");
  }),
  tags: ["request-failure"],
  play: async () => {
    await submitWith("Production");
    await within(document.body).findByText(
      "A workspace with this name already exists.",
    );
  },
};
