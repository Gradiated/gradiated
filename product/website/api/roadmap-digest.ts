// The day's roadmap activity in one Slack message, run by Vercel Cron
// (vercel.json). Posts nothing on a quiet day.
import { roadmapEntries } from "../src/model-roadmap.js";
import {
  escapeSlack,
  KEYS,
  modelName,
  postToSlack,
  runInStore,
  toCounts,
} from "./_roadmap.js";

const SHOWN_SUGGESTIONS = 40;
// Under Slack's 3,000-character section limit, even after escaping.
const LINE_MAX = 2_800;

const table = (today: Map<string, number>, totals: Map<string, number>) => {
  const rows = roadmapEntries
    .filter((entry) => !entry.release)
    .map((entry) => ({
      name: entry.name ?? entry.category,
      today: today.get(entry.id) ?? 0,
      total: totals.get(entry.id) ?? 0,
    }))
    .sort((a, b) => b.today - a.today || b.total - a.total);
  const width = Math.max(5, ...rows.map((row) => row.name.length));
  const line = (name: string, day: string, total: string) =>
    `${name.padEnd(width)}  ${day.padStart(5)}  ${total.padStart(5)}`;
  return [
    line("Model", "Today", "Total"),
    line("-".repeat(width), "-----", "-----"),
    ...rows.map((row) =>
      line(row.name, row.today ? `+${row.today}` : "0", String(row.total)),
    ),
  ].join("\n");
};

type Suggestion = { modelId: string; suggestion: string };

const parse = (raw: unknown): Suggestion | undefined => {
  try {
    const value = JSON.parse(String(raw)) as Suggestion;
    return typeof value.modelId === "string" &&
      typeof value.suggestion === "string"
      ? value
      : undefined;
  } catch {
    return undefined;
  }
};

export const GET = async (request: Request): Promise<Response> => {
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`)
    return new Response(null, { status: 401 });

  // One run at a time: a second, overlapping call finds the lock and stops.
  const lock = await runInStore([
    ["SET", "roadmap:digest:lock", "1", "NX", "EX", "120"],
  ]);
  if (!lock) return new Response("Store unavailable", { status: 503 });
  if (lock[0] !== "OK") return Response.json({ posted: false, busy: true });
  try {
    return await digest();
  } finally {
    await runInStore([["DEL", "roadmap:digest:lock"]]);
  }
};

const digest = async (): Promise<Response> => {
  const replies = await runInStore([
    ["HGETALL", KEYS.pendingVotes],
    ["LRANGE", KEYS.pendingSuggestions, "0", "-1"],
    ["HGETALL", KEYS.totals],
  ]);
  if (!replies) return new Response("Store unavailable", { status: 503 });

  const today = new Map(
    [...toCounts(replies[0])].filter(([, count]) => count > 0),
  );
  const rawSuggestions = Array.isArray(replies[1]) ? replies[1] : [];
  // Stored newest first; the summary reads oldest first.
  const suggestions = rawSuggestions
    .map(parse)
    .filter((value): value is Suggestion => value !== undefined)
    .reverse();
  const votes = [...today.values()].reduce((sum, count) => sum + count, 0);
  if (!votes && !suggestions.length)
    return Response.json({ posted: false, votes, suggestions: 0 });

  const summary = `${votes} upvote${votes === 1 ? "" : "s"} · ${suggestions.length} name suggestion${suggestions.length === 1 ? "" : "s"}`;
  const blocks: object[] = [
    {
      type: "section",
      text: { type: "mrkdwn", text: `*Roadmap today:* ${summary}` },
    },
  ];
  if (votes)
    blocks.push({
      type: "section",
      text: {
        type: "mrkdwn",
        text: "```\n" + table(today, toCounts(replies[2])) + "\n```",
      },
    });
  if (suggestions.length) {
    const lines = suggestions
      .slice(0, SHOWN_SUGGESTIONS)
      .map((item) =>
        `• *${escapeSlack(modelName(item.modelId))}*: ${escapeSlack(item.suggestion).replaceAll("\n", " ")}`.slice(
          0,
          LINE_MAX,
        ),
      );
    if (suggestions.length > SHOWN_SUGGESTIONS)
      lines.push(
        `_…and ${suggestions.length - SHOWN_SUGGESTIONS} more, kept in the store._`,
      );
    // Slack caps a section at 3,000 characters.
    let chunk = "*Name suggestions*";
    for (const line of lines) {
      if (chunk.length + line.length + 1 > 2_900) {
        blocks.push({ type: "section", text: { type: "mrkdwn", text: chunk } });
        chunk = "";
      }
      chunk += (chunk ? "\n" : "") + line;
    }
    blocks.push({ type: "section", text: { type: "mrkdwn", text: chunk } });
  }

  if (!(await postToSlack({ text: `Roadmap today: ${summary}`, blocks })))
    return new Response("Slack delivery failed", { status: 502 });

  // Clear only what was summarised, so activity during the run carries over.
  const cleared = await runInStore([
    ...[...today].map(([id, count]) => [
      "HINCRBY",
      KEYS.pendingVotes,
      id,
      String(-count),
    ]),
    ["LTRIM", KEYS.pendingSuggestions, "0", String(-rawSuggestions.length - 1)],
  ]);
  if (!cleared) {
    // Posted but not cleared: the next summary would repeat it, so flag it.
    console.error("Roadmap digest posted but could not clear the day");
    return Response.json(
      { posted: true, cleared: false, votes, suggestions: suggestions.length },
      { status: 500 },
    );
  }
  return Response.json({
    posted: true,
    votes,
    suggestions: suggestions.length,
  });
};
