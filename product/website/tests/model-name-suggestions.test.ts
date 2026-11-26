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
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

test("only unnamed models accept suggestions", async () => {
  for (const id of ["task-routing", "linden-1", "unknown"]) {
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

const vote = (modelId: string, value: unknown = "up") =>
  POST(
    new Request(`${localOrigin}/api/model-name-suggestions`, {
      method: "POST",
      headers: { Origin: localOrigin, "Content-Type": "application/json" },
      body: JSON.stringify({ modelId, vote: value }),
    }),
  );

test("upvotes post the model name, without totals when no store is set", async () => {
  expect((await vote("task-routing")).status).toBe(204);
  const body = JSON.parse(deliver.mock.calls[0][1].body);
  expect(body.text).toBe("User upvoted Linden-2");
  expect(body.blocks).toHaveLength(1);
  expect(body.blocks[0].text.text).toBe("User upvoted *Linden-2*");
});

test("rejects upvotes on released models and unknown vote values", async () => {
  expect((await vote("linden-1")).status).toBe(400);
  expect((await vote("code-review", "down")).status).toBe(400);
  expect(deliver).not.toHaveBeenCalled();
});

const useStore = () => {
  vi.stubEnv("KV_REST_API_URL", "https://store.upstash.io");
  vi.stubEnv("KV_REST_API_TOKEN", "test-only");
  // A fresh rate-limit window: the handler counts requests per minute.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(Date.now() + 10 * 60_000);
};

test("with a store, votes and suggestions are saved, not posted", async () => {
  useStore();
  deliver.mockImplementation(async () =>
    Response.json([{ result: 1 }, { result: 1 }]),
  );

  expect((await vote("code-review")).status).toBe(204);
  expect((await submit("code-review", "Juniper")).status).toBe(204);

  const urls = deliver.mock.calls.map(([url]) => String(url));
  expect(urls.every((url) => url === "https://store.upstash.io/pipeline")).toBe(
    true,
  );
  const [voteCommands, suggestionCommands] = deliver.mock.calls.map(
    ([, init]) => JSON.parse(init.body),
  );
  expect(voteCommands).toEqual([
    ["HINCRBY", "roadmap:upvotes", "code-review", "1"],
    ["HINCRBY", "roadmap:upvotes:pending", "code-review", "1"],
  ]);
  expect(suggestionCommands.map((c: string[]) => c.slice(0, 2))).toEqual([
    ["LPUSH", "roadmap:suggestions"],
    ["LPUSH", "roadmap:suggestions:pending"],
  ]);
  expect(JSON.parse(suggestionCommands[0][2])).toMatchObject({
    modelId: "code-review",
    suggestion: "Juniper",
  });
});

test("empty KV settings fall back to the Upstash names", async () => {
  useStore();
  vi.stubEnv("KV_REST_API_URL", "");
  vi.stubEnv("KV_REST_API_TOKEN", "");
  vi.stubEnv("UPSTASH_REDIS_REST_URL", "https://other.upstash.io");
  vi.stubEnv("UPSTASH_REDIS_REST_TOKEN", "test-only");
  deliver.mockImplementation(async () =>
    Response.json([{ result: 1 }, { result: 1 }]),
  );
  expect((await vote("code-review")).status).toBe(204);
  expect(String(deliver.mock.calls[0][0])).toBe(
    "https://other.upstash.io/pipeline",
  );
});

test("if the store fails, the vote posts to Slack straight away", async () => {
  useStore();
  deliver.mockImplementation(async (url: unknown) =>
    String(url).startsWith("https://store.upstash.io")
      ? new Response("down", { status: 500 })
      : new Response("ok"),
  );
  expect((await vote("code-review")).status).toBe(204);
  const slack = JSON.parse(String(deliver.mock.calls[1][1].body));
  expect(slack.text).toBe("User upvoted Code review");
});
