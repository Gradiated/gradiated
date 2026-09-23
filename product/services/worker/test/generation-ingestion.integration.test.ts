import { randomUUID } from "node:crypto";

import type { GenerationWriter } from "@gradiated/control";
import type { RedisClientType } from "@gradiated/valkey";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import {
  runGenerationIngestionLoop,
  type GenerationIngestionConfig,
  type IngestionTelemetry,
} from "../src/generation-ingestion-loop.js";
import {
  generationSettled,
  ingestionTelemetry,
  mispricedFields,
  recordingClickHouse,
  streamFields,
} from "./support/generation.js";
import { connectTestValkey } from "./support/valkey.js";

const slotId = "20260815T123000Z-300s-v1";
const nextSlotId = "20260815T123500Z-300s-v1";
const slotMilliseconds = Date.parse("2026-08-15T12:31:00.000Z");
const nextSlotMilliseconds = Date.parse("2026-08-15T12:36:00.000Z");

let client: RedisClientType;

beforeAll(async () => {
  client = await connectTestValkey();
});

afterAll(async () => {
  await client.close();
});

const streamConfig = (): GenerationIngestionConfig => ({
  batchSize: 10,
  claimIdleMs: 50,
  consumer: "consumer-a",
  group: `group-${randomUUID()}`,
  readBlockMs: 100,
  stream: `generation-settled-test:${randomUUID()}`,
});

const generationId = (index: number): string =>
  `0198ad73-a200-7000-8000-${index.toString().padStart(12, "0")}`;

const addGeneration = async (
  stream: string,
  id: string,
  index: number,
): Promise<string> =>
  client.xAdd(
    stream,
    id,
    streamFields(generationSettled({ generation_id: generationId(index) })),
  );

const runOnePass = async (
  writer: GenerationWriter,
  config: GenerationIngestionConfig,
  telemetry: IngestionTelemetry = ingestionTelemetry(),
): Promise<void> => {
  const controller = new AbortController();
  vi.mocked(telemetry.recordPass).mockImplementation(() => controller.abort());

  await runGenerationIngestionLoop({
    client,
    writer,
    config,
    telemetry,
    onReady: async () => undefined,
    signal: controller.signal,
  });
};

const leavePendingWithDeadConsumer = async (
  options: GenerationIngestionConfig,
  id: string,
): Promise<void> => {
  await client.xGroupCreate(options.stream, options.group, "0", {
    MKSTREAM: true,
  });
  await addGeneration(options.stream, id, 1);
  await client.xReadGroup(
    options.group,
    "dead-consumer",
    { key: options.stream, id: ">" },
    { COUNT: 1 },
  );
};

const pendingCount = async (options: GenerationIngestionConfig) =>
  (await client.xPending(options.stream, options.group)).pending;

const streamIds = async (stream: string) =>
  (await client.xRange(stream, "-", "+")).map((entry) => entry.id);

const sleep = (milliseconds: number) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

