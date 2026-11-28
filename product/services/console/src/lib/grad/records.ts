import type { DatasetRecord } from "@/lib/grad/types";

type Message = NonNullable<DatasetRecord["messages"]>[number];

const PREVIEW_CHARS = 280;

const clip = (text: string) =>
  text.length > PREVIEW_CHARS ? `${text.slice(0, PREVIEW_CHARS - 1)}…` : text;

const textOf = (content: unknown): string => {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";

  return content
    .map((part: unknown) =>
      typeof part === "object" &&
      part !== null &&
      "text" in part &&
      typeof part.text === "string"
        ? part.text
        : "",
    )
    .filter(Boolean)
    .join(" ");
};

const lastOf = (
  messages: readonly Message[] | undefined,
  role: Message["role"],
) =>
  textOf(
    [...(messages ?? [])].reverse().find((message) => message.role === role)
      ?.content,
  );

const fieldText = (value: string | readonly Message[] | undefined) =>
  typeof value === "string"
    ? value
    : lastOf(value, "assistant") || lastOf(value, "user");

export interface RecordPreview {
  input: string;
  output: string;
}

export const recordPreview = (record: DatasetRecord): RecordPreview => {
  const messages = record.messages ?? record.input?.messages;
  const turns = record.output?.turns;

  const input =
    lastOf(messages, "user") || fieldText(record.prompt) || record.query || "";
  const output =
    lastOf(turns, "assistant") ||
    lastOf(messages, "assistant") ||
    fieldText(record.completion) ||
    fieldText(record.chosen) ||
    record.positive ||
    "";

  return { input: clip(input.trim()), output: clip(output.trim()) };
};

export const recordScores = (record: DatasetRecord) =>
  Object.entries(record.scores ?? {}).map(
    ([name, value]) =>
      `${name} ${Number.isInteger(value) ? value : value.toFixed(2)}`,
  );
