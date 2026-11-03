import { expect, test, type Page } from "@playwright/test";

test.setTimeout(60_000);
test.use({ actionTimeout: 20_000 });

const workspace = "00000000-0000-4000-8000-000000000002";
const task = {
  id: "00000000-0000-4000-8000-000000000003",
  name: "support-triage",
  base_model_id: "Qwen/Qwen3-0.6B",
  comparison_model_id: null,
  judge_model_id: "openai/gpt-6.1-sol",
  production_version_id: null,
  training_schedule: null,
};
const version = {
  id: "00000000-0000-4000-8000-000000000004",
  task: task.name,
  name: "support-triage-v1",
  base_model_id: task.base_model_id,
  training_run_id: null,
  status: "unavailable",
  is_production: false,
  created_at: "2026-11-03T12:00:00Z",
  adapter: { rank: 2 },
};
const setup = async (page: Page, role = "admin") => {
  let uploaded = false;
  let received: Record<string, unknown> | undefined;
  let uploads = 0;
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error")
      errors.push(`${message.text()} (${message.location().url})`);
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    const path = url.pathname;
    const json = (body: unknown) => route.fulfill({ json: body });
    if (path.startsWith("/array/"))
      return route.fulfill({ contentType: "application/javascript", body: "" });
    if (path.startsWith("/flags") || path.startsWith("/decide"))
      return json({
        featureFlags: { training: true },
        flags: { training: { key: "training", enabled: true, variant: null } },
      });
    if (!path.startsWith("/api/") && !path.startsWith("/storage/"))
      return route.continue();
    if (path === "/api/v1/me")
      return json({
        id: "test-user",
        email: "test@example.invalid",
        name: "Test User",
        organizations: [
          {
            id: "test-org",
            name: "Test workspace",
            role,
            status: "active",
            default_workspace_id: workspace,
            auto_join_domain: null,
            onboarding_completed: true,
          },
        ],
      });
    if (path.endsWith("/workspaces"))
      return json({
        data: [
          {
            id: workspace,
            organization_id: "test-org",
            name: "Test workspace",
            is_default: true,
            default_judge_model: task.judge_model_id,
            trace_capture_enabled: true,
            trace_retention_days: 90,
          },
        ],
        next_cursor: null,
      });
    if (path === "/api/v1/models")
      return json({
        data: [
          { id: task.base_model_id, name: "Qwen3 0.6B", status: "unavailable" },
        ],
      });
    if (path.endsWith("/model-uploads")) {
      received = route.request().postDataJSON();
      return json({
        id: version.id,
        config_url: `${url.origin}/storage/config`,
        weights_url: `${url.origin}/storage/weights`,
        expires_at: "2026-11-03T13:00:00Z",
      });
    }
    if (path.startsWith("/storage/")) {
      uploads++;
      return route.fulfill({ status: 200 });
    }
    if (path.endsWith(`/model-uploads/${version.id}/version`)) {
      uploaded = true;
      return json(version);
    }
    if (path.endsWith("/tasks"))
      return json({
        data: [
          {
            ...task,
            latest_run: null,
            latest_version: uploaded ? version : null,
          },
        ],
      });
    if (path.endsWith(`/tasks/${task.name}`)) return json(task);
    if (path.endsWith("/versions"))
      return json({ data: uploaded ? [version] : [] });
    if (path.endsWith("/training-runs") || path.endsWith("/generations"))
      return json({ data: [], next_cursor: null });
    if (path.startsWith("/api/")) return json({ data: [] });
    return route.continue();
  });
  return { received: () => received, uploads: () => uploads, errors };
};
const selectFiles = async (page: Page) => {
  await page.getByLabel("Choose adapter files").setInputFiles([
    {
      name: "adapter_config.json",
      mimeType: "application/json",
      buffer: Buffer.from(
        JSON.stringify({
          peft_type: "LORA",
          base_model_name_or_path: task.base_model_id,
        }),
      ),
    },
    {
      name: "adapter_model.safetensors",
      mimeType: "application/octet-stream",
      buffer: Buffer.alloc(32, 1),
    },
  ]);
};

