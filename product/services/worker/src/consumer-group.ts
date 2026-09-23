import type { RedisClientType } from "@gradiated/valkey";

import { WorkerInvariantError } from "./errors.js";
import {
  formatStreamId,
  nextStreamId,
  parseStreamId,
  type StreamId,
} from "./stream-id.js";

export type ConsumerGroup = { stream: string; group: string };

export type ConsumerGroupProgress = {
  pending: number;
  unread: number | null;
  oldestPending: StreamId | null;
  lastDelivered: StreamId | null;
};

export type ConsumerGroupClient = Pick<RedisClientType, "multi">;

const emptyStreamId = "0-0";

const missingGroupReply = /^(NOGROUP|ERR no such key)/;

const isMissingGroup = (error: unknown): boolean =>
  error instanceof Error &&
  "replies" in error &&
  Array.isArray(error.replies) &&
  error.replies.some(
    (reply) => reply instanceof Error && missingGroupReply.test(reply.message),
  );

const missingGroup = (group: string, cause?: unknown) =>
  new WorkerInvariantError(
    "ECONSUMER_GROUP_MISSING",
    `Valkey consumer group is missing: ${group}`,
    { cause },
  );

// One MULTI keeps the pending list and the delivery cursor consistent. A
// delivery between two separate reads would let the trim and the settlement
// boundary pass entries that are delivered but not yet ingested.
export const readConsumerGroupProgress = async (
  client: ConsumerGroupClient,
  { stream, group }: ConsumerGroup,
): Promise<ConsumerGroupProgress> => {
  const [pending, groups] = await client
    .multi()
    .xPending(stream, group)
    .xInfoGroups(stream)
    .execTyped()
    .catch((error: unknown) => {
      throw isMissingGroup(error) ? missingGroup(group, error) : error;
    });
  const info = groups.find((candidate) => candidate.name === group);

  if (!info) throw missingGroup(group);

  const lastDeliveredId = String(info["last-delivered-id"]);

  return {
    pending: Number(pending.pending),
    unread: info.lag === null ? null : Number(info.lag),
    oldestPending:
      pending.firstId === null ? null : parseStreamId(String(pending.firstId)),
    lastDelivered:
      lastDeliveredId === emptyStreamId ? null : parseStreamId(lastDeliveredId),
  };
};

export const trimThreshold = ({
  oldestPending,
  lastDelivered,
}: ConsumerGroupProgress): string | null => {
  if (oldestPending) return formatStreamId(oldestPending);

  return lastDelivered ? formatStreamId(nextStreamId(lastDelivered)) : null;
};

export const ingestionBoundaryMilliseconds = ({
  oldestPending,
  lastDelivered,
}: ConsumerGroupProgress): number | null =>
  (oldestPending ?? lastDelivered)?.milliseconds ?? null;
