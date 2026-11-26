// Shared by the roadmap endpoints. The underscore keeps Vercel from routing it.
import { roadmapEntries } from "../src/model-roadmap.js";

export const KEYS = {
  totals: "roadmap:upvotes",
  pendingVotes: "roadmap:upvotes:pending",
  suggestions: "roadmap:suggestions",
  pendingSuggestions: "roadmap:suggestions:pending",
};

export const slackWebhook = (): URL | undefined => {
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

// The project's Upstash Redis, over its REST API.
const store = (): { url: string; token: string } | undefined => {
  const url =
    process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL || "";
  const token =
    process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN || "";
  return url.startsWith("https://") && token ? { url, token } : undefined;
};

export const hasStore = (): boolean => store() !== undefined;

export const runInStore = async (
  commands: string[][],
): Promise<unknown[] | undefined> => {
  const target = store();
  if (!target) return undefined;
  try {
    const response = await fetch(`${target.url}/pipeline`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${target.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(commands),
      signal: AbortSignal.timeout(3_000),
    });
    if (!response.ok) return undefined;
    const replies = (await response.json()) as {
      result?: unknown;
      error?: string;
    }[];
    if (replies.some((reply) => reply?.error)) return undefined;
    return replies.map((reply) => reply?.result);
  } catch {
    return undefined;
  }
};

export const toCounts = (reply: unknown): Map<string, number> => {
  const pairs = Array.isArray(reply) ? (reply as string[]) : [];
  const counts = new Map<string, number>();
  for (let n = 0; n + 1 < pairs.length; n += 2)
    counts.set(pairs[n], Number(pairs[n + 1]) || 0);
  return counts;
};

export const modelName = (id: string): string => {
  const entry = roadmapEntries.find((candidate) => candidate.id === id);
  return entry ? (entry.name ?? entry.category) : id;
};

export type SlackMessage = { text: string; blocks: object[] };

export const postToSlack = async (message: SlackMessage): Promise<boolean> => {
  const webhook = slackWebhook();
  if (!webhook) return false;
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
    if (response.ok && (await response.text()).trim() === "ok") return true;
    console.error("Roadmap webhook rejected delivery", response.status);
  } catch {
    console.error("Roadmap webhook delivery failed");
  }
  return false;
};

// Slack mrkdwn treats these as markup; visitors' text is shown as typed.
export const escapeSlack = (text: string): string =>
  text.replace(
    /[&<>]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c] ?? c,
  );
