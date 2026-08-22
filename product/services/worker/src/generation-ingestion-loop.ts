import {
  GenerationSettledSchema,
  type GenerationSettled,
} from "@gradiated/contracts";
import type { GenerationWriter } from "@gradiated/control";
import type { RedisClientType } from "@gradiated/valkey";

type StreamMessage = {
  id: string;
  message: Record<string, string>;
};

export type GenerationIngestionOptions = {
  batchSize: number;
  claimIdleMs: number;
  consumer: string;
  group: string;
  readBlockMs: number;
  stream: string;
  onReady?: (() => Promise<void>) | undefined;
  onBacklog?:
    | ((
        pending: number,
        unread: number,
        oldestPendingId: string | null,
      ) => void)
    | undefined;
  onMessagesProcessed?:
    ((source: "new" | "recovered", count: number) => void) | undefined;
  onPass?: ((durationSeconds: number) => void) | undefined;
};

const streamIdPattern = /^(0|[1-9][0-9]*)-(0|[1-9][0-9]*)$/;
const settlementSlotMilliseconds = 300_000n;

const parseStreamId = (streamId: string): [bigint, bigint] => {
  const match = streamIdPattern.exec(streamId);
  if (!match?.[1] || !match[2]) {
    throw new Error(`Invalid Valkey Stream ID: ${streamId}`);
  }
  return [BigInt(match[1]), BigInt(match[2])];
};

export const deriveSettlementSlotId = (streamId: string): string => {
  const [milliseconds] = parseStreamId(streamId);
  const slotStart =
    (milliseconds / settlementSlotMilliseconds) * settlementSlotMilliseconds;
  if (slotStart > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new Error(
      `Valkey Stream ID is outside the supported date range: ${streamId}`,
    );
  }

  const iso = new Date(Number(slotStart)).toISOString();
  const compact = iso.slice(0, 19).replaceAll("-", "").replaceAll(":", "");
  return `${compact}Z-300s-v1`;
};

export const parseGenerationStreamMessage = (
  entry: StreamMessage,
): GenerationSettled => {
  const fields = Object.keys(entry.message).sort();
  if (
    fields.length !== 2 ||
    fields[0] !== "generation_id" ||
    fields[1] !== "properties"
  ) {
    throw new Error(`Invalid generation stream fields at ${entry.id}`);
  }

  const generationId = entry.message.generation_id;
  const serializedProperties = entry.message.properties;
  if (!generationId || !serializedProperties) {
    throw new Error(`Missing generation stream field at ${entry.id}`);
  }

  let properties: unknown;
  try {
    properties = JSON.parse(serializedProperties);
  } catch {
    throw new Error(`Invalid generation properties JSON at ${entry.id}`);
  }

  const result = GenerationSettledSchema.safeParse({
    generation_id: generationId,
    properties,
  });
  if (!result.success) {
    throw new Error(`Invalid generation event at ${entry.id}`);
  }
  return result.data;
};

export const nextStreamId = (streamId: string): string => {
  const [milliseconds, sequence] = parseStreamId(streamId);
  return `${milliseconds}-${sequence + 1n}`;
};

export const getSafeTrimThreshold = (
  firstPendingId: string | null,
  lastDeliveredId: string,
): string | null => {
  if (firstPendingId) return firstPendingId;
  if (lastDeliveredId === "0-0") return null;
  return nextStreamId(lastDeliveredId);
};

export const processGenerationMessage = async (
  client: Pick<RedisClientType, "xAck">,
  writer: GenerationWriter,
  options: Pick<GenerationIngestionOptions, "group" | "stream">,
  entry: StreamMessage,
): Promise<void> => {
  const event = parseGenerationStreamMessage(entry);
  await writer.insertGeneration(event, deriveSettlementSlotId(entry.id));
  await client.xAck(options.stream, options.group, entry.id);
};

const ensureConsumerGroup = async (
  client: RedisClientType,
  options: GenerationIngestionOptions,
): Promise<void> => {
  try {
    await client.xGroupCreate(options.stream, options.group, "0", {
      MKSTREAM: true,
    });
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes("BUSYGROUP")) {
      throw error;
    }
  }
};

const processMessages = async (
  client: RedisClientType,
  writer: GenerationWriter,
  options: GenerationIngestionOptions,
  messages: readonly (StreamMessage | null)[],
): Promise<number> => {
  let processed = 0;
  for (const message of messages) {
    if (message) {
      await processGenerationMessage(client, writer, options, message);
      processed += 1;
    }
  }
  return processed;
};

const recoverStaleMessages = async (
  client: RedisClientType,
  writer: GenerationWriter,
  options: GenerationIngestionOptions,
): Promise<void> => {
  let cursor = "0-0";
  do {
    const claimed = await client.xAutoClaim(
      options.stream,
      options.group,
      options.consumer,
      options.claimIdleMs,
      cursor,
      { COUNT: options.batchSize },
    );
    const processed = await processMessages(
      client,
      writer,
      options,
      claimed.messages,
    );
    options.onMessagesProcessed?.("recovered", processed);
    cursor = claimed.nextId;
  } while (cursor !== "0-0");
};

const trimAcknowledgedMessages = async (
  client: RedisClientType,
  options: GenerationIngestionOptions,
): Promise<void> => {
  const [pending, groups] = await Promise.all([
    client.xPending(options.stream, options.group),
    client.xInfoGroups(options.stream),
  ]);
  const group = groups.find((candidate) => candidate.name === options.group);
  if (!group)
    throw new Error(`Valkey consumer group is missing: ${options.group}`);

  options.onBacklog?.(
    Number(pending.pending),
    Number(group.lag),
    pending.firstId ? String(pending.firstId) : null,
  );

  const threshold = getSafeTrimThreshold(
    pending.firstId,
    String(group["last-delivered-id"]),
  );
  if (threshold) {
    await client.xTrim(options.stream, "MINID", threshold, {
      strategyModifier: "=",
    });
  }
};

export const runGenerationIngestionLoop = async (
  client: RedisClientType,
  writer: GenerationWriter,
  options: GenerationIngestionOptions,
  signal: AbortSignal,
): Promise<void> => {
  await ensureConsumerGroup(client, options);
  await options.onReady?.();

  while (!signal.aborted) {
    const started = process.hrtime.bigint();
    await recoverStaleMessages(client, writer, options);
    const streams = await client.xReadGroup(
      options.group,
      options.consumer,
      { key: options.stream, id: ">" },
      { COUNT: options.batchSize, BLOCK: options.readBlockMs },
    );
    for (const stream of streams ?? []) {
      const processed = await processMessages(
        client,
        writer,
        options,
        stream.messages,
      );
      options.onMessagesProcessed?.("new", processed);
    }
    await trimAcknowledgedMessages(client, options);
    options.onPass?.(Number(process.hrtime.bigint() - started) / 1e9);
  }
};
