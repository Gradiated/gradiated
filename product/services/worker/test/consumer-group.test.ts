import { randomUUID } from "node:crypto";

import type { RedisClientType } from "@gradiated/valkey";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  ingestionBoundaryMilliseconds,
  readConsumerGroupProgress,
  trimThreshold,
  type ConsumerGroup,
  type ConsumerGroupProgress,
} from "../src/consumer-group.js";
import { parseStreamId } from "../src/stream-id.js";
import { connectTestValkey } from "./support/valkey.js";

const progress = (
  oldestPendingId: string | null,
  lastDeliveredId: string | null,
): ConsumerGroupProgress => ({
  pending: oldestPendingId ? 1 : 0,
  unread: 0,
  oldestPending: oldestPendingId ? parseStreamId(oldestPendingId) : null,
  lastDelivered: lastDeliveredId ? parseStreamId(lastDeliveredId) : null,
});

describe("consumer group progress", () => {
  it("holds the trim and the ingestion boundary at the oldest pending entry", () => {
    const pending = progress("100-2", "200-4");

    expect(trimThreshold(pending)).toBe("100-2");
    expect(ingestionBoundaryMilliseconds(pending)).toBe(100);
  });

  it("trims through the last delivered entry when none are pending", () => {
    const delivered = progress(null, "200-4");

    expect(trimThreshold(delivered)).toBe("200-5");
    expect(ingestionBoundaryMilliseconds(delivered)).toBe(200);
  });

  it("has no trim or boundary before the group delivers an entry", () => {
    const empty = progress(null, null);

    expect(trimThreshold(empty)).toBeNull();
    expect(ingestionBoundaryMilliseconds(empty)).toBeNull();
  });
});

describe("reading consumer group progress from Valkey", () => {
  let client: RedisClientType;
  let consumer: RedisClientType;

  beforeAll(async () => {
    [client, consumer] = await Promise.all([
      connectTestValkey(),
      connectTestValkey(),
    ]);
  });

  afterAll(async () => {
    await Promise.all([client.close(), consumer.close()]);
  });

  const createGroup = async (): Promise<ConsumerGroup> => {
    const group = {
      stream: `consumer-group-test:${randomUUID()}`,
      group: `group-${randomUUID()}`,
    };
    await client.xGroupCreate(group.stream, group.group, "0", {
      MKSTREAM: true,
    });

    return group;
  };

  const deliver = async ({ stream, group }: ConsumerGroup, count: number) =>
    consumer.xReadGroup(
      group,
      "consumer-a",
      { key: stream, id: ">" },
      { COUNT: count },
    );

  it("reports pending, unread and delivered entries", async () => {
    const group = await createGroup();
    for (const id of ["100-1", "100-2", "100-3"]) {
      await client.xAdd(group.stream, id, { field: "value" });
    }
    await deliver(group, 2);

    const read = await readConsumerGroupProgress(client, group);

    expect(read).toEqual({
      pending: 2,
      unread: 1,
      oldestPending: parseStreamId("100-1"),
      lastDelivered: parseStreamId("100-2"),
    });
  });

  it("reads the pending list and the delivery cursor as one snapshot", async () => {
    const group = await createGroup();
    const entryCount = 200;
    for (let index = 1; index <= entryCount; index += 1) {
      await client.xAdd(group.stream, `100-${index}`, { field: "value" });
    }

    const deliveries = (async () => {
      for (let index = 0; index < entryCount; index += 1) {
        await deliver(group, 1);
      }
    })();
    const snapshots: ConsumerGroupProgress[] = [];
    let delivering = true;
    void deliveries.finally(() => {
      delivering = false;
    });
    while (delivering) {
      snapshots.push(await readConsumerGroupProgress(client, group));
    }
    await deliveries;

    const inconsistent = snapshots.filter(
      (snapshot) =>
        snapshot.lastDelivered !== null && snapshot.oldestPending === null,
    );
    expect(snapshots.length).toBeGreaterThan(1);
    expect(inconsistent).toEqual([]);
  });

  it("rejects a stream that has no such group with a bounded code", async () => {
    const { stream } = await createGroup();

    await expect(
      readConsumerGroupProgress(client, { stream, group: "missing" }),
    ).rejects.toMatchObject({ code: "ECONSUMER_GROUP_MISSING" });
  });

  it("rejects a stream that does not exist yet with a bounded code", async () => {
    await expect(
      readConsumerGroupProgress(client, {
        stream: `consumer-group-test:${randomUUID()}`,
        group: "missing",
      }),
    ).rejects.toMatchObject({ code: "ECONSUMER_GROUP_MISSING" });
  });

  it("keeps a failure that is not a missing group unchanged", async () => {
    const stream = `consumer-group-test:${randomUUID()}`;
    await client.set(stream, "not a stream");

    await expect(
      readConsumerGroupProgress(client, { stream, group: "missing" }),
    ).rejects.not.toHaveProperty("code");

    await client.del(stream);
  });
});
