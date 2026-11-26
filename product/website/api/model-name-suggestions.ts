import {
  canSuggestName,
  MODEL_NAME_SUGGESTION_MAX_LENGTH,
  roadmapEntries,
} from "../src/model-roadmap.js";

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

const fail = (error: string, status: number): Response =>
  Response.json({ error }, { status });

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

  /* An upvote on an unreleased roadmap model, or a name suggestion. */
  let heading: string;
  let detail: string;
  if ("vote" in input) {
    if (input.vote !== "up" || entry.release) return fail("Invalid vote", 400);
    heading = `Upvote for ${entry.name ?? entry.category}`;
    detail = entry.name ? entry.category : entry.description;
  } else {
    const suggestion =
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
    heading = `Model name suggestion for ${entry.category}`;
    detail = suggestion;
  }

  const webhook = slackWebhook();
  if (!webhook) return fail("Suggestions are temporarily unavailable", 503);

  const client = process.env.VERCEL
    ? (request.headers.get("x-vercel-forwarded-for") ?? "unknown")
    : "local";
  if (!acceptRequest(client)) return fail("Too many suggestions", 429);

  try {
    const response = await fetch(webhook, {
      method: "POST",
      redirect: "error",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: heading,
        unfurl_links: false,
        unfurl_media: false,
        blocks: [
          {
            type: "section",
            text: { type: "plain_text", text: heading },
          },
          {
            type: "section",
            text: { type: "plain_text", text: detail },
          },
        ],
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
