import { expect, test } from "./fixtures";
import { apiPathEndsWith, fulfillJson, fulfillProblem } from "./routes";

test.skip(
  process.env.VITE_FEATURE_FLAGS !== "training",
  "Run the trace suite with the training feature enabled.",
);
test.beforeEach(async ({ page }) => {
  const task = {
    name: "support-triage",
    base_model_id: null,
    comparison_model_id: null,
    production_version_id: null,
  };
  await page.route(apiPathEndsWith("/tasks"), (route) =>
    fulfillJson(route, { data: [task] }),
  );
  await page.route(apiPathEndsWith("/tasks/support-triage"), (route) =>
    fulfillJson(route, task),
  );
  for (const resource of ["runs", "versions"]) {
    await page.route(
      apiPathEndsWith(`/tasks/support-triage/${resource}`),
      (route) => fulfillJson(route, { data: [] }),
    );
  }
});

const id = "0198ae50-94d8-7d4d-a8be-000000000001";
const generation = {
  generation_id: id,
  trace_id: "synthetic-live-trace",
  task: "support-triage",
  model: "test-model",
  source: "relay",
  trainable: false,
  started_at: "2026-09-25T12:00:00.000Z",
  completed_at: "2026-09-25T12:00:01.000Z",
  status: 200,
  outcome: "complete",
  usage: { input: 5, output: 2 },
  content_ref: "opaque-ref",
};
test("Data reads scoped API pages, deduplicates retries, and loads content only on opening", async ({
  page,
}) => {
  const requests: string[] = [];
  await page.route(apiPathEndsWith("/generations"), (route) => {
    requests.push(route.request().url());
    return fulfillJson(route, {
      data: [generation, generation],
      next_cursor: new URL(route.request().url()).searchParams.has("cursor")
        ? null
        : "older",
    });
  });
  let opened = 0;
  await page.route(apiPathEndsWith(`/generations/${id}`), (route) => {
    opened++;
    return fulfillJson(route, {
      generation_id: id,
      raw: {
        request: {
          messages: [{ role: "user", content: "Synthetic prompt" }],
        },
        response: { text: "Synthetic completion" },
      },
      canonical: null,
    });
  });
  await page.goto("/tasks");
  await expect(
    page.getByRole("tab", { name: "Data", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "support-triage", exact: true }).click();
  await page.getByRole("tab", { name: "Data", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "synthetic-live-trace", exact: true }),
  ).toHaveCount(1);
  expect(opened).toBe(0);
  await page.getByRole("button", { name: "Load older content" }).click();
  await expect(
    page.getByRole("button", { name: "Load older content" }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "synthetic-live-trace", exact: true })
    .click();
  await expect(page.getByText(/Synthetic prompt/)).toBeVisible();
  await expect(page.getByText(/Synthetic completion/)).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("trace-content.png") });
  expect(opened).toBe(1);
  expect(requests.some((url) => url.includes("cursor=older"))).toBe(true);
  expect(
    requests.every(
      (url) =>
        /workspaces\/[^/]+\//.test(url) &&
        new URL(url).searchParams.get("task_id") === "support-triage",
    ),
  ).toBe(true);
});
test("Data shows a storage failure instead of fake traces", async ({
  page,
}) => {
  await page.route(apiPathEndsWith("/generations"), (route) =>
    fulfillProblem(route, 503, "Storage unavailable"),
  );
  await page.goto("/tasks");
  await expect(
    page.getByRole("tab", { name: "Data", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "support-triage", exact: true }).click();
  await page.getByRole("tab", { name: "Data", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Could not load traces", {
    timeout: 15000,
  });
  await expect(
    page.getByRole("button", { name: "synthetic-live-trace", exact: true }),
  ).toHaveCount(0);
});
test("capture settings send the real workspace policy", async ({ page }) => {
  const updates: unknown[] = [];
  await page.route(/\/workspaces\/[^/]+$/, (route) => {
    if (route.request().method() !== "PATCH") return route.fallback();
    updates.push(route.request().postDataJSON());
    return fulfillJson(route, route.request().postDataJSON());
  });
  await page.goto("/tasks");
  await expect(
    page.getByRole("link", { name: "support-triage", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Settings", exact: true }).click();
  await page.getByRole("switch", { name: "Trace capture" }).click();
  await expect.poll(() => updates.length).toBe(1);
  expect(updates[0]).toEqual({
    trace_capture_enabled: true,
  });
  await page.getByRole("combobox", { name: "Content retention" }).click();
  await page.getByRole("option", { name: "90 days", exact: true }).click();
  await expect.poll(() => updates.length).toBe(2);
  expect(updates[1]).toMatchObject({ trace_retention_days: 90 });
});

test("settings stay responsive during a save and roll back failed edits", async ({
  page,
}) => {
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  const updates: unknown[] = [];
  await page.route(/\/workspaces\/[^/]+$/, async (route) => {
    if (route.request().method() !== "PATCH") return route.fallback();

    updates.push(route.request().postDataJSON());
    if (updates.length === 1) {
      await held;
      return fulfillProblem(route, 503, "Settings unavailable");
    }

    return fulfillJson(route, route.request().postDataJSON());
  });
  await page.goto("/tasks");
  await expect(
    page.getByRole("link", { name: "support-triage", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Settings", exact: true }).click();
  const capture = page.getByRole("switch", { name: "Trace capture" });
  await capture.click();
  await expect(capture).toBeChecked();
  await expect(capture).toBeEnabled();
  await expect.poll(() => updates.length).toBe(1);
  await page.getByRole("combobox", { name: "Content retention" }).click();
  await page.getByRole("option", { name: "90 days", exact: true }).click();
  await expect(
    page.getByRole("combobox", { name: "Content retention" }),
  ).toHaveText("90 days");
  expect(updates).toHaveLength(1);
  release();
  await expect(capture).not.toBeChecked();
  await expect.poll(() => updates.length).toBe(2);
  await expect(page.getByRole("alert")).toContainText("Settings unavailable");
});

test("trace generations render chronologically without a selector, with a loading skeleton", async ({
  page,
}) => {
  let release!: () => void;
  const loading = new Promise<void>((resolve) => {
    release = resolve;
  });
  const earlier = {
    ...generation,
    generation_id: "0198ae50-94d8-7d4d-a8be-000000000002",
    started_at: "2026-09-25T11:00:00.000Z",
  };
  await page.route(apiPathEndsWith("/generations"), async (route) => {
    await loading;
    return fulfillJson(route, {
      data: [generation, earlier],
      next_cursor: null,
    });
  });
  for (const row of [generation, earlier]) {
    await page.route(
      apiPathEndsWith(`/generations/${row.generation_id}`),
      (route) =>
        fulfillJson(route, {
          generation_id: row.generation_id,
          raw: { request: { prompt: row.generation_id }, response: {} },
          canonical: null,
        }),
    );
  }
  await page.goto("/tasks/support-triage");
  await page.getByRole("tab", { name: "Data", exact: true }).click();
  await expect(page.getByRole("region", { name: "Traces" })).toHaveAttribute(
    "aria-busy",
    "true",
  );
  await expect(page.getByText("Loading traces…")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Refresh", exact: true }),
  ).toHaveCount(0);
  release();
  await page
    .getByRole("button", { name: "synthetic-live-trace", exact: true })
    .click();
  const timeline = page.getByRole("list", { name: "Trace timeline" });
  await expect(timeline.getByRole("listitem")).toHaveCount(2);
  await expect(timeline.getByRole("listitem").nth(0)).toContainText(
    earlier.generation_id,
  );
  await expect(timeline.getByRole("listitem").nth(1)).toContainText(
    generation.generation_id,
  );
  await expect(page.getByRole("combobox", { name: "Generation" })).toHaveCount(
    0,
  );
});

test("model selectors use supported roles and save comparison selections", async ({
  page,
}) => {
  const task = {
    id: "0198ae50-94d8-7d4d-a8be-000000000003",
    name: "support-triage",
    base_model_id: "Qwen/Qwen3-0.6B",
    comparison_model_id: "Qwen/Qwen3-0.6B",
    production_version_id: null,
    training_schedule: null,
  };
  let saved: unknown;
  await page.route(apiPathEndsWith("/tasks/support-triage"), (route) => {
    if (route.request().method() === "PATCH") {
      saved = route.request().postDataJSON();
      Object.assign(task, saved);
      return fulfillJson(route, task);
    }
    return fulfillJson(route, task);
  });
  await page.route(apiPathEndsWith("/training-runs"), (route) =>
    fulfillJson(route, { data: [] }),
  );
  await page.route(apiPathEndsWith("/models"), async (route) => {
    const response = await route.fetch();
    const catalog = await response.json();
    const model = catalog.data[0];
    return fulfillJson(route, {
      ...catalog,
      data: [
        { ...model, id: "Qwen/Qwen3-0.6B", status: "unavailable" },
        { ...model, id: "jaredpalmer/kev-9b", status: "available" },
      ],
    });
  });
  await page.goto("/tasks/support-triage");
  await page.getByRole("tab", { name: "Settings", exact: true }).click();
  await page.getByRole("combobox", { name: "Base model" }).click();
  await expect(page.getByRole("option", { name: /Qwen/ })).toBeVisible();
  await expect(page.getByRole("option", { name: /kev/ })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.getByRole("combobox", { name: "Comparison model" }).click();
  await expect(
    page.getByRole("option", { name: "jaredpalmer/kev-9b", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("option", {
      name: "anthropic/claude-opus-5-5",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("option", { name: "openai/gpt-6-astra", exact: true })
    .click();
  await expect
    .poll(() => saved)
    .toEqual({ comparison_model_id: "openai/gpt-6-astra" });
  await expect(
    page.getByRole("combobox", { name: "Comparison model" }),
  ).toContainText("openai/gpt-6-astra");
});
