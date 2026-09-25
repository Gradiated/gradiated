import { expect, test } from "./fixtures";
import { apiPathEndsWith, fulfillJson, fulfillProblem } from "./routes";

test.skip(
  process.env.VITE_FEATURE_FLAGS !== "training",
  "Run the trace suite with the training feature enabled.",
);
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
  await page.getByRole("tab", { name: "Settings", exact: true }).click();
  await page.getByRole("switch", { name: "Trace capture" }).click();
  await expect.poll(() => updates.length).toBe(1);
  expect(updates[0]).toEqual({
    trace_capture_enabled: true,
  });
  await page
    .getByRole("combobox", { name: "Content retention" })
    .selectOption("90");
  await expect.poll(() => updates.length).toBe(2);
  expect(updates[1]).toMatchObject({ trace_retention_days: 90 });
});
