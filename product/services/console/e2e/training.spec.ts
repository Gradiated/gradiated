import { randomUUID } from "node:crypto";
import { Pool } from "pg";
import { expect, test } from "./fixtures";
import { apiUrl, databaseUrl } from "./env";
import { apiPathEndsWith, fulfillJson, fulfillProblem } from "./routes";

test.skip(
  process.env.VITE_FEATURE_FLAGS !== "training",
  "Requires the training feature.",
);

for (const taskName of ["support-triage", "Billing Questions & Refunds"]) {
  test(`settings, versions, promotion and paged events persist for ${taskName}`, async ({
    page,
    context,
    account,
  }) => {
    const response = await context.request.get(
      `${apiUrl}/api/v1/organizations/${account.organizationId}/workspaces`,
    );
    expect(response.ok()).toBe(true);
    const {
      data: [workspace],
    } = await response.json();
    const pool = new Pool({ connectionString: databaseUrl });
    const taskId = randomUUID();
    const runId = randomUUID();
    const versionId = randomUUID();
    const versionName = `${taskName}-20260929`;

    try {
      const {
        rows: [model],
      } = await pool.query<{ id: string }>("SELECT id FROM models LIMIT 1");
      await pool.query(
        "INSERT INTO tasks (id, workspace_id, name, base_model_id) VALUES ($1, $2, $3, $4)",
        [taskId, workspace.id, taskName, model!.id],
      );
      await pool.query(
        "INSERT INTO training_runs (id, task_id, trigger, stage, base_model_id, input_cutoff, finished_at) VALUES ($1, $2, 'manual', 'succeeded', $3, now(), now())",
        [runId, taskId, model!.id],
      );
      await pool.query(
        "INSERT INTO task_versions (id, workspace_id, task_id, training_run_id, name, base_model_id, adapter, status) VALUES ($1, $2, $3, $4, $5, $6, $7, 'available')",
        [
          versionId,
          workspace.id,
          taskId,
          runId,
          versionName,
          model!.id,
          JSON.stringify({
            format: "peft_lora",
            artifact_uri: "s3://test/adapter",
            sha256: "a".repeat(64),
            size_bytes: 10,
            rank: 8,
          }),
        ],
      );
      await pool.query(
        "INSERT INTO training_run_events (run_id, at, source, attempt, payload) VALUES ($1, now(), 'control_plane', 1, $2)",
        [runId, JSON.stringify({ type: "stage_entered", stage: "queued" })],
      );
      await pool.query(
        "INSERT INTO training_run_events (run_id, at, source, attempt, payload) SELECT $1, now(), 'control_plane', 1, jsonb_build_object('type', 'note', 'level', 'info', 'message', 'event-' || n) FROM generate_series(1, 1001) n",
        [runId],
      );

      await page.route(apiPathEndsWith("/tasks"), async (route) => {
        const taskResponse = await context.request.get(
          `${apiUrl}/api/v1/workspaces/${workspace.id}/tasks/${encodeURIComponent(taskName)}`,
        );
        const runResponse = await context.request.get(
          `${apiUrl}/api/v1/workspaces/${workspace.id}/training-runs/${runId}`,
        );
        return fulfillJson(route, {
          data: [
            {
              ...(await taskResponse.json()),
              latest_run: {
                ...(await runResponse.json()),
                version_name: versionName,
              },
            },
          ],
        });
      });
      await page.goto("/tasks");
      const taskRow = page.getByRole("row").filter({
        has: page.getByRole("link", { name: taskName, exact: true }),
      });
      await expect(taskRow).toContainText(versionName);
      await expect(
        page.getByRole("columnheader", { name: "Quality", exact: true }),
      ).toBeVisible();
      await expect(taskRow.getByRole("cell").nth(3)).toHaveText("—");
      await pool.query(
        "UPDATE training_runs SET evaluation = $2 WHERE id = $1",
        [
          runId,
          JSON.stringify({
            holdout_groups: 10,
            holdout_examples: 20,
            comparison_model_id: "openai/gpt-5",
            judge_model_id: "openai/gpt-5.6-sol",
            vs_comparison: {
              comparator_model_id: "openai/gpt-5",
              win: 0.7,
              tie: 0.2,
              loss: 0.1,
              unresolved: 0,
            },
            cost_per_request_nano_usd: { comparison: 2000, fine_tuned: 1000 },
            output_tokens_per_second: { comparison: 50, fine_tuned: 100 },
            error_rate: 0,
          }),
        ],
      );
      await page.reload();
      await expect(taskRow.getByRole("cell").nth(3)).toContainText("cheaper");
      await expect(taskRow.getByRole("cell").nth(4)).toContainText("faster");
      await expect(
        taskRow
          .getByRole("cell")
          .nth(5)
          .getByRole("img", { name: /Better 70%/ }),
      ).toBeVisible();
      await pool.query(
        "UPDATE training_runs SET evaluation = NULL WHERE id = $1",
        [runId],
      );
      await pool.query("UPDATE training_runs SET dataset = $2 WHERE id = $1", [
        runId,
        JSON.stringify({
          eligible_examples: 100,
          duplicates_removed: 10,
          train: 70,
          validation: 10,
          test: 10,
        }),
      ]);
      await page.goto(`/tasks/${encodeURIComponent(taskName)}`);
      await expect(
        page.getByRole("heading", { name: versionName, exact: true }),
      ).toBeVisible();
      await expect(page.getByText(/70 training examples/)).toBeVisible();
      await expect(
        page.getByText("Evaluation not available yet."),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Re-train", exact: true }),
      ).toBeDisabled();
      await page.getByRole("tab", { name: "Settings", exact: true }).click();
      await page
        .getByRole("textbox", { name: "Comparison model" })
        .fill("openai/gpt-5");
      await page.getByRole("button", { name: "Save", exact: true }).click();
      await expect
        .poll(
          async () =>
            (
              await pool.query(
                "SELECT comparison_model_id FROM tasks WHERE id = $1",
                [taskId],
              )
            ).rows[0].comparison_model_id,
        )
        .toBe("openai/gpt-5");
      await page.reload();
      await page.getByRole("tab", { name: "Settings", exact: true }).click();
      await expect(
        page.getByRole("textbox", { name: "Comparison model" }),
      ).toHaveValue("openai/gpt-5");
      await page.getByRole("tab", { name: "Model", exact: true }).click();
      await page
        .getByRole("button", { name: "Promote to production", exact: true })
        .click();
      await page.route(
        apiPathEndsWith("/production"),
        (route) =>
          fulfillProblem(route, 503, "Promotion temporarily unavailable"),
        { times: 1 },
      );
      await page.getByRole("button", { name: "Promote", exact: true }).click();
      await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
        "Promotion temporarily unavailable",
      );
      await page.getByRole("button", { name: "Promote", exact: true }).click();
      await expect(page.getByText("Production", { exact: true })).toBeVisible();
      expect(
        (
          await pool.query(
            "SELECT production_version_id FROM tasks WHERE id = $1",
            [taskId],
          )
        ).rows[0].production_version_id,
      ).toBe(versionId);
      await page
        .getByRole("tab", { name: "Training runs", exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: "Load more events" }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Queued", exact: true }),
      ).toBeVisible();
      await page.getByRole("button", { name: "Load more events" }).click();
      await expect(
        page.getByRole("button", { name: "Load more events" }),
      ).toHaveCount(0);
      await page.getByRole("button", { name: "Queued", exact: true }).click();
      await expect(page.locator("pre")).toContainText("event-1001");
      const polledCursors: (string | null)[] = [];
      const recordEventRequest = (
        request: import("@playwright/test").Request,
      ) => {
        const url = new URL(request.url());
        if (url.pathname.endsWith(`/training-runs/${runId}/events`))
          polledCursors.push(url.searchParams.get("after"));
      };
      page.on("request", recordEventRequest);
      await expect
        .poll(() => polledCursors.length, { timeout: 15_000 })
        .toBeGreaterThan(0);
      expect(
        polledCursors.every((cursor) => cursor !== null && Number(cursor) > 0),
      ).toBe(true);
      page.off("request", recordEventRequest);

      await pool.query(
        "UPDATE task_versions SET status = 'unavailable' WHERE id = $1",
        [versionId],
      );
      await page.reload();
      await page.getByRole("tab", { name: "Model", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "Use", exact: true }),
      ).toBeDisabled();
      let failDownload = true;
      await page.route(
        apiPathEndsWith(`/versions/${versionId}/adapter`),
        (route) =>
          failDownload
            ? fulfillProblem(route, 503, "Storage unavailable")
            : fulfillJson(route, {
                url: `${apiUrl}/test-adapter.tar.gz`,
                expires_at: new Date(Date.now() + 300_000).toISOString(),
              }),
      );
      await page.route(`${apiUrl}/test-adapter.tar.gz`, (route) =>
        route.fulfill({
          status: 200,
          headers: {
            "content-type": "application/gzip",
            "content-disposition": 'attachment; filename="adapter.tar.gz"',
          },
          body: Buffer.from("test archive"),
        }),
      );
      await page.getByRole("button", { name: "Download", exact: true }).click();
      await page
        .getByRole("button", { name: "adapter.tar.gz", exact: true })
        .click();
      await expect(page.getByRole("alert")).toContainText(
        "Storage unavailable",
      );
      failDownload = false;
      const downloaded = page.waitForEvent("download");
      await page
        .getByRole("button", { name: "adapter.tar.gz", exact: true })
        .click();
      expect((await downloaded).suggestedFilename()).toBe("adapter.tar.gz");
      await page.keyboard.press("Escape");
      const versionsResponse = await context.request.get(
        `${apiUrl}/api/v1/workspaces/${workspace.id}/tasks/${encodeURIComponent(taskName)}/versions`,
      );
      const versions = await versionsResponse.json();
      await page.route(
        apiPathEndsWith(`/tasks/${encodeURIComponent(taskName)}/versions`),
        (route) =>
          fulfillJson(route, {
            data: [
              ...versions.data,
              {
                ...versions.data[0],
                id: randomUUID(),
                name: "older-unavailable-version",
                is_production: false,
              },
            ],
          }),
      );
      await page.reload();
      await page
        .getByRole("button", { name: "Actions for older-unavailable-version" })
        .click();
      await expect(
        page.getByRole("menuitem", { name: "Use this version", exact: true }),
      ).toBeDisabled();
      await expect(
        page.getByRole("menuitem", {
          name: "Promote to production",
          exact: true,
        }),
      ).toBeDisabled();
      await expect(
        page.getByRole("menuitem", { name: "Download adapter", exact: true }),
      ).toBeEnabled();
    } finally {
      await pool.query("DELETE FROM tasks WHERE id = $1", [taskId]);
      await pool.end();
    }
  });
}

