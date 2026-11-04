import { expect, test, type Page } from "@playwright/test";
import { qwen3_0_6b } from "../src/stories/base-model-configs";
import { sampleReport, sampleReportData } from "../src/stories/report-fixture";

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
    if (
      url.hostname === "huggingface.co" &&
      url.pathname.endsWith("/config.json")
    )
      return route.fulfill({ json: qwen3_0_6b });
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
const selectFiles = async (page: Page, rank = 2) => {
  const bytes = rank * 4 * 2;
  const header = Buffer.from(
    JSON.stringify({
      "base_model.model.layers.0.self_attn.q_proj.lora_A.weight": {
        dtype: "BF16",
        shape: [rank, 4],
        data_offsets: [0, bytes],
      },
      "base_model.model.layers.0.self_attn.q_proj.lora_B.weight": {
        dtype: "BF16",
        shape: [4, rank],
        data_offsets: [bytes, 2 * bytes],
      },
    }),
  );
  const prefix = Buffer.alloc(8);
  prefix.writeBigUInt64LE(BigInt(header.length));
  await page.getByLabel("Choose adapter files").setInputFiles([
    {
      name: "adapter_config.json",
      mimeType: "application/json",
      buffer: Buffer.from(
        JSON.stringify({
          peft_type: "LORA",
          r: rank,
          base_model_name_or_path: task.base_model_id,
        }),
      ),
    },
    {
      name: "adapter_model.safetensors",
      mimeType: "application/octet-stream",
      buffer: Buffer.concat([prefix, header, Buffer.alloc(2 * bytes)]),
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
    await page.getByLabel("Model name", { exact: true }).fill(task.name);
    await page.getByLabel("Version name", { exact: true }).fill(version.name);
    await selectFiles(page, mobile ? 2 : 32);
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
    expect(state.received()).not.toHaveProperty("base_model_revision");
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
  await expect(page.getByLabel("Model name", { exact: true })).toHaveCount(0);
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
    await expect(
      page.getByText("Not the checkpoint we serve", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "a".repeat(12) }),
    ).toHaveAttribute(
      "href",
      `https://huggingface.co/${task.base_model_id}/tree/${"a".repeat(40)}`,
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
    await expect(
      page.getByRole("dialog").getByText("Unknown", { exact: true }),
    ).toBeVisible();
    const submit = page
      .getByRole("dialog")
      .getByRole("button", { name: "Upload version", exact: true });
    await expect(submit).toBeEnabled();
  });
}

test("rejects an adapter above rank 32 before uploading", async ({ page }) => {
  const state = await setup(page);
  await page.goto("/tasks");
  await page.getByRole("button", { name: "Add model", exact: true }).click();
  await page.getByLabel("Choose adapter files").setInputFiles({
    name: "adapter_config.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({
        base_model_name_or_path: task.base_model_id,
        r: 33,
      }),
    ),
  });
  await expect(page.getByRole("alert")).toHaveText(
    "Adapter rank 33 exceeds the maximum supported upload rank of 32.",
  );
  await expect(
    page.getByRole("button", { name: "Create task & upload" }),
  ).toBeDisabled();
  expect(state.uploads()).toBe(0);
  expect(state.errors).toEqual([]);
});

