import { expect, test } from "@playwright/test";

const workspaceId = "00000000-0000-4000-8000-000000000002";
const task = {
  id: "00000000-0000-4000-8000-000000000003",
  name: "test-task",
  base_model_id: "Qwen/Qwen3-0.6B",
  comparison_model_id: "Qwen/Qwen3-0.6B",
  judge_model_id: "Qwen/Qwen3-0.6B",
  production_version_id: null,
  training_schedule: null as string | null,
};
const evaluation = {
  judging_method: "randomized_single",
  holdout_groups: 1,
  holdout_examples: 1,
  comparison_model_id: "Qwen/Qwen3-0.6B",
  judge_model_id: "Qwen/Qwen3-0.6B",
  vs_comparison: {
    comparator_model_id: "Qwen/Qwen3-0.6B",
    win: 0,
    tie: 1,
    loss: 0,
    unresolved: 0,
  },
  cost_per_request_nano_usd: null,
  output_tokens_per_second: { fine_tuned: 30, comparison: 40 },
  error_rate: 0,
};

test("direct task reload initializes flags, edits schedules and opens held-out results", async ({
  page,
}) => {
  let schedule: string | null = null;
  let judge = task.judge_model_id;
  let rejectSchedule = true;
  let scheduleAttempts = 0;
  let releaseTask: (() => void) | undefined;
  let holdTask = true;
  let releaseTasks: (() => void) | undefined;
  let releaseContent: () => void = () => {};
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") return route.abort();

    const path = url.pathname;
    const json = (body: unknown) => route.fulfill({ json: body });
    if (path.startsWith("/flags") || path.startsWith("/decide"))
      return json({
        featureFlags: { training: true },
        featureFlagPayloads: {},
        flags: { training: { key: "training", enabled: true, variant: null } },
      });
    if (path === "/api/v1/me")
      return json({
        id: "test-user",
        email: "test@example.invalid",
        name: "Test User",
        organizations: [
          {
            id: "test-org",
            name: "Test org",
            role: "owner",
            status: "active",
            default_workspace_id: workspaceId,
          },
        ],
      });
    if (path.endsWith("/workspaces"))
      return json({
        data: [
          {
            id: workspaceId,
            organization_id: "test-org",
            name: "Test workspace",
            is_default: true,
            default_judge_model: "Qwen/Qwen3-0.6B",
            trace_capture_enabled: true,
            trace_retention_days: 90,
          },
        ],
        next_cursor: null,
      });
    if (path === "/api/v1/models")
      return json({
        data: [
          { id: "Qwen/Qwen3-0.6B", status: "unavailable" },
          { id: "jaredpalmer/kev-9b", status: "available" },
        ],
        next_cursor: null,
      });
    if (path.startsWith("/api/") && path.endsWith("/tasks/test-task")) {
      if (holdTask && route.request().method() === "GET") {
        await new Promise<void>((resolve) => {
          releaseTask = resolve;
        });
      }
      if (route.request().method() === "PATCH") {
        const patch = route.request().postDataJSON();
        if ("training_schedule" in patch) {
          scheduleAttempts++;
          schedule = patch.training_schedule;
          if (rejectSchedule) {
            rejectSchedule = false;
            return route.fulfill({
              status: 503,
              json: {
                title: "Unavailable",
                detail:
                  "Automatic training could not be updated. Retry saving the schedule.",
                status: 503,
              },
            });
          }
        }
        if ("judge_model_id" in patch) judge = patch.judge_model_id;
      }
      return json({
        ...task,
        training_schedule: schedule,
        judge_model_id: judge,
      });
    }
    if (path.endsWith("/training-runs"))
      return json({
        data: [
          {
            id: "test-run",
            stage: "succeeded",
            created_at: "2026-10-01T12:00:00Z",
            evaluation,
            dataset: { train: 10 },
            trigger: "manual",
          },
        ],
        next_cursor: null,
      });
    if (path.endsWith("/versions"))
      return json({
        data: [
          {
            id: "test-version",
            task: task.name,
            name: "test-v1",
            base_model_id: task.base_model_id,
            training_run_id: "test-run",
            created_at: "2026-10-01T12:00:00Z",
            status: "unavailable",
            is_production: false,
          },
        ],
        next_cursor: null,
      });
    if (path.endsWith("/evaluation"))
      return json([
        {
          id: "example-1",
          group: "group-1",
          fine_tuned_first: true,
          judgment: "TIE",
          fine_tuned: { text: "144", tokens: 3, seconds: 1 },
          comparison: { text: "144", tokens: 3, seconds: 1 },
        },
      ]);
    if (path.endsWith("/generations"))
      return json({
        data: [
          {
            generation_id: "generation-1",
            trace_id: "trace-1",
            started_at: "2026-10-01T12:00:00Z",
            source: "import",
            model: "Qwen/Qwen3-0.6B",
            status: 200,
            outcome: "complete",
            content_ref: "test-content",
          },
        ],
        next_cursor: null,
      });
    if (path.endsWith("/generations/generation-1")) {
      await new Promise<void>((resolve) => {
        releaseContent = resolve;
      });
      return json({
        raw: {
          request: {
            messages: [{ role: "user", content: "What is 100 + 44?" }],
          },
          response: { answer: "144" },
        },
      });
    }
    if (path.startsWith("/api/") && path.endsWith("/tasks")) {
      await new Promise<void>((resolve) => {
        releaseTasks = resolve;
      });
      return json({ data: [], next_cursor: null });
    }
    if (path.startsWith("/api/")) return json({ data: [], next_cursor: null });
    return route.continue();
  });

  await page.goto("/tasks/test-task");
  await expect(
    page.getByRole("status", { name: "Loading task", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("status", { name: "Loading task", exact: true }),
  ).toHaveText("");
  await expect.poll(() => Boolean(releaseTask)).toBe(true);
  holdTask = false;
  releaseTask!();
  expect(errors).toEqual([]);
  await expect(
    page.getByRole("heading", { level: 1, name: task.name }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { level: 1, name: task.name }),
  ).toBeVisible();
  const resolved = page.getByText("Resolved 100%", { exact: true });
  await expect(resolved).toBeVisible();
  await expect(resolved.locator("..")).toContainText("Speed");
  await expect(resolved.locator("..")).toContainText("Errors");
  await expect(page.getByText(/^Unresolved [0-9]+%$/)).toHaveCount(0);
  await page.getByRole("button", { name: "View test results" }).click();
  await expect(page.getByRole("dialog")).toContainText("Example 1");
  await expect(page.getByRole("dialog")).toContainText("Equivalent");
  await page.getByRole("button", { name: "Close", exact: true }).click();

  await page.getByRole("tab", { name: "Settings", exact: true }).click();
  await page.getByRole("combobox", { name: "Comparison model" }).click();
  await expect(
    page.getByRole("option", { name: "jaredpalmer/kev-9b" }),
  ).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("combobox", { name: "Base model" })).toHaveText(
    "Qwen/Qwen3-0.6B",
  );
  await page
    .getByRole("combobox", { name: "Judge model", exact: true })
    .click();
  await page
    .getByRole("option", { name: "openai/gpt-6-sol", exact: true })
    .click();
  await expect.poll(() => judge).toBe("openai/gpt-6-sol");
  await page.getByRole("combobox", { name: "Training schedule" }).click();
  await expect(
    page.getByRole("option", { name: "Custom cron", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("option", { name: "Scheduled", exact: true }).click();
  await page.getByRole("combobox", { name: "Training day" }).click();
  await expect(
    page.getByRole("option", { name: "Every day", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("option", { name: "Monday", exact: true }).click();
  await expect(page.getByText("Every Monday at 03:00 UTC.")).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Cron schedule" }),
  ).toHaveCount(0);
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const boxes = await Promise.all(
      [
        "Training schedule",
        "Training hour",
        "Training minute",
        "Training day",
      ].map((name) =>
        page.getByRole("combobox", { name, exact: true }).boundingBox(),
      ),
    );
    expect(boxes.every((box) => box && Math.abs(box.y - boxes[0]!.y) < 1)).toBe(
      true,
    );
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("button", { name: "Save schedule" }).click();
  await expect(page.getByRole("alert")).toContainText("Retry saving");
  await expect(page.getByRole("combobox", { name: "Training day" })).toHaveText(
    "Monday",
  );
  await expect(
    page.getByRole("combobox", { name: "Training hour" }),
  ).toHaveText("03");
  await expect(
    page.getByRole("button", { name: "Save schedule" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Save schedule" }).click();
  await expect.poll(() => scheduleAttempts).toBe(2);
  await expect.poll(() => schedule).toBe("0 3 * * MON");
  await page.reload();
  await page.getByRole("tab", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("combobox", { name: "Judge model", exact: true }),
  ).toHaveText("openai/gpt-6-sol");
  await expect(page.getByRole("combobox", { name: "Training day" })).toHaveText(
    "Monday",
  );
  await expect(
    page.getByRole("combobox", { name: "Training hour" }),
  ).toHaveText("03");
  await page.getByRole("combobox", { name: "Training minute" }).click();
  await page.getByRole("option", { name: "45", exact: true }).click();
  await page.getByRole("combobox", { name: "Training day" }).click();
  await expect(
    page.getByRole("option", { name: "Every day", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("option", { name: "Friday", exact: true }).click();
  await expect(page.getByText("Every Friday at 03:45 UTC.")).toBeVisible();
  await page.getByRole("button", { name: "Save schedule" }).click();
  await expect.poll(() => schedule).toBe("45 3 * * FRI");
  await page.reload();
  await page.getByRole("tab", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Training day" })).toHaveText(
    "Friday",
  );
  await expect(
    page.getByRole("combobox", { name: "Training minute" }),
  ).toHaveText("45");
  schedule = "0 3 * * *";
  await page.reload();
  await page.getByRole("tab", { name: "Settings", exact: true }).click();
  await expect(
    page.getByText("Choose a weekday to replace the current schedule."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save schedule" }),
  ).toBeDisabled();
  expect(schedule).toBe("0 3 * * *");
  schedule = "30 6 * * MON-FRI";
  await page.reload();
  await page.getByRole("tab", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Cron schedule" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Save schedule" }),
  ).toBeDisabled();
  expect(schedule).toBe("30 6 * * MON-FRI");
  await page.getByRole("combobox", { name: "Training schedule" }).click();
  await expect(
    page.getByRole("option", { name: "Custom cron", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("option", { name: "Manual only" }).click();
  await page.getByRole("button", { name: "Save schedule" }).click();
  await expect.poll(() => schedule).toBeNull();
  await page.getByRole("tab", { name: "Data", exact: true }).click();
  await page.getByText("trace-1", { exact: true }).click();
  await expect(
    page.getByRole("status", { name: "Loading trace content" }),
  ).toBeVisible();
  await expect(page.getByText("Loading content…", { exact: true })).toHaveCount(
    0,
  );
  releaseContent();
  await expect(page.getByRole("dialog")).toContainText("What is 100 + 44?");
  await page.goto("/tasks");
  const tasksTable = page.getByRole("region", { name: "Tasks", exact: true });
  await expect(tasksTable).toHaveAttribute("aria-busy", "true");
  await expect(tasksTable.getByRole("columnheader")).toHaveText([
    "Task",
    "Model",
    "Replaces",
    "Cost",
    "Speed",
    "Quality",
    "Last trained",
  ]);
  await expect(tasksTable.locator("tbody tr")).toHaveCount(5);
  await expect(tasksTable.locator("tbody")).toHaveText("");
  await expect.poll(() => Boolean(releaseTasks)).toBe(true);
  releaseTasks!();
  await expect(
    page.getByRole("heading", { name: "No tasks yet" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Settings", exact: true }).click();
  await expect(
    page.getByText(
      "Disable this to prevent capturing traces for training, this will disable all training functionality",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Content retention", exact: true }),
  ).toHaveText("90 days");
  expect(errors).toEqual([]);
});
