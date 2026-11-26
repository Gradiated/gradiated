import {
  canSuggestName,
  MODEL_NAME_SUGGESTION_MAX_LENGTH,
  roadmapEntries,
} from "../src/model-roadmap.js";
import type { RoadmapEntry } from "../src/model-roadmap.js";
import {
  hasStore,
  KEYS,
  modelName,
  postToSlack,
  runInStore,
  slackWebhook,
} from "./_roadmap.js";

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

const fail = (error: string, status: number): Response =>
  Response.json({ error }, { status });

// Saved for the daily summary (api/roadmap-digest.ts); suggestions are also
// kept for good.
const store = (entry: RoadmapEntry, suggestion: string | undefined) =>
  suggestion === undefined
    ? runInStore([
        ["HINCRBY", KEYS.totals, entry.id, "1"],
        ["HINCRBY", KEYS.pendingVotes, entry.id, "1"],
      ])
    : (() => {
        const record = JSON.stringify({
          modelId: entry.id,
          suggestion,
          at: new Date().toISOString(),
        });
        return runInStore([
          ["LPUSH", KEYS.suggestions, record],
          ["LPUSH", KEYS.pendingSuggestions, record],
        ]);
      })();

// Without a store there is no summary, so it goes to Slack straight away.
const postNow = (entry: RoadmapEntry, suggestion: string | undefined) =>
  postToSlack(
    suggestion === undefined
      ? {
          text: `User upvoted ${modelName(entry.id)}`,
          blocks: [
            {
              type: "section",
              text: {
                type: "mrkdwn",
                text: `User upvoted *${modelName(entry.id)}*`,
              },
            },
          ],
        }
      : {
          text: `Model name suggestion for ${entry.category}`,
          blocks: [
            {
              type: "section",
              text: {
                type: "plain_text",
                text: `Model name suggestion for ${entry.category}`,
              },
            },
            { type: "section", text: { type: "plain_text", text: suggestion } },
          ],
        },
  );

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

  if (!hasStore() && !slackWebhook())
    return fail("Suggestions are temporarily unavailable", 503);

  const client = process.env.VERCEL
    ? (request.headers.get("x-vercel-forwarded-for") ?? "unknown")
    : "local";
  if (!acceptRequest(client)) return fail("Too many suggestions", 429);

  const text = isVote ? undefined : suggestion;
  if (hasStore() && (await store(entry, text)))
    return new Response(null, { status: 204 });
  // No store, or it failed: post straight away so nothing is lost.
  if (hasStore()) console.error("Roadmap store rejected the write");
  if (await postNow(entry, text)) return new Response(null, { status: 204 });

  return fail("Could not deliver the suggestion", 502);
};
