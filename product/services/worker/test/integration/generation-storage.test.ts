import { randomUUID } from "node:crypto";
import { createClient, type ClickHouseClient } from "@clickhouse/client";
import {
  createGenerationSettlementStore,
  createGenerationWriter,
  createGenerationSettlementReader,
  SettlementFinancialConflictError,
} from "@gradiated/control";
import type { RedisClientType } from "@gradiated/valkey";
import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  inject,
  it,
} from "vitest";

import { createTestDatabase } from "../../../../packages/control/test/support/postgres.js";
import {
  seedOrganization,
  billingAccountRow,
  ledgerRows,
} from "../../../../packages/control/test/support/fixtures.js";
import { processSettlementPass } from "../../src/settlement-loop.js";

import {
  runGenerationIngestionLoop,
  type GenerationIngestionConfig,
} from "../../src/generation-ingestion-loop.js";
import { generationSettled, streamFields } from "../support/generation.js";
import { connectTestValkey } from "../support/valkey.js";

const slotId = "20260815T123000Z-300s-v1";
const timestamp = Date.parse("2026-08-15T12:31:00Z");
let valkey: RedisClientType;
let clickhouse: ClickHouseClient;

beforeAll(async () => {
  valkey = await connectTestValkey();
  clickhouse = createClient({
    url: inject("workerClickHouseUrl"),
    username: "test",
    password: "test",
    database: "test",
    clickhouse_settings: {
      async_insert_busy_timeout_ms: 10,
      async_insert_use_adaptive_busy_timeout: 0,
    },
  });
});
afterAll(async () => {
  await valkey?.close();
  await clickhouse?.close();
});

beforeEach(async () => {
  await clickhouse.command({ query: "truncate table generations" });
});

const configuration = (): GenerationIngestionConfig => ({
  stream: `integration:${randomUUID()}`,
  group: `group-${randomUUID()}`,
  consumer: "worker",
  batchSize: 10,
  claimIdleMs: 0,
  readBlockMs: 10,
});
const onePass = async (config: GenerationIngestionConfig) => {
  const controller = new AbortController();
  await runGenerationIngestionLoop({
    client: valkey,
    writer: createGenerationWriter(clickhouse),
    config,
    signal: controller.signal,
    onReady: async () => {},
    telemetry: {
      recordIngestedMessages: () => {},
      recordDeletedMessages: () => {},
      recordIngestionBacklog: () => {},
      recordPass: () => controller.abort(),
    },
  });
};
const settlements = () =>
  createGenerationSettlementReader(clickhouse).getOrganizationSettlements(
    slotId,
  );

const event = (organizationId: string = randomUUID()) =>
  generationSettled({
    generation_id: randomUUID(),
    properties: { organization_id: organizationId },
  });

