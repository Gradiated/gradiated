import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { GET } from "../api/roadmap-digest";

const store = "https://store.upstash.io";
let deliver: ReturnType<typeof vi.fn>;

const run = (secret = "cron-test") =>
  GET(
    new Request("https://www.gradiated.com/api/roadmap-digest", {
      headers: { Authorization: `Bearer ${secret}` },
    }),
  );

const withActivity = (
  pending: string[],
  suggestions: string[],
  totals: string[],
) =>
  deliver.mockImplementation(async (url: unknown, init: RequestInit) => {
    if (!String(url).startsWith(store)) return new Response("ok");
    const commands = JSON.parse(String(init.body)) as string[][];
    if (commands[0][0] === "HGETALL")
      return Response.json([
        { result: pending },
        { result: suggestions },
        { result: totals },
      ]);
    return Response.json(commands.map(() => ({ result: 0 })));
  });

beforeEach(() => {
  vi.stubEnv("CRON_SECRET", "cron-test");
  vi.stubEnv(
    "MODEL_NAME_SLACK_WEBHOOK_URL",
    "https://hooks.slack.com/services/T000/B000/test-only",
  );
  vi.stubEnv("KV_REST_API_URL", store);
  vi.stubEnv("KV_REST_API_TOKEN", "test-only");
  deliver = vi.fn();
  vi.stubGlobal("fetch", deliver);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

test("refuses calls without the cron secret", async () => {
  expect((await run("wrong")).status).toBe(401);
  expect(deliver).not.toHaveBeenCalled();
});

test("posts nothing on a quiet day", async () => {
  withActivity(["code-review", "0"], [], ["code-review", "4"]);
  expect(await (await run()).json()).toMatchObject({ posted: false });
  expect(deliver).toHaveBeenCalledTimes(1);
});

test("posts the day's upvotes and suggestions, then clears what it sent", async () => {
  const suggestion = (modelId: string, text: string) =>
    JSON.stringify({ modelId, suggestion: text, at: "2026-11-26T12:00:00Z" });
  withActivity(
    ["code-review", "2", "task-routing", "1"],
    // Newest first, as stored.
    [
      suggestion("code-review", "Sentinel"),
      suggestion("code-review", "Juniper <b>"),
    ],
    ["code-review", "5", "task-routing", "1"],
  );

  expect(await (await run()).json()).toMatchObject({
    posted: true,
    votes: 3,
    suggestions: 2,
  });

  const slack = JSON.parse(String(deliver.mock.calls[1][1].body));
  expect(slack.text).toBe("Roadmap today: 3 upvotes · 2 name suggestions");
  const table: string = slack.blocks[1].text.text;
  expect(table).toMatch(/Model\s+Today\s+Total/);
  expect(table).toMatch(/Code review\s+\+2\s+5/);
  expect(table).toMatch(/Linden-2\s+\+1\s+1/);
  const list: string = slack.blocks[2].text.text;
  expect(list.indexOf("Juniper")).toBeLessThan(list.indexOf("Sentinel"));
  expect(list).toContain("Juniper &lt;b&gt;");

  const cleanup = JSON.parse(String(deliver.mock.calls[2][1].body));
  expect(cleanup).toEqual([
    ["HINCRBY", "roadmap:upvotes:pending", "code-review", "-2"],
    ["HINCRBY", "roadmap:upvotes:pending", "task-routing", "-1"],
    ["LTRIM", "roadmap:suggestions:pending", "0", "-3"],
  ]);
});

test("keeps the day's activity if Slack fails", async () => {
  withActivity(["code-review", "1"], [], ["code-review", "1"]);
  deliver.mockImplementationOnce(async () =>
    Response.json([
      { result: ["code-review", "1"] },
      { result: [] },
      { result: ["code-review", "1"] },
    ]),
  );
  deliver.mockImplementationOnce(
    async () => new Response("no", { status: 500 }),
  );
  expect((await run()).status).toBe(502);
  expect(deliver).toHaveBeenCalledTimes(2);
});