describe("generation ingestion loop against Valkey", () => {
  it("inserts each entry with its slot, then acknowledges and trims it", async () => {
    const options = streamConfig();
    const clickHouse = recordingClickHouse();
    await addGeneration(options.stream, `${slotMilliseconds}-1`, 1);
    await addGeneration(options.stream, `${slotMilliseconds}-2`, 2);
    await addGeneration(options.stream, `${nextSlotMilliseconds}-0`, 3);

    await runOnePass(clickHouse.writer, options);

    expect(clickHouse.inserted).toEqual([
      { id: generationId(1), slotId },
      { id: generationId(2), slotId },
      { id: generationId(3), slotId: nextSlotId },
    ]);
    expect(await pendingCount(options)).toBe(0);
    expect(await client.xLen(options.stream)).toBe(0);
  });

  it("leaves a failed insert pending and untrimmed", async () => {
    const options = streamConfig();
    const clickHouse = recordingClickHouse();
    clickHouse.failWith(new Error("ClickHouse unavailable"));
    await addGeneration(options.stream, `${slotMilliseconds}-1`, 1);

    await expect(runOnePass(clickHouse.writer, options)).rejects.toThrow(
      "ClickHouse unavailable",
    );

    expect(await pendingCount(options)).toBe(1);
    expect(await client.xLen(options.stream)).toBe(1);
  });

  it("acknowledges the other entries of a batch when one insert fails", async () => {
    const options = streamConfig();
    const clickHouse = recordingClickHouse();
    const failedId = `${slotMilliseconds}-2`;
    clickHouse.failWith(new Error("ClickHouse unavailable"), generationId(2));
    await addGeneration(options.stream, `${slotMilliseconds}-1`, 1);
    await addGeneration(options.stream, failedId, 2);
    await addGeneration(options.stream, `${slotMilliseconds}-3`, 3);

    await expect(runOnePass(clickHouse.writer, options)).rejects.toThrow(
      "ClickHouse unavailable",
    );

    expect(clickHouse.inserted).toEqual([
      { id: generationId(1), slotId },
      { id: generationId(3), slotId },
    ]);
    const pending = await client.xPendingRange(
      options.stream,
      options.group,
      "-",
      "+",
      10,
    );
    expect(pending.map((entry) => entry.id)).toEqual([failedId]);
  });

  it("inserts the entries of a batch concurrently", async () => {
    const options = streamConfig();
    const started: string[] = [];
    let release: () => void = () => undefined;
    const released = new Promise<void>((resolve) => {
      release = resolve;
    });
    const writer: GenerationWriter = {
      insertGeneration: async (event) => {
        started.push(event.generation_id);
        if (started.length === 3) release();

        await released;
      },
    };
    await addGeneration(options.stream, `${slotMilliseconds}-1`, 1);
    await addGeneration(options.stream, `${slotMilliseconds}-2`, 2);
    await addGeneration(options.stream, `${slotMilliseconds}-3`, 3);

    await runOnePass(writer, options);

    expect(started).toHaveLength(3);
    expect(await pendingCount(options)).toBe(0);
  });

  it("restarts against an existing consumer group", async () => {
    const options = streamConfig();
    const clickHouse = recordingClickHouse();
    await runOnePass(clickHouse.writer, options);
    await addGeneration(options.stream, `${slotMilliseconds}-1`, 1);

    await runOnePass(clickHouse.writer, options);

    expect(clickHouse.inserted).toEqual([{ id: generationId(1), slotId }]);
    expect(await pendingCount(options)).toBe(0);
  });

  it("rejects when the consumer group cannot be created", async () => {
    const options = streamConfig();
    await client.set(options.stream, "not a stream");

    await expect(
      runOnePass(recordingClickHouse().writer, options),
    ).rejects.toThrow("WRONGTYPE");

    await client.del(options.stream);
  });

  it("reclaims an entry that a dead consumer left pending", async () => {
    const options = streamConfig();
    const clickHouse = recordingClickHouse();
    const telemetry = ingestionTelemetry();
    await leavePendingWithDeadConsumer(options, `${slotMilliseconds}-1`);
    await sleep(options.claimIdleMs + 20);

    await runOnePass(clickHouse.writer, options, telemetry);

    expect(clickHouse.inserted).toEqual([{ id: generationId(1), slotId }]);
    const processed = vi.mocked(telemetry.recordIngestedMessages).mock.calls;
    expect(processed).toContainEqual(["recovered", 1]);
    expect(processed).not.toContainEqual(["new", 1]);
    expect(await pendingCount(options)).toBe(0);
    expect(await client.xLen(options.stream)).toBe(0);
  });

  it("reports and releases a pending entry that left the stream", async () => {
    const options = streamConfig();
    const telemetry = ingestionTelemetry();
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const deletedId = `${slotMilliseconds}-1`;
    await leavePendingWithDeadConsumer(options, deletedId);
    await client.xDel(options.stream, deletedId);
    await sleep(options.claimIdleMs + 20);

    await runOnePass(recordingClickHouse().writer, options, telemetry);

    expect(telemetry.recordDeletedMessages).toHaveBeenCalledWith(1);
    expect(log).toHaveBeenCalledWith(
      expect.stringContaining('"event":"generation_entry_deleted"'),
    );
    expect(await pendingCount(options)).toBe(0);
    log.mockRestore();
  });

  it.each([
    [
      "an extra field",
      "EINVALID_STREAM_ENTRY",
      {
        ...streamFields(generationSettled({ generation_id: generationId(9) })),
        prompt: "secret",
      },
    ],
    [
      "invalid JSON",
      "EINVALID_GENERATION_JSON",
      { generation_id: generationId(9), properties: "{not json" },
    ],
    [
      "an invalid event",
      "EINVALID_GENERATION_EVENT",
      { generation_id: generationId(9), properties: JSON.stringify({}) },
    ],
    [
      "a charge that differs from its components",
      "EINVALID_GENERATION_EVENT",
      mispricedFields(generationSettled({ generation_id: generationId(9) })),
    ],
  ])(
    "holds a poison entry with %s and everything behind it",
    async (_case, code, poison) => {
      const options = streamConfig();
      const clickHouse = recordingClickHouse();
      const poisonId = `${slotMilliseconds}-2`;
      await addGeneration(options.stream, `${slotMilliseconds}-1`, 1);
      await client.xAdd(options.stream, poisonId, poison);
      await addGeneration(options.stream, `${slotMilliseconds}-3`, 3);

      await expect(
        runOnePass(clickHouse.writer, options),
      ).rejects.toMatchObject({ code });

      expect(clickHouse.inserted).toEqual([{ id: generationId(1), slotId }]);
      expect(await pendingCount(options)).toBe(2);

      await runOnePass(clickHouse.writer, { ...options, claimIdleMs: 60_000 });

      expect(await streamIds(options.stream)).toEqual([
        poisonId,
        `${slotMilliseconds}-3`,
      ]);

      await expect(
        runOnePass(clickHouse.writer, { ...options, claimIdleMs: 0 }),
      ).rejects.toMatchObject({ code });

      expect(clickHouse.inserted).toHaveLength(1);
      expect(await pendingCount(options)).toBe(2);
      expect(await streamIds(options.stream)).toEqual([
        poisonId,
        `${slotMilliseconds}-3`,
      ]);
    },
  );

  it("stops after the current blocking read when aborted", async () => {
    const controller = new AbortController();
    const telemetry = ingestionTelemetry();

    await runGenerationIngestionLoop({
      client,
      writer: recordingClickHouse().writer,
      config: { ...streamConfig(), readBlockMs: 200 },
      telemetry,
      onReady: async () => {
        setTimeout(() => controller.abort(), 20);
      },
      signal: controller.signal,
    });

    expect(telemetry.recordPass).toHaveBeenCalledOnce();
  });

  it("reports the entry that another consumer still holds as backlog", async () => {
    const options = streamConfig();
    const telemetry = ingestionTelemetry();
    const clickHouse = recordingClickHouse();
    await leavePendingWithDeadConsumer(options, `${slotMilliseconds}-1`);
    await addGeneration(options.stream, `${slotMilliseconds}-2`, 2);

    await runOnePass(
      clickHouse.writer,
      { ...options, claimIdleMs: 60_000 },
      telemetry,
    );

    expect(clickHouse.inserted).toEqual([{ id: generationId(2), slotId }]);
    expect(telemetry.recordIngestionBacklog).toHaveBeenCalledWith({
      pending: 1,
      unread: 0,
      oldestPendingMilliseconds: slotMilliseconds,
    });
  });
});
