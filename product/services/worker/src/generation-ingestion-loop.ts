import type { GenerationWriter } from "@gradiated/control";
import type { RedisClientType } from "@gradiated/valkey";

import { readConsumerGroupProgress, trimThreshold } from "./consumer-group.js";
import {
  parseGenerationStreamEntry,
  type GenerationStreamEntry,
  type StreamMessage,
} from "./generation-stream-entry.js";
import { serviceLog } from "./logging.js";
import { stopwatch, type WorkerMetrics } from "./metrics.js";

export type GenerationIngestionConfig = {
  stream: string;
  group: string;
  consumer: string;
  batchSize: number;
  claimIdleMs: number;
  readBlockMs: number;
};

export type IngestionTelemetry = Pick<
  WorkerMetrics,
  | "recordIngestedMessages"
  | "recordDeletedMessages"
  | "recordIngestionBacklog"
  | "recordPass"
>;

export type GenerationIngestion = {
  client: RedisClientType;
  writer: GenerationWriter;
  config: GenerationIngestionConfig;
  telemetry: IngestionTelemetry;
  onReady: () => Promise<void>;
  signal: AbortSignal;
};

const parseValidPrefix = (entries: readonly (StreamMessage | null)[]) => {
  const valid: (GenerationStreamEntry & { id: string })[] = [];

  for (const entry of entries) {
    if (!entry) continue;

    try {
      valid.push({ id: entry.id, ...parseGenerationStreamEntry(entry) });
    } catch (error) {
      return { valid, poison: error };
    }
  }

  return { valid, poison: null };
};

// Each insert waits for an async-insert flush, so the batch inserts
// concurrently to share flushes. Entries behind a poison entry stay pending.
const consume = async (
  { client, writer, config }: GenerationIngestion,
  entries: readonly (StreamMessage | null)[],
): Promise<number> => {
  const { valid, poison } = parseValidPrefix(entries);

  const inserts = await Promise.allSettled(
    valid.map(({ event, slotId }) => writer.insertGeneration(event, slotId)),
  );
  const insertedIds = valid
    .filter((_entry, index) => inserts[index]?.status === "fulfilled")
    .map(({ id }) => id);
  const failedInsert = inserts.find((insert) => insert.status === "rejected");

  if (insertedIds.length > 0) {
    await client.xAck(config.stream, config.group, insertedIds);
  }

  if (failedInsert) throw failedInsert.reason;
  if (poison) throw poison;

  return insertedIds.length;
};

const ensureConsumerGroup = async ({
  client,
  config,
}: GenerationIngestion): Promise<void> => {
  try {
    await client.xGroupCreate(config.stream, config.group, "0", {
      MKSTREAM: true,
    });
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes("BUSYGROUP")) {
      throw error;
    }
  }
};

const reportDeleted = (telemetry: IngestionTelemetry, count: number): void => {
  if (count === 0) return;

  serviceLog("error", "generation_entry_deleted", {
    loop: "generation_ingestion",
    dependency: "valkey",
  });
  telemetry.recordDeletedMessages(count);
};

const recoverStale = async (ingestion: GenerationIngestion): Promise<void> => {
  const { client, config, telemetry } = ingestion;
  let cursor = "0-0";

  do {
    const claimed = await client.xAutoClaim(
      config.stream,
      config.group,
      config.consumer,
      config.claimIdleMs,
      cursor,
      { COUNT: config.batchSize },
    );
    const consumed = await consume(ingestion, claimed.messages);

    telemetry.recordIngestedMessages("recovered", consumed);
    reportDeleted(telemetry, claimed.deletedMessages.length);
    cursor = claimed.nextId;
  } while (cursor !== "0-0" && !ingestion.signal.aborted);
};

const readNew = async (ingestion: GenerationIngestion): Promise<void> => {
  const { client, config, telemetry } = ingestion;
  const streams = await client.xReadGroup(
    config.group,
    config.consumer,
    { key: config.stream, id: ">" },
    { COUNT: config.batchSize, BLOCK: config.readBlockMs },
  );

  for (const stream of streams ?? []) {
    const consumed = await consume(ingestion, stream.messages);

    telemetry.recordIngestedMessages("new", consumed);
  }
};

const recordBacklogAndTrim = async ({
  client,
  config,
  telemetry,
}: GenerationIngestion): Promise<void> => {
  const progress = await readConsumerGroupProgress(client, config);

  telemetry.recordIngestionBacklog({
    pending: progress.pending,
    unread: progress.unread,
    oldestPendingMilliseconds: progress.oldestPending?.milliseconds ?? null,
  });

  const threshold = trimThreshold(progress);
  if (!threshold) return;

  await client.xTrim(config.stream, "MINID", threshold, {
    strategyModifier: "=",
  });
};

export const runGenerationIngestionLoop = async (
  ingestion: GenerationIngestion,
): Promise<void> => {
  await ensureConsumerGroup(ingestion);
  await ingestion.onReady();

  while (!ingestion.signal.aborted) {
    const elapsedSeconds = stopwatch();

    await recoverStale(ingestion);
    if (!ingestion.signal.aborted) await readNew(ingestion);
    await recordBacklogAndTrim(ingestion);

    ingestion.telemetry.recordPass("generation_ingestion", elapsedSeconds());
  }
};
