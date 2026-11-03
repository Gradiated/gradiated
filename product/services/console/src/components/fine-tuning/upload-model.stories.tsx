import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, within, waitFor } from "storybook/test";
import { delay, http, HttpResponse } from "msw";
import type { components } from "@/api/schema";
import { StoryPage } from "@/stories/story-page";
import { handlers } from "@/stories/handlers";

const task = {
  id: "00000000-0000-4000-8000-000000000003",
  name: "support-triage",
  base_model_id: "Qwen/Qwen3-0.6B",
  comparison_model_id: null,
  production_version_id: null,
  judge_model_id: "openai/gpt-6.1-sol",
  training_schedule: null,
} satisfies components["schemas"]["Task"];
const version = {
  id: "00000000-0000-4000-8000-000000000004",
  task: task.name,
  name: "support-triage-v1",
  base_model_id: task.base_model_id,
  training_run_id: null,
  adapter: {
    format: "peft_lora",
    artifact_uri: "s3://storybook/runs/adapter.tar.gz",
    sha256: "a".repeat(64),
    size_bytes: 24 * 1024 * 1024,
    rank: 2,
    base_model_revision: "a".repeat(40),
  },
  status: "unavailable",
  is_production: false,
  created_at: "2026-10-01T12:00:00Z",
} satisfies components["schemas"]["TaskVersion"];

type Phase =
  | "ready"
  | "uploading"
  | "validating"
  | "upload-error"
  | "validation-error"
  | "models-error";
const uploadHandlers = ({
  phase = "ready",
  existing = false,
  published = false,
}: { phase?: Phase; existing?: boolean; published?: boolean } = {}) => {
  let completed = published;
  return [
    ...(phase === "models-error"
      ? [
          http.get("/api/v1/models", () =>
            HttpResponse.json(
              { detail: "Model catalog is temporarily unavailable." },
              { status: 503 },
            ),
          ),
        ]
      : []),
    http.get("/api/v1/workspaces/:workspaceId/tasks", () =>
      HttpResponse.json({
        data:
          existing || completed
            ? [
                {
                  ...task,
                  latest_run: null,
                  latest_version: completed ? version : null,
                },
              ]
            : [],
      }),
    ),
    http.get("/api/v1/workspaces/:workspaceId/tasks/:task", () =>
      HttpResponse.json(task),
    ),
    http.get("/api/v1/workspaces/:workspaceId/tasks/:task/versions", () =>
      HttpResponse.json({ data: completed ? [version] : [] }),
    ),
    http.get("/api/v1/workspaces/:workspaceId/training-runs", () =>
      HttpResponse.json({ data: [] }),
    ),
    http.post("/api/v1/workspaces/:workspaceId/model-uploads", () =>
      HttpResponse.json(
        {
          id: version.id,
          config_url: new URL(
            "/storybook-adapter-files/config",
            location.origin,
          ).href,
          weights_url: new URL(
            "/storybook-adapter-files/weights",
            location.origin,
          ).href,
          expires_at: "2026-10-02T13:00:00Z",
        },
        { status: 201 },
      ),
    ),
    http.put("/storybook-adapter-files/:file", async () => {
      if (phase === "uploading") await delay("infinite");
      return new HttpResponse(null, {
        status: phase === "upload-error" ? 500 : 200,
      });
    }),
    http.put(
      "/api/v1/workspaces/:workspaceId/model-uploads/:uploadId/version",
      async () => {
        if (phase === "validating") await delay("infinite");
        if (phase === "validation-error")
          return HttpResponse.json(
            {
              detail:
                "Invalid LoRA adapter. The tensor rank does not match the config.",
            },
            { status: 409 },
          );

        completed = true;
        return HttpResponse.json(version);
      },
    ),
    ...handlers,
  ];
};

const openUpload = async (canvasElement: HTMLElement, existing = false) => {
  const canvas = within(canvasElement);
  if (!existing)
    await canvas.findByRole(
      "heading",
      { name: "No tasks yet" },
      { timeout: 10000 },
    );
  const trigger = await canvas.findByRole(
    "button",
    { name: existing ? "Upload version" : "Add model" },
    { timeout: 10000 },
  );
  await waitFor(() => expect(trigger).toBeEnabled());
  await userEvent.click(trigger);
  const body = within(canvasElement.ownerDocument.body);
  return within(await body.findByRole("dialog"));
};
const selectFiles = async (
  dialog: ReturnType<typeof within>,
  configOnly = false,
) => {
  const config = new File(
    [
      JSON.stringify({
        base_model_name_or_path: task.base_model_id,
        revision: "a".repeat(40),
      }),
    ],
    "adapter_config.json",
    { type: "application/json" },
  );
  const weights = new File([new Uint8Array(1024)], "adapter_model.safetensors");
  await userEvent.upload(
    dialog.getByLabelText("Choose adapter files"),
    configOnly ? [config] : [config, weights],
  );
  await dialog.findByText("adapter_config.json");
};
const fillUpload = async (canvasElement: HTMLElement, existing = false) => {
  const dialog = await openUpload(canvasElement, existing);
  if (!existing)
    await userEvent.type(dialog.getByLabelText("Task name"), task.name);
  await userEvent.type(dialog.getByLabelText("Version name"), version.name);
  await selectFiles(dialog);
  await waitFor(() =>
    expect(
      dialog.getByRole("button", {
        name: existing ? "Upload version" : "Create task & upload",
      }),
    ).toBeEnabled(),
  );
  return dialog;
};

const meta = {
  title: "Training/Model upload",
  component: StoryPage,
  render: (args) => <StoryPage key={args.path} {...args} />,
  args: { path: "/tasks" },
  parameters: { msw: uploadHandlers() },
} satisfies Meta<typeof StoryPage>;
export default meta;
type Story = StoryObj<typeof meta>;