test("shows detected adapter details without model or revision fields", async ({
  page,
}) => {
  await setup(page);
  await page.goto("/tasks");
  await page.getByRole("button", { name: "Add model", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("combobox")).toHaveCount(0);
  await expect(
    dialog.getByText("Adapter details", { exact: true }),
  ).toHaveCount(0);
  await selectFiles(page, 1);
  const detail = (label: string) =>
    dialog
      .locator("dl > div")
      .filter({ has: page.getByRole("term").getByText(label, { exact: true }) })
      .getByRole("definition");
  await expect(detail("Rank")).toHaveText("1");
  await expect(detail("Precision")).toHaveText("BF16");
  await expect(
    dialog.getByRole("img", { name: "Adapter covers 1 of 28 layers" }),
  ).toBeVisible();
  await expect(detail("Size")).toHaveText(/^\d+ KB$/);
  await expect(detail("Checkpoint")).toHaveText("Unknown");
  await expect(
    dialog.getByRole("textbox", { name: "Base checkpoint revision" }),
  ).toHaveCount(0);
});

// The task page hides its training runs, data and settings tabs while models are delivered by hand.
test.skip("model dropdown scrolls with the mouse wheel", async ({ page }) => {
  await setup(page);
  await page.route("**/api/v1/models?external=true", (route) =>
    route.fulfill({
      json: {
        data: Array.from({ length: 24 }, (_, index) => ({
          id: `test/model-${index}`,
          name: `External model ${index}`,
          status: "available",
        })),
      },
    }),
  );
  await page.goto(`/tasks/${task.name}?tab=settings`);
  await page.getByRole("tab", { name: "Settings", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Comparison model", exact: true })
    .click();
  const list = page.locator("[cmdk-list]");
  await expect(
    page.getByRole("option", { name: "External model 23" }),
  ).toHaveCount(1);
  await list.hover();
  await page.mouse.wheel(0, 500);
  await expect
    .poll(() => list.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
});

test("slugifies model and version names as they are typed", async ({
  page,
}) => {
  await setup(page);
  await page.goto("/tasks");
  await page.getByRole("button", { name: "Add model", exact: true }).click();
  const model = page.getByLabel("Model name", { exact: true });
  const version = page.getByLabel("Version name", { exact: true });
  await model.pressSequentially("Support Triage!");
  await version.pressSequentially("Support Triage V1!");
  await expect(model).toHaveValue("support-triage");
  await expect(version).toHaveValue("support-triage-v1");
});

const deliveredVersion = {
  ...version,
  status: "available",
  is_production: true,
  adapter: {
    format: "peft_lora",
    artifact_uri: "s3://test/adapter.tar.gz",
    sha256: "a".repeat(64),
    size_bytes: 1024 * 1024,
    rank: 2,
    validated_base_model_revision: "c1899de289a04d12100db370d81485cdf75e47ca",
  },
};

const versionFiles = async (
  page: Page,
  files: Record<string, string>,
  { staff = false, versions = [deliveredVersion] } = {},
) => {
  const entries = Object.entries(files).map(([name, content], index) => ({
    id: `00000000-0000-4000-8000-0000000001${String(index).padStart(2, "0")}`,
    name,
    content_type: name.endsWith(".md") ? "text/markdown" : "text/csv",
    size_bytes: content.length,
    created_at: version.created_at,
    content,
  }));
  const calls = { downloads: [] as string[], created: [] as unknown[] };
  await page.route(/\/api\/v1\/me$/, (route) =>
    route.fulfill({
      json: {
        id: "test-user",
        email: "test@example.invalid",
        email_verified: true,
        is_staff: staff,
        name: "Test User",
        organizations: [
          {
            id: "test-org",
            name: "Test workspace",
            role: "admin",
            status: "active",
            default_workspace_id: workspace,
            auto_join_domain: null,
            onboarding_completed: true,
          },
        ],
      },
    }),
  );
  await page.route(/\/tasks\/support-triage\/versions$/, (route) =>
    route.fulfill({ json: { data: versions, next_cursor: null } }),
  );
  await page.route(/\/versions\/[^/]+\/files(\/.*)?$/, (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    const file = entries.find((entry) => path.includes(entry.id));
    if (path.endsWith("/files") && method === "GET")
      return route.fulfill({
        json: { data: entries.map(({ content: _content, ...rest }) => rest) },
      });
    if (path.endsWith("/files") && method === "POST") {
      calls.created.push(route.request().postDataJSON());
      return route.fulfill({
        status: 201,
        json: {
          id: "00000000-0000-4000-8000-000000000999",
          upload_url: `${new URL(route.request().url()).origin}/storage/report`,
          expires_at: "2026-11-03T13:00:00Z",
        },
      });
    }
    if (method === "PUT")
      return route.fulfill({
        json: {
          id: "00000000-0000-4000-8000-000000000999",
          name: "notes.md",
          content_type: "text/markdown",
          size_bytes: 5,
          created_at: version.created_at,
        },
      });
    if (path.endsWith("/content") && file)
      return route.fulfill({
        json: {
          name: file.name,
          content_type: file.content_type,
          content: file.content,
        },
      });
    if (path.endsWith("/download") && file) {
      calls.downloads.push(file.name);
      return route.fulfill({
        json: {
          url: `${new URL(route.request().url()).origin}/storage/${file.name}`,
          expires_at: "2026-11-03T13:00:00Z",
        },
      });
    }
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });

  return calls;
};

test("version page renders the delivered report, its files and actions", async ({
  page,
}) => {
  await setup(page);
  const calls = await versionFiles(page, {
    "report.md": sampleReport,
    ...sampleReportData,
  });
  await page.goto(`/tasks/${task.name}/versions/${version.id}`);

  await expect(
    page.getByRole("heading", { level: 1, name: version.name }),
  ).toBeVisible();
  await expect(
    page.getByText("Refund and billing routing, round two"),
  ).toBeVisible();
  await expect(page.getByText("72%", { exact: true })).toBeVisible();
  await expect(page.getByText("Win rate by category")).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Charged twice for my October invoice" }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "On this page" }).getByRole("link"),
  ).toHaveText([
    "What changed",
    "Results",
    "Training",
    "Examples",
    "Next steps",
  ]);
  await expect(page.getByRole("button", { name: "Promoted" })).toBeDisabled();
  await expect(
    page.getByRole("link", { name: "Try in playground" }),
  ).toHaveAttribute("href", /model=support-triage/);
  await expect(page.getByRole("button", { name: "Add files" })).toHaveCount(0);
  await expect(page.getByText(/report\.md has/)).toHaveCount(0);

  await page.getByRole("button", { name: "Download metrics.csv" }).click();
  await expect.poll(() => calls.downloads).toContain("metrics.csv");
});

test("staff add files and see report problems", async ({ page }) => {
  await setup(page);
  const calls = await versionFiles(
    page,
    { "report.md": '{% callout type="tip" %}Hi{% /callout %}' },
    { staff: true },
  );
  await page.goto(`/tasks/${task.name}/versions/${version.id}`);

  await expect(page.getByText("report.md has 1 problem")).toBeVisible();
  await page.getByLabel("Add files").setInputFiles({
    name: "notes.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("hello"),
  });
  await expect(page.getByText("notes.md added.")).toBeVisible();
  expect(calls.created).toEqual([
    { name: "notes.md", size_bytes: 5, content_type: "text/markdown" },
  ]);
});

test("version page without a report offers promotion", async ({ page }) => {
  await setup(page);
  await versionFiles(
    page,
    {},
    { versions: [{ ...deliveredVersion, is_production: false }] },
  );
  await page.goto(`/tasks/${task.name}/versions/${version.id}`);

  await expect(page.getByText("No report for this version yet")).toBeVisible();
  await page.getByRole("button", { name: "Promote", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
});