test("task discovery distinguishes errors from an empty workspace and can retry", async ({
  page,
}) => {
  let fail = true;
  await page.route(apiPathEndsWith("/tasks"), (route) =>
    fail
      ? fulfillProblem(route, 503, "Trace storage unavailable")
      : fulfillJson(route, { data: [] }),
  );
  await page.goto("/tasks");
  await expect(page.getByRole("alert")).toContainText(
    "Trace storage unavailable",
    { timeout: 15_000 },
  );
  await expect(page.getByText("No tasks yet", { exact: true })).toHaveCount(0);
  fail = false;
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByText("No tasks yet", { exact: true })).toBeVisible();
  await expect(page.getByText(/First request received|500 traces/)).toHaveCount(
    0,
  );
});

test("the task list does not request per-task histories", async ({ page }) => {
  let historyRequests = 0;
  page.on("request", (request) => {
    if (
      /\/(training-runs|tasks\/[^/]+\/versions)$/.test(
        new URL(request.url()).pathname,
      )
    )
      historyRequests++;
  });
  await page.route(apiPathEndsWith("/tasks"), (route) =>
    fulfillJson(route, {
      data: Array.from({ length: 100 }, (_, index) => ({
        id: `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`,
        name: `task-${index}`,
        base_model_id: null,
        comparison_model_id: null,
        production_version_id: null,
      })),
    }),
  );
  await page.goto("/tasks");
  await expect(
    page.getByRole("link", { name: "task-99", exact: true }),
  ).toBeVisible();
  expect(historyRequests).toBe(0);
});