export const NewTaskEmpty: Story = {
  play: async ({ canvasElement }) => {
    const dialog = await openUpload(canvasElement);
    await expect(
      dialog.getByRole("button", { name: "Create task & upload" }),
    ).toBeDisabled();
  },
};
export const ExistingTaskEmpty: Story = {
  args: { path: `/tasks/${task.name}` },
  parameters: { msw: uploadHandlers({ existing: true }) },
  play: async ({ canvasElement }) => {
    const dialog = await openUpload(canvasElement, true);
    await expect(dialog.queryByLabelText("Task name")).toBeNull();
  },
};
export const ConfigOnly: Story = {
  play: async ({ canvasElement }) => {
    const dialog = await openUpload(canvasElement);
    await selectFiles(dialog, true);
    await expect(
      dialog.getByRole("button", { name: "Create task & upload" }),
    ).toBeDisabled();
  },
};
export const FilesSelected: Story = {
  play: async ({ canvasElement }) => {
    await fillUpload(canvasElement);
  },
};
export const Uploading: Story = {
  parameters: { msw: uploadHandlers({ phase: "uploading" }) },
  play: async ({ canvasElement }) => {
    const dialog = await fillUpload(canvasElement);
    await userEvent.click(
      dialog.getByRole("button", { name: "Create task & upload" }),
    );
    await expect(
      await dialog.findByRole("button", { name: "Uploading files…" }),
    ).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeDisabled();
  },
};
export const Validating: Story = {
  parameters: { msw: uploadHandlers({ phase: "validating" }) },
  play: async ({ canvasElement }) => {
    const dialog = await fillUpload(canvasElement);
    await userEvent.click(
      dialog.getByRole("button", { name: "Create task & upload" }),
    );
    await expect(
      await dialog.findByRole("button", { name: "Validating adapter…" }),
    ).toBeDisabled();
  },
};
export const UnsupportedFile: Story = {
  play: async ({ canvasElement }) => {
    const dialog = await openUpload(canvasElement);
    await userEvent.upload(
      dialog.getByLabelText("Choose adapter files"),
      new File(["unsupported"], "model.bin"),
      { applyAccept: false },
    );
    await expect(await dialog.findByRole("alert")).toHaveTextContent(
      /Choose adapter_config.json/,
    );
  },
};
export const InvalidConfig: Story = {
  play: async ({ canvasElement }) => {
    const dialog = await openUpload(canvasElement);
    await userEvent.upload(
      dialog.getByLabelText("Choose adapter files"),
      new File(["invalid JSON"], "adapter_config.json", {
        type: "application/json",
      }),
    );
    await expect(await dialog.findByRole("alert")).toHaveTextContent(
      /valid JSON/,
    );
    await expect(
      dialog.queryByText("adapter_config.json", { exact: true }),
    ).toBeNull();
  },
};
export const UploadError: Story = {
  tags: ["request-failure"],
  parameters: { msw: uploadHandlers({ phase: "upload-error" }) },
  play: async ({ canvasElement }) => {
    const dialog = await fillUpload(canvasElement);
    await userEvent.click(
      dialog.getByRole("button", { name: "Create task & upload" }),
    );
    await expect(await dialog.findByRole("alert")).toHaveTextContent(
      /File upload failed/,
    );
    await expect(
      dialog.getByRole("button", { name: "Create task & upload" }),
    ).toBeEnabled();
  },
};
export const ValidationError: Story = {
  tags: ["request-failure"],
  parameters: { msw: uploadHandlers({ phase: "validation-error" }) },
  play: async ({ canvasElement }) => {
    const dialog = await fillUpload(canvasElement);
    await userEvent.click(
      dialog.getByRole("button", { name: "Create task & upload" }),
    );
    await expect(await dialog.findByRole("alert")).toHaveTextContent(
      /tensor rank/,
    );
  },
};
export const ModelCatalogError: Story = {
  tags: ["request-failure"],
  parameters: { msw: uploadHandlers({ phase: "models-error" }) },
  play: async ({ canvasElement }) => {
    const dialog = await openUpload(canvasElement);
    await expect(
      await dialog.findByRole("button", { name: "Try again" }),
    ).toBeVisible();
    await expect(
      dialog.getByRole("combobox", { name: "Base model" }),
    ).toBeDisabled();
  },
};
export const UploadedAwaitingQualification: Story = {
  play: async ({ canvasElement }) => {
    const dialog = await fillUpload(canvasElement);
    await userEvent.click(
      dialog.getByRole("button", { name: "Create task & upload" }),
    );
    const body = within(canvasElement.ownerDocument.body);
    await waitFor(() => expect(body.queryByRole("dialog")).toBeNull());
    const canvas = within(canvasElement);
    await expect(
      await canvas.findByText(/Awaiting serving qualification/),
    ).toBeVisible();
    await expect(canvas.getByRole("button", { name: "Use" })).toBeDisabled();
    await expect(
      canvas.getByRole("button", { name: "Promote" }),
    ).toBeDisabled();
  },
};
export const FilesSelectedMobile: Story = {
  ...FilesSelected,
  tags: ["mobile"],
  globals: { viewport: { value: "mobile1", isRotated: false } },
};
export const UploadedMobile: Story = {
  args: { path: `/tasks/${task.name}` },
  tags: ["mobile"],
  parameters: { msw: uploadHandlers({ existing: true, published: true }) },
  globals: { viewport: { value: "mobile1", isRotated: false } },
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByText(/Awaiting serving qualification/),
    ).toBeVisible();
  },
};
