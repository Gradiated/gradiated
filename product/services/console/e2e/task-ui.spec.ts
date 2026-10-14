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
  let comparison = task.comparison_model_id;
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
            auto_join_domain: null,
            onboarding_completed: true,
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
        data:
          new URL(route.request().url()).searchParams.get("external") === "true"
            ? [
                {
                  id: "openai/gpt-6.1-sol",
                  name: "GPT-6.1 Sol",
                  status: "available",
                },
                {
                  id: "openai/gpt-6-sol",
                  name: "GPT-6 Sol",
                  status: "available",
                },
                {
                  id: "openai/gpt-4.1-mini",
                  name: "GPT-4.1 Mini",
                  status: "available",
                },
              ]
            : [
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
        if ("comparison_model_id" in patch)
          comparison = patch.comparison_model_id;
      }
      return json({
        ...task,
        training_schedule: schedule,
        judge_model_id: judge,
        comparison_model_id: comparison,
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
  await expect(page.getByRole("option", { name: "Kev 9B" })).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "Search comparison model" })
    .fill("4.1");
  await expect(page.getByRole("option", { name: "GPT-6.1 Sol" })).toHaveCount(
    0,
  );
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect.poll(() => comparison).toBe("openai/gpt-4.1-mini");
  await expect(page.getByRole("combobox", { name: "Base model" })).toHaveText(
    "Qwen3 0.6B",
  );
  await page
    .getByRole("combobox", { name: "Judge model", exact: true })
    .click();
  await expect(
    page.getByRole("option", { name: "GPT-4.1 Mini", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Search judge model" })
    .fill("GPT-6 Sol");
  await page.getByRole("option", { name: "GPT-6 Sol", exact: true }).click();
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
  ).toHaveText("GPT-6 Sol");
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

for (const initialRows of [0, 35]) {
  test(`Data automatically loads older traces with ${initialRows} initial rows and retries failures`, async ({
    page,
  }) => {
    const requests: (string | null)[] = [];
    let releaseOlder!: () => void;
    const older = new Promise<void>((resolve) => {
      releaseOlder = resolve;
    });
    let failOldest = true;
    let linkMode = false;
    const row = (index: number) => ({
      generation_id: `generation-${index}`,
      trace_id: `trace-${index}`,
      started_at: "2026-10-01T12:00:00Z",
      source: "import",
      model: "Qwen/Qwen3-0.6B",
      status: 200,
      outcome: "complete",
      content_ref: `content-${index}`,
    });
    await page.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.hostname !== "127.0.0.1") return route.abort();

      const path = url.pathname;
      const json = (body: unknown) => route.fulfill({ json: body });
      if (path.startsWith("/flags") || path.startsWith("/decide"))
        return json({
          featureFlags: { training: true },
          featureFlagPayloads: {},
          flags: {
            training: { key: "training", enabled: true, variant: null },
          },
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
              auto_join_domain: null,
              onboarding_completed: true,
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
            },
          ],
          next_cursor: null,
        });
      if (path.startsWith("/api/") && path.endsWith("/tasks/test-task"))
        return json(task);
      if (path.endsWith("/generations/generation-100"))
        return json({
          raw: { request: { prompt: "Shared trace prompt" }, response: {} },
        });
      if (path.endsWith("/generations/generation-101"))
        return json({
          raw: { request: { prompt: "Earlier trace prompt" }, response: {} },
        });
      if (path.endsWith("/generations")) {
        expect(url.pathname).toBe(
          `/api/v1/workspaces/${workspaceId}/generations`,
        );
        expect(url.searchParams.get("task_id")).toBe(task.name);
        const cursor = url.searchParams.get("cursor");
        requests.push(cursor);

        if (cursor === "older") {
          await older;
          return json({ data: [], next_cursor: "oldest" });
        }
        if (cursor === "oldest") {
          if (failOldest)
            return route.fulfill({
              status: 503,
              json: { title: "Storage unavailable", status: 503 },
            });

          return json({
            data: [row(100)],
            next_cursor: linkMode ? "earlier" : null,
          });
        }
        if (cursor === "earlier")
          return json({
            data: [
              {
                ...row(101),
                trace_id: "trace-100",
                started_at: "2026-10-01T11:00:00Z",
              },
            ],
            next_cursor: null,
          });

        return json({
          data: Array.from({ length: initialRows }, (_, index) => row(index)),
          next_cursor: "older",
        });
      }
      if (path.startsWith("/api/"))
        return json({ data: [], next_cursor: null });

      return route.continue();
    });

    await page.goto("/tasks/test-task");
    await page.getByRole("tab", { name: "Data", exact: true }).click();
    await expect(
      page.getByText("Captured requests and responses for this task.", {
        exact: true,
      }),
    ).toBeVisible();
    const traces = page.getByRole("region", { name: "Traces" });
    await expect(traces.getByRole("button")).toHaveCount(initialRows);
    await expect(
      page.getByRole("button", { name: "Load older content" }),
    ).toHaveCount(0);
    if (initialRows) {
      expect(requests).toEqual([null]);
      await traces.getByRole("row").last().scrollIntoViewIfNeeded();
    } else {
      await expect(
        page.getByText(/Scroll to check earlier hours/),
      ).toBeVisible();
      await page.waitForTimeout(300);
      expect(requests).toEqual([null]);
      await page.mouse.wheel(0, 400);
    }

    const loading = page.getByRole("status", { name: "Loading older content" });
    await expect(loading).toBeVisible();
    await loading.scrollIntoViewIfNeeded();
    expect(requests).toEqual([null, "older"]);
    releaseOlder();
    await expect(loading).toHaveCount(0);
    await page.waitForTimeout(300);
    expect(requests).toEqual([null, "older"]);
    await page.mouse.wheel(0, 400);
    await expect(page.getByRole("alert")).toContainText(
      "Could not load traces",
      {
        timeout: 20_000,
      },
    );
    await expect(traces.getByRole("button")).toHaveCount(initialRows);
    const failedRequestCount = requests.length;
    await page.getByRole("button", { name: "Retry", exact: true }).focus();
    expect(requests).toHaveLength(failedRequestCount);
    failOldest = false;
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(traces.getByRole("button")).toHaveCount(initialRows + 1);
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(loading).toHaveCount(0);
    await traces.getByRole("row").last().scrollIntoViewIfNeeded();
    expect(requests).toHaveLength(failedRequestCount + 1);
    expect(requests.slice(-2)).toEqual(["oldest", "oldest"]);

    await page.getByRole("button", { name: "trace-100", exact: true }).click();
    await expect(page).toHaveURL(/traceId=trace-100/);
    const dialog = page.getByRole("dialog", { name: "Trace", exact: true });
    await expect(dialog.getByText(/Shared trace prompt/)).toBeVisible();
    await expect(dialog).not.toContainText("Generations from the loaded pages");
    await expect(dialog).not.toContainText("HTTP 200");
    await expect(dialog).not.toContainText("generation-100");
    await page.goBack();
    await expect(dialog).toHaveCount(0);
    await page.goForward();
    await expect(dialog).toBeVisible();
    requests.length = 0;
    linkMode = true;
    await page.reload();
    await expect(
      page.getByRole("tab", { name: "Data", exact: true, includeHidden: true }),
    ).toHaveAttribute("aria-selected", "true");
    await expect(dialog.getByText(/Shared trace prompt/)).toBeVisible();
    await dialog
      .getByRole("list", { name: "Trace timeline" })
      .scrollIntoViewIfNeeded();
    await dialog.evaluate((element) => {
      element.scrollTop = element.scrollHeight;
    });
    await expect(dialog.getByText(/Earlier trace prompt/)).toBeVisible();
    await expect(dialog.getByRole("listitem")).toHaveCount(2);
    expect(requests).toEqual([null, "older", "oldest", "earlier"]);
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(page).not.toHaveURL(/traceId=/);
    await expect(
      page.getByRole("tab", { name: "Data", exact: true, includeHidden: true }),
    ).toHaveAttribute("aria-selected", "true");
  });
}