for (const mobile of [false, true]) {
  test(`creates a task with an uploaded model on ${mobile ? "mobile" : "desktop"}`, async ({
    page,
  }) => {
    await page.setViewportSize(
      mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
    );
    const state = await setup(page);
    await page.goto("/tasks");
    await page.getByRole("button", { name: "Add model", exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Create task & upload" }),
    ).toBeDisabled();
    await page.getByLabel("Task name", { exact: true }).fill(task.name);
    await page.getByLabel("Version name", { exact: true }).fill(version.name);
    await selectFiles(page);
    await page.getByLabel("Base checkpoint revision").fill("a".repeat(40));
    await expect(page.getByText("Adapter files ready")).toBeVisible();
    const dialog = page.getByRole("dialog");
    const box = await dialog.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(mobile ? 390 : 1440);
    await page.screenshot({
      path: `../../../.agents/runtime/model-upload-${mobile ? "mobile" : "desktop"}.png`,
    });
    await page.getByRole("button", { name: "Create task & upload" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(
      page.getByText("Awaiting serving qualification", { exact: false }),
    ).toBeVisible();
    expect(state.received()).toMatchObject({
      create_task: true,
      task: task.name,
      name: version.name,
      base_model_id: task.base_model_id,
    });
    expect(state.uploads()).toBe(2);
    expect(state.errors).toEqual([]);
  });
}

test("uploads another version from an existing task and rejects unsupported files", async ({
  page,
}) => {
  const state = await setup(page);
  await page.goto(`/tasks/${task.name}`);
  await page
    .getByRole("button", { name: "Upload version", exact: true })
    .click();
  await expect(page.getByLabel("Task name", { exact: true })).toHaveCount(0);
  await page.getByLabel("Choose adapter files").setInputFiles({
    name: "model.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("invalid"),
  });
  await expect(page.getByRole("alert")).toContainText(
    "Choose adapter_config.json",
  );
  await selectFiles(page);
  await page.getByLabel("Version name", { exact: true }).fill(version.name);
  await page.getByLabel("Base checkpoint revision").fill("b".repeat(40));
  await page
    .getByRole("button", { name: "Upload version", exact: true })
    .last()
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(state.received()).toMatchObject({
    create_task: false,
    task: task.name,
  });
});

test("workspace members cannot upload models", async ({ page }) => {
  await setup(page, "member");
  await page.goto("/tasks");
  await expect(
    page.getByRole("button", { name: "Add model", exact: true }),
  ).toBeDisabled();
  await page.goto(`/tasks/${task.name}`);
  await expect(
    page.getByRole("button", { name: "Upload version", exact: true }),
  ).toBeDisabled();
});

for (const revision of [undefined, null, "main"]) {
  test(`replacing config clears the stale revision when the next revision is ${String(revision)}`, async ({
    page,
  }) => {
    await setup(page);
    await page.goto(`/tasks/${task.name}`);
    await page
      .getByRole("button", { name: "Upload version", exact: true })
      .click();
    await page.getByLabel("Version name", { exact: true }).fill(version.name);
    const picker = page.getByLabel("Choose adapter files");
    await picker.setInputFiles([
      {
        name: "adapter_config.json",
        mimeType: "application/json",
        buffer: Buffer.from(
          JSON.stringify({
            base_model_name_or_path: task.base_model_id,
            revision: "a".repeat(40),
          }),
        ),
      },
      {
        name: "adapter_model.safetensors",
        mimeType: "application/octet-stream",
        buffer: Buffer.alloc(32, 1),
      },
    ]);
    await expect(page.getByLabel("Base checkpoint revision")).toHaveValue(
      "a".repeat(40),
    );
    await picker.setInputFiles({
      name: "adapter_config.json",
      mimeType: "application/json",
      buffer: Buffer.from(
        JSON.stringify({
          base_model_name_or_path: task.base_model_id,
          revision,
        }),
      ),
    });
    await expect(page.getByLabel("Base checkpoint revision")).toHaveValue("");
    const submit = page
      .getByRole("dialog")
      .getByRole("button", { name: "Upload version", exact: true });
    await expect(submit).toBeDisabled();
    await page.getByLabel("Base checkpoint revision").fill("b".repeat(40));
    await expect(submit).toBeEnabled();
  });
}