describe("generation storage against real Valkey and ClickHouse", () => {
  it("stores materialized fields before acknowledging the stream and aggregates exact tenant totals", async () => {
    const config = configuration();
    const organization = randomUUID();
    const events = [event(organization), event(organization), event()];
    for (const [index, generation] of events.entries()) {
      await valkey.xAdd(
        config.stream,
        `${timestamp}-${index}`,
        streamFields(generation),
      );
    }
    await onePass(config);
    expect((await valkey.xPending(config.stream, config.group)).pending).toBe(
      0,
    );
    expect(await valkey.xLen(config.stream)).toBe(0);
    const rows = await (
      await clickhouse.query({
        query:
          "select id, organization_id, settlement_slot_id, charge from generations where organization_id = {id:UUID}",
        query_params: { id: organization },
        format: "JSONEachRow",
      })
    ).json<{
      id: string;
      organization_id: string;
      settlement_slot_id: string;
      charge: number | string;
    }>();
    expect(rows.map((row) => row.id).sort()).toEqual(
      events
        .slice(0, 2)
        .map((row) => row.generation_id)
        .sort(),
    );
    expect(
      rows.every(
        (row) =>
          row.organization_id === organization &&
          row.settlement_slot_id === slotId &&
          Number(row.charge) === 20,
      ),
    ).toBe(true);
    expect(
      (await settlements()).find((row) => row.organizationId === organization),
    ).toEqual({
      organizationId: organization,
      slotId,
      totalCharge: 40n,
      generationCount: 2n,
    });
  });

  it("keeps failed ClickHouse inserts pending and recovers them after the table becomes available", async () => {
    const config = configuration();
    const generation = event();
    await valkey.xAdd(
      config.stream,
      `${timestamp}-0`,
      streamFields(generation),
    );
    await clickhouse.command({
      query: "rename table generations to unavailable_generations",
    });
    try {
      await expect(onePass(config)).rejects.toThrow();
      expect((await valkey.xPending(config.stream, config.group)).pending).toBe(
        1,
      );
      expect(await valkey.xLen(config.stream)).toBe(1);
    } finally {
      await clickhouse.command({
        query: "rename table unavailable_generations to generations",
      });
    }
    await onePass({ ...config, consumer: "replacement" });
    expect((await valkey.xPending(config.stream, config.group)).pending).toBe(
      0,
    );
    expect(
      (await settlements()).find(
        (row) => row.organizationId === generation.properties.organization_id,
      ),
    ).toMatchObject({
      totalCharge: 20n,
      generationCount: 1n,
    });
  });

  it("does not double bill an insert committed before its stream acknowledgement was lost", async () => {
    const config = configuration();
    const generation = event();
    await valkey.xAdd(
      config.stream,
      `${timestamp}-0`,
      streamFields(generation),
    );
    await valkey.xGroupCreate(config.stream, config.group, "0");
    await valkey.xReadGroup(config.group, "crashed", {
      key: config.stream,
      id: ">",
    });
    await createGenerationWriter(clickhouse).insertGeneration(
      generation,
      slotId,
    );
    expect((await valkey.xPending(config.stream, config.group)).pending).toBe(
      1,
    );

    await onePass(config);
    expect((await valkey.xPending(config.stream, config.group)).pending).toBe(
      0,
    );
    expect(
      (await settlements()).find(
        (row) => row.organizationId === generation.properties.organization_id,
      ),
    ).toMatchObject({
      totalCharge: 20n,
      generationCount: 1n,
    });
  });

  it("settles ingested generations into PostgreSQL exactly once across worker retries", async () => {
    const db = await createTestDatabase();
    const leader = await createGenerationSettlementStore(
      db.pool,
    ).tryAcquireLeadership();
    if (!leader) throw new Error("A fresh test database must grant leadership");
    try {
      const organization = await seedOrganization(db.database, {
        billing: { mode: "prepaid", balance: 1_000n },
      });
      const config = configuration();
      const first = event(organization);
      const events = [first, first, event(organization)];
      for (const [index, generation] of events.entries()) {
        await valkey.xAdd(
          config.stream,
          `${timestamp}-${index}`,
          streamFields(generation),
        );
      }
      await onePass(config);
      const pass = {
        reader: createGenerationSettlementReader(clickhouse),
        leadership: leader,
        ingestionBoundary: async () => Date.parse("2026-08-15T12:35:00Z"),
        now: new Date("2026-08-15T12:40:00Z"),
        cursor: null,
        config: {
          maxSlotsPerPass: 1,
          pollMilliseconds: 1,
          settlementDelayMilliseconds: 0,
        },
      };
      expect((await processSettlementPass(pass)).processedSlots).toBe(1);
      expect((await processSettlementPass(pass)).processedSlots).toBe(1);
      expect(
        (await billingAccountRow(db.database, organization))?.balance,
      ).toBe(960n);
      expect(await ledgerRows(db.database, organization)).toMatchObject([
        {
          amount: -40n,
          balanceAfter: 960n,
          generationCount: 2n,
          sourceType: "generation_settlement_batch",
          sourceId: `${slotId}:${organization}`,
          periodStart: new Date("2026-08-15T12:30:00Z"),
          periodEnd: new Date("2026-08-15T12:35:00Z"),
        },
      ]);
      expect((await valkey.xPending(config.stream, config.group)).pending).toBe(
        0,
      );
    } finally {
      await leader.release();
      await db.dispose();
    }
  });

  it("refuses settlement when actual stored copies disagree on a generation's charge", async () => {
    const generation = event();
    await createGenerationWriter(clickhouse).insertGeneration(
      generation,
      slotId,
    );
    await clickhouse.insert({
      table: "generations",
      columns: ["id", "properties"],
      format: "JSONEachRow",
      values: [
        {
          id: generation.generation_id,
          properties: {
            ...generation.properties,
            settlement: { slot_id: slotId },
            usage: { ...generation.properties.usage, charge: 30 },
          },
        },
      ],
    });
    await expect(settlements()).rejects.toBeInstanceOf(
      SettlementFinancialConflictError,
    );
  });
});