test("Billing loads 100 transactions at a time with skeleton rows and retry", async ({
  page,
}) => {
  const requests: (string | null)[] = [];
  let fail = true;
  let releasePage!: () => void;
  const held = new Promise<void>((resolve) => {
    releasePage = resolve;
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") return route.abort();

    const path = url.pathname;
    const json = (body: unknown) => route.fulfill({ json: body });
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
            auto_join_domain: null,
            onboarding_completed: true,
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
          },
        ],
        next_cursor: null,
      });
    if (path.endsWith("/billing") && path.startsWith("/api/"))
      return json({ balance: "100000000000", mode: "prepaid" });
    if (path.endsWith("/balance-transactions")) {
      expect(path).toBe("/api/v1/organizations/test-org/balance-transactions");
      expect(url.searchParams.get("limit")).toBe("100");
      const cursor = url.searchParams.get("cursor");
      requests.push(cursor);
      if (cursor) {
        await held;
        if (fail)
          return route.fulfill({
            status: 503,
            json: { detail: "Unavailable" },
          });
      }
      return json({
        data: Array.from({ length: cursor ? 3 : 100 }, (_, index) => ({
          id: `transaction-${cursor ? 100 + index : index}`,
          type: "credit",
          amount: "1000000000",
          balance_after: "100000000000",
          created_at: "2026-10-01T12:00:00Z",
        })),
        next_cursor: cursor ? null : "older",
      });
    }
    if (
      path.startsWith("/api/") ||
      path.startsWith("/flags") ||
      path.startsWith("/decide")
    )
      return json({ data: [], next_cursor: null });

    return route.continue();
  });
  await page.goto("/billing");
  const history = page.getByRole("table", { name: "Balance history" });
  await expect(history.getByRole("row")).toHaveCount(100);
  expect(requests).toEqual([null]);
  await history.getByRole("row").last().scrollIntoViewIfNeeded();
  await expect(
    page.getByRole("status", { name: "Loading older transactions" }),
  ).toBeVisible();
  await expect(history.getByRole("row", { includeHidden: true })).toHaveCount(
    103,
  );
  expect(requests).toEqual([null, "older"]);
  releasePage();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Could not load balance history." }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(history.getByRole("row")).toHaveCount(100);
  const failedRequestCount = requests.length;
  fail = false;
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(
    page.getByRole("status", { name: "Loading older transactions" }),
  ).toHaveCount(0);
  await expect(history.getByRole("row")).toHaveCount(103);
  await expect(
    page.getByRole("button", { name: "Next", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Previous", exact: true }),
  ).toHaveCount(0);
  await history.getByRole("row").last().scrollIntoViewIfNeeded();
  expect(requests).toHaveLength(failedRequestCount + 1);
});
