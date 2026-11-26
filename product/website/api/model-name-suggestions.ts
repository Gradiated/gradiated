import {
  canSuggestName,
  MODEL_NAME_SUGGESTION_MAX_LENGTH,
  roadmapEntries,
} from "../src/model-roadmap.js";
import type { RoadmapEntry } from "../src/model-roadmap.js";

const bodyLimit = 4_096;
const rateWindowMs = 60_000;
const requestsByClient = new Map<string, number>();
let rateWindow = -1;
let totalRequests = 0;

const acceptRequest = (client: string): boolean => {
  const window = Math.floor(Date.now() / rateWindowMs);
  if (window !== rateWindow) {
    requestsByClient.clear();
    totalRequests = 0;
    rateWindow = window;
  }

  const count = requestsByClient.get(client) ?? 0;
  if (count >= 4 || totalRequests >= 25) return false;

  requestsByClient.set(client, count + 1);
  totalRequests += 1;
  return true;
};

const readSubmission = async (request: Request): Promise<unknown> => {
  const reader = request.body?.getReader();
  if (!reader) return undefined;

  const decoder = new TextDecoder("utf-8", { fatal: true });
  let size = 0;
  let body = "";
  try {
    for (;;) {
      const chunk = await reader.read();
      if (chunk.done) break;
      size += chunk.value.byteLength;
      if (size > bodyLimit) {
        await reader.cancel();
        return undefined;
      }

      body += decoder.decode(chunk.value, { stream: true });
    }

    return JSON.parse(body + decoder.decode());
  } catch {
    return undefined;
  } finally {
    reader.releaseLock();
  }
};

const slackWebhook = (): URL | undefined => {
  const webhook = URL.parse(process.env.MODEL_NAME_SLACK_WEBHOOK_URL ?? "");
  if (
    webhook?.origin === "https://hooks.slack.com" &&
    /^\/services\/[A-Za-z0-9]+\/[A-Za-z0-9]+\/[A-Za-z0-9_-]+$/.test(
      webhook.pathname,
    ) &&
    !webhook.username &&
    !webhook.password &&
    !webhook.search &&
    !webhook.hash
  ) {
    return webhook;
  }

  return undefined;
};

// Upvote totals live in the project's Upstash Redis, over its REST API.
const voteStore = (): { url: string; token: string } | undefined => {
  const url =
    process.env.KV_REST_API_URL ?? process.env.UPSTASH_REDIS_REST_URL ?? "";
  const token =
    process.env.KV_REST_API_TOKEN ?? process.env.UPSTASH_REDIS_REST_TOKEN ?? "";
  return url.startsWith("https://") && token ? { url, token } : undefined;
};

const VOTES_KEY = "roadmap:upvotes";

// Adds one to a model's count and returns every model's total.
const countVote = async (
  modelId: string,
): Promise<Map<string, number> | undefined> => {
  const store = voteStore();
  if (!store) return undefined;
  try {
    const response = await fetch(`${store.url}/pipeline`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${store.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify([
        ["HINCRBY", VOTES_KEY, modelId, "1"],
        ["HGETALL", VOTES_KEY],
      ]),
      signal: AbortSignal.timeout(3_000),
    });
    if (!response.ok) return undefined;
    const [, all] = (await response.json()) as { result?: unknown }[];
    const pairs = Array.isArray(all?.result) ? (all.result as string[]) : [];
    const totals = new Map<string, number>();
    for (let n = 0; n + 1 < pairs.length; n += 2)
      totals.set(pairs[n], Number(pairs[n + 1]) || 0);
    return totals;
  } catch {
    return undefined;
  }
};

// Every model that can be upvoted, most votes first, as a fixed-width table.
const votesTable = (totals: Map<string, number>): string => {
  const rows: [string, number][] = roadmapEntries
    .filter((entry) => !entry.release)
    .map((entry): [string, number] => [
      entry.name ?? entry.category,
      totals.get(entry.id) ?? 0,
    ])
    .sort((a, b) => b[1] - a[1]);
  const width = Math.max(5, ...rows.map(([name]) => name.length));
  const line = (name: string, votes: string) =>
    `${name.padEnd(width)}  ${votes.padStart(7)}`;
  return [
    line("Model", "Upvotes"),
    line("-".repeat(width), "-------"),
    ...rows.map(([name, votes]) => line(name, String(votes))),
  ].join("\n");
};

const fail = (error: string, status: number): Response =>
  Response.json({ error }, { status });

type Message = { text: string; blocks: object[] };

const voteMessage = async (entry: RoadmapEntry): Promise<Message> => {
  const name = entry.name ?? entry.category;
  const totals = await countVote(entry.id);
  return {
    text: `User upvoted ${name}`,
    blocks: [
      {
        type: "section",
        text: { type: "mrkdwn", text: `User upvoted *${name}*` },
      },
      ...(totals
        ? [
            {
              type: "section",
              text: {
                type: "mrkdwn",
                text: "```\n" + votesTable(totals) + "\n```",
              },
            },
          ]
        : []),
    ],
  };
};

const suggestionMessage = (
  entry: RoadmapEntry,
  suggestion: string,
): Message => {
  const heading = `Model name suggestion for ${entry.category}`;
  return {
    text: heading,
    blocks: [
      { type: "section", text: { type: "plain_text", text: heading } },
      { type: "section", text: { type: "plain_text", text: suggestion } },
    ],
  };
};

export const POST = async (request: Request): Promise<Response> => {
  if (request.method !== "POST")
    return new Response(null, { status: 405, headers: { Allow: "POST" } });

  if (request.headers.get("origin") !== new URL(request.url).origin) {
    return fail("Invalid request origin", 403);
  }

  if (
    request.headers.get("content-type")?.split(";")[0]?.trim() !==
    "application/json"
  ) {
    return fail("Expected JSON", 415);
  }

  const input = await readSubmission(request);
  if (!input || typeof input !== "object" || !("modelId" in input)) {
    return fail("Invalid suggestion", 400);
  }

  const entry = roadmapEntries.find(
    (candidate) => candidate.id === input.modelId,
  );
  if (!entry) return fail("Invalid suggestion", 400);

  const isVote = "vote" in input;
  let suggestion = "";
  if (isVote) {
    if (input.vote !== "up" || entry.release) return fail("Invalid vote", 400);
  } else {
    suggestion =
      "suggestion" in input && typeof input.suggestion === "string"
        ? input.suggestion.trim()
        : "";
    if (
      !canSuggestName(entry) ||
      !suggestion ||
      suggestion.length > MODEL_NAME_SUGGESTION_MAX_LENGTH
    ) {
      return fail("Invalid suggestion", 400);
    }
  }

  const webhook = slackWebhook();
  if (!webhook) return fail("Suggestions are temporarily unavailable", 503);

  const client = process.env.VERCEL
    ? (request.headers.get("x-vercel-forwarded-for") ?? "unknown")
    : "local";
  if (!acceptRequest(client)) return fail("Too many suggestions", 429);

  const message = isVote
    ? await voteMessage(entry)
    : suggestionMessage(entry, suggestion);

  try {
    const response = await fetch(webhook, {
      method: "POST",
      redirect: "error",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...message,
        unfurl_links: false,
        unfurl_media: false,
      }),
      signal: AbortSignal.timeout(5_000),
    });

    if (response.ok && (await response.text()).trim() === "ok") {
      return new Response(null, { status: 204 });
    }

    console.error("Model name webhook rejected delivery", response.status);
  } catch {
    console.error("Model name webhook delivery failed");
  }

  return fail("Could not deliver the suggestion", 502);
};
