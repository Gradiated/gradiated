import type { Page, Request } from "@playwright/test";

import type { components, operations } from "../src/api/schema";
import { expect, test } from "./fixtures";
import { apiPathEndsWith, fulfillJson } from "./routes";

type ApiKey = components["schemas"]["ApiKey"];
type GenerationLog =
  operations["listGenerations"]["responses"][200]["content"]["application/json"]["data"][number];

const FIRST_ID = "0198ae50-94d8-7d4d-a8be-000000000001";
const SECOND_ID = "0198ae50-94d8-7d4d-a8be-000000000002";
const API_KEY_ID = "0198ae50-94d8-7d4d-a8be-0000000000aa";

const generation = (id: string): GenerationLog => ({
  id,
  external_id: null,
  model_id: "deepseek/deepseek-v4.1-flash-1017",
  status: "succeeded",
  streamed: false,
  charge: "1000",
  input_tokens: 10,
  cached_input_tokens: 0,
  cache_write_tokens: 0,
  output_tokens: 20,
  reasoning_tokens: 0,
  finish_reason: "stop",
  error_code: null,
  usable_output_delivered: true,
  cancellation_owner: null,
  received_at: "2026-09-01T00:00:00.000Z",
  started_at: "2026-09-01T00:00:00.100Z",
  first_token_at: "2026-09-01T00:00:00.200Z",
  completed_at: "2026-09-01T00:00:01.000Z",
});

const apiKey: ApiKey = {
  id: API_KEY_ID,
  organization_id: "0198ae50-94d8-7d4d-a8be-0000000000bb",
  workspace_id: "0198ae50-94d8-7d4d-a8be-0000000000cc",
  name: "Routed key",
  expires_at: null,
  revoked_at: null,
  created_by: null,
  created_at: "2026-09-01T00:00:00.000Z",
  updated_at: "2026-09-01T00:00:00.000Z",
};

const rowFor = (page: Page, id: string) =>
  page.getByRole("button").filter({ hasText: id.slice(-6) });

const pageNumber = (page: Page) =>
  page
    .getByRole("button", { name: "Previous page" })
    .locator("xpath=following-sibling::span[1]");

const routeGenerations = async (page: Page) => {
  const requests: URL[] = [];

  await page.route(apiPathEndsWith("/generations"), (route) => {
    const url = new URL(route.request().url());
    requests.push(url);

    return fulfillJson(
      route,
      url.searchParams.get("cursor") === "second-page"
        ? { data: [generation(SECOND_ID)], next_cursor: null }
        : { data: [generation(FIRST_ID)], next_cursor: "second-page" },
    );
  });

  return requests;
};

test("changing a filter returns to the first page without the old cursor", async ({
  page,
}) => {
  const requests = await routeGenerations(page);
  await page.goto("/logs");

  await expect(rowFor(page, FIRST_ID)).toBeVisible();
  await expect(pageNumber(page)).toHaveText("1");

  await page.getByRole("button", { name: "Next page" }).click();

  await expect(rowFor(page, SECOND_ID)).toBeVisible();
  await expect(pageNumber(page)).toHaveText("2");

  await page.getByRole("combobox").filter({ hasText: "All statuses" }).click();
  await page.getByRole("option", { name: "Failed" }).click();

  await expect(rowFor(page, FIRST_ID)).toBeVisible();
  await expect(pageNumber(page)).toHaveText("1");

  const filtered = requests.filter(
    (url) => url.searchParams.get("status") === "failed",
  );
  expect(filtered.length).toBeGreaterThan(0);
  expect(filtered.map((url) => url.searchParams.get("cursor"))).toEqual(
    filtered.map(() => null),
  );
});

test("an API-key link preselects the API-key filter", async ({ page }) => {
  await page.route(apiPathEndsWith("/api-keys"), (route) =>
    fulfillJson(route, { data: [apiKey], next_cursor: null }),
  );
  const requests = await routeGenerations(page);
  const filtered = page.waitForRequest(
    (request: Request) =>
      new URL(request.url()).searchParams.get("api_key_id") === API_KEY_ID,
  );

  await page.goto(`/logs?apiKeyId=${API_KEY_ID}`);

  await filtered;
  await expect(page.getByRole("combobox", { name: "API key" })).toHaveText(
    "Routed key",
  );
  expect(
    requests.every((url) => url.searchParams.get("api_key_id") === API_KEY_ID),
  ).toBe(true);
});

test("searching from a later page queries the first page", async ({ page }) => {
  const requests = await routeGenerations(page);
  await page.goto("/logs");

  await page.getByRole("button", { name: "Next page" }).click();
  await expect(rowFor(page, SECOND_ID)).toBeVisible();

  await page.getByLabel("Search logs").fill("gen");

  await expect(rowFor(page, FIRST_ID)).toBeVisible();
  await expect(pageNumber(page)).toHaveText("1");

  const searched = requests.filter((url) => url.searchParams.has("search"));
  expect(searched.length).toBeGreaterThan(0);
  expect(searched.every((url) => !url.searchParams.has("cursor"))).toBe(true);
});
