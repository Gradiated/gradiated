import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { POST } from "../api/model-name-suggestions";

const localOrigin = "https://www.gradiated.com";
// A synthetic URL only. The tests replace fetch before calling the handler.
const webhook = "https://hooks.slack.com/services/T000/B000/test-only";
let deliver: ReturnType<typeof vi.fn>;

const submit = (modelId: string, suggestion: string, origin = localOrigin) =>
  POST(
    new Request(`${localOrigin}/api/model-name-suggestions`, {
      method: "POST",
      headers: { Origin: origin, "Content-Type": "application/json" },
      body: JSON.stringify({ modelId, suggestion }),
    }),
  );

beforeEach(() => {
  vi.stubEnv("MODEL_NAME_SLACK_WEBHOOK_URL", webhook);
  deliver = vi.fn(async () => new Response("ok"));
  vi.stubGlobal("fetch", deliver);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

test("only unnamed models accept suggestions", async () => {
  for (const id of ["task-routing", "linden-1", "carat", "unknown"]) {
    expect((await submit(id, "Example name")).status).toBe(400);
  }

  expect(deliver).not.toHaveBeenCalled();
});

test("rejects cross-origin and empty or oversized submissions", async () => {
  expect(
    (await submit("code-review", "Example name", "https://elsewhere.invalid"))
      .status,
  ).toBe(403);
  expect((await submit("code-review", "  ")).status).toBe(400);
  expect((await submit("code-review", "A".repeat(601))).status).toBe(400);
  expect((await submit("code-review", "A".repeat(4_096))).status).toBe(400);
  expect(deliver).not.toHaveBeenCalled();
});

test("sends the suggestion as plain text to the configured Slack channel", async () => {
  const suggestion = "Spotter because it spots regressions. <!channel>";
  expect((await submit("code-review", suggestion)).status).toBe(204);

  const [url, request] = deliver.mock.calls[0]!;
  expect(String(url)).toBe(webhook);
  expect(request.redirect).toBe("error");
  expect(JSON.parse(request.body)).toMatchObject({
    text: "Model name suggestion for Code review",
    unfurl_links: false,
    blocks: [
      {
        text: {
          type: "plain_text",
          text: "Model name suggestion for Code review",
        },
      },
      { text: { type: "plain_text", text: suggestion } },
    ],
  });
});

test("fails closed for an invalid destination and reports Slack delivery failures", async () => {
  vi.stubEnv(
    "MODEL_NAME_SLACK_WEBHOOK_URL",
    "https://elsewhere.invalid/services/T000/B000/test-only",
  );
  expect((await submit("code-review", "Spotter")).status).toBe(503);
  expect(deliver).not.toHaveBeenCalled();

  vi.stubEnv("MODEL_NAME_SLACK_WEBHOOK_URL", webhook);
  deliver.mockResolvedValue(new Response("denied", { status: 403 }));
  expect((await submit("code-review", "Spotter")).status).toBe(502);
});

test("throttles repeated submissions from one client", async () => {
  vi.stubEnv("VERCEL", "1");
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const response = await POST(
      new Request(`${localOrigin}/api/model-name-suggestions`, {
        method: "POST",
        headers: {
          Origin: localOrigin,
          "Content-Type": "application/json",
          "x-vercel-forwarded-for": "192.0.2.1",
        },
        body: JSON.stringify({ modelId: "code-review", suggestion: "Spotter" }),
      }),
    );
    expect(response.status).toBe(attempt < 4 ? 204 : 429);
  }

  expect(deliver).toHaveBeenCalledTimes(4);
});
