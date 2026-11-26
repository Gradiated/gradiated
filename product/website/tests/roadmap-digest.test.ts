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

const storeCalls = () =>
  deliver.mock.calls
    .filter(([url]) => String(url).startsWith(store))
    .map(([, init]) => JSON.parse(String(init.body)) as string[][]);
const slackCalls = () =>
  deliver.mock.calls
    .filter(([url]) => !String(url).startsWith(store))
    .map(([, init]) => JSON.parse(String(init.body)));

const withActivity = (
  pending: string[],
  suggestions: string[],
  totals: string[],
  { locked = false, cleanupFails = false, slackFails = false } = {},
) =>
  deliver.mockImplementation(async (url: unknown, init: RequestInit) => {
    if (!String(url).startsWith(store))
      return slackFails
        ? new Response("no", { status: 500 })
        : new Response("ok");
    const commands = JSON.parse(String(init.body)) as string[][];
    if (commands[0][0] === "SET")
      return Response.json([{ result: locked ? null : "OK" }]);
    if (commands[0][0] === "HINCRBY" || commands[0][0] === "LTRIM")
      return cleanupFails
        ? new Response("down", { status: 500 })
        : Response.json(commands.map(() => ({ result: 0 })));
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
  expect(slackCalls()).toHaveLength(0);
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

  const [slack] = slackCalls();
  expect(slack.text).toBe("Roadmap today: 3 upvotes · 2 name suggestions");
  const table: string = slack.blocks[1].text.text;
  expect(table).toMatch(/Model\s+Today\s+Total/);
  expect(table).toMatch(/Code review\s+\+2\s+5/);
  expect(table).toMatch(/Linden-2\s+\+1\s+1/);
  const list: string = slack.blocks[2].text.text;
  expect(list.indexOf("Juniper")).toBeLessThan(list.indexOf("Sentinel"));
  expect(list).toContain("Juniper &lt;b&gt;");

  const cleanup = storeCalls().find(([command]) => command[0] === "HINCRBY");
  expect(cleanup).toEqual([
    ["HINCRBY", "roadmap:upvotes:pending", "code-review", "-2"],
    ["HINCRBY", "roadmap:upvotes:pending", "task-routing", "-1"],
    ["LTRIM", "roadmap:suggestions:pending", "0", "-3"],
  ]);
});

test("keeps the day's activity if Slack fails", async () => {
  withActivity(["code-review", "1"], [], ["code-review", "1"], {
    slackFails: true,
  });
  expect((await run()).status).toBe(502);
  expect(storeCalls().some(([command]) => command[0] === "HINCRBY")).toBe(
    false,
  );
});

test("a second, overlapping run stops at the lock", async () => {
  withActivity(["code-review", "1"], [], ["code-review", "1"], {
    locked: true,
  });
  expect(await (await run()).json()).toMatchObject({ busy: true });
  expect(slackCalls()).toHaveLength(0);
});

test("flags a summary that posted but could not clear the day", async () => {
  withActivity(["code-review", "1"], [], ["code-review", "1"], {
    cleanupFails: true,
  });
  const response = await run();
  expect(response.status).toBe(500);
  expect(await response.json()).toMatchObject({ posted: true, cleared: false });
});
