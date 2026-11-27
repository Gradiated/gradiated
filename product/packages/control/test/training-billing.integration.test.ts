import { randomUUID } from "node:crypto";

import { UsageEventSchema, type UsageEvent } from "@gradiated/contracts";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import {
  createTrainingBillingService,
  UsageEventRejectedError,
  type TrainingBillingService,
} from "../src/billing/training-billing.js";
import { amountForQuantity } from "../src/billing/price-lists.js";
import type { UsageEventRow } from "../src/clickhouse/usage-event-ingestion.js";
import {
  priceListItems,
  priceLists,
  workspaces,
} from "../src/db/schema/index.js";
import {
  billingAccountRow,
  ledgerRows,
  seedOrganization,
  seedWorkspace,
} from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const PLACEHOLDER = "pv_training_2026_11_27_placeholder";
const QWEN3_8B_NANO_USD_PER_MTOK = 400_000_000n;

describe("training billing", () => {
  let testDatabase: TestDatabase;
  let inserted: UsageEventRow[][];
  let billing: TrainingBillingService;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
  });

  afterAll(() => testDatabase.dispose());

  const service = (
    insert = vi.fn(async (rows: UsageEventRow[]) => {
      inserted.push(rows);
    }),
  ) => {
    inserted = [];
    billing = createTrainingBillingService(testDatabase.database, { insert });

    return billing;
  };

  const customer = async (
    billingSeed: { mode: "prepaid" | "invoiced"; balance: bigint } = {
      mode: "prepaid",
      balance: 10_000_000_000n,
    },
    status: "active" | "suspended" = "active",
  ) => {
    const organizationId = await seedOrganization(testDatabase.database, {
      status,
      billing: billingSeed,
    });
    const workspaceId = await seedWorkspace(testDatabase.database, {
      organizationId,
      isDefault: true,
    });

    return { organizationId, workspaceId };
  };

  const usageEvent = (
    workspaceId: string,
    fields: Partial<Record<keyof UsageEvent, unknown>> = {},
  ): UsageEvent => {
    const quantity = Number(fields.quantity ?? 1_048_576);

    return UsageEventSchema.parse({
      event_id: `training:run-usage:run_${randomUUID()}:1:${quantity}`,
      workspace_id: workspaceId,
      product: "training",
      sku: "train:qwen/qwen3-8b",
      quantity,
      amount_nano_usd: amountForQuantity(
        BigInt(quantity),
        QWEN3_8B_NANO_USD_PER_MTOK,
      ).toString(),
      price_version: PLACEHOLDER,
      occurred_at: "2026-11-27T12:00:00.000Z",
      subject_id: "run_1",
      tags: { attempt: "1", recipe_kind: "sft" },
      ...fields,
    });
  };

  describe("prices", () => {
    it("serves the placeholder training price list as current", async () => {
      const list = await service().priceList({ product: "training" });

      expect(list).toMatchObject({
        id: PLACEHOLDER,
        product: "training",
        placeholder: true,
      });
      expect(
        list.items.find((item) => item.sku === "train:qwen/qwen3-8b"),
      ).toEqual({
        sku: "train:qwen/qwen3-8b",
        unit: "token",
        priceNanoUsdPerMillion: QWEN3_8B_NANO_USD_PER_MTOK,
      });
    });

    it("prices every placeholder model, larger models higher", async () => {
      const list = await service().priceList({ product: "training" });
      const price = (sku: string) =>
        list.items.find((item) => item.sku === sku)?.priceNanoUsdPerMillion;

      expect(list.items).toHaveLength(8);
      const qwen = ["0.6b", "1.7b", "4b", "8b", "14b", "32b"].map((size) =>
        price(`train:qwen/qwen3-${size}`),
      );
      expect(qwen).toEqual([...qwen].sort((a, b) => Number(a! - b!)));
    });

    it("serves an older version by id after a newer one takes effect", async () => {
      const id = `pv_test_${randomUUID().replaceAll("-", "").slice(0, 12)}`;
      await testDatabase.database.insert(priceLists).values({
        id,
        product: "training",
        effectiveAt: new Date("2026-11-28T00:00:00Z"),
        placeholder: false,
      });
      await testDatabase.database.insert(priceListItems).values({
        priceListId: id,
        sku: "train:qwen/qwen3-8b",
        unit: "token",
        priceNanoUsdPerMillion: 500_000_000n,
      });
      const later = createTrainingBillingService(
        testDatabase.database,
        { insert: async () => undefined },
        () => new Date("2026-11-29T00:00:00Z"),
      );

      expect((await later.priceList({ product: "training" })).id).toBe(id);
      expect(
        (
          await later.priceList({
            product: "training",
            priceVersion: PLACEHOLDER,
          })
        ).id,
      ).toBe(PLACEHOLDER);

      await testDatabase.database
        .delete(priceListItems)
        .where(eq(priceListItems.priceListId, id));
      await testDatabase.database
        .delete(priceLists)
        .where(eq(priceLists.id, id));
    });

    it("reports an unknown version as not found", async () => {
      await expect(
        service().priceList({ product: "training", priceVersion: "pv_nope" }),
      ).rejects.toMatchObject({ code: "not_found" });
    });
  });

  describe("usage ingest", () => {
    it("debits the balance once per event and records it in ClickHouse", async () => {
      const { organizationId, workspaceId } = await customer();
      const event = usageEvent(workspaceId);

      const first = await service().ingestUsageEvents([event]);
      const replay = await billing.ingestUsageEvents([event]);

      expect(first).toEqual({ accepted: 1, duplicates: 0 });
      expect(replay).toEqual({ accepted: 0, duplicates: 1 });
      expect(await ledgerRows(testDatabase.database, organizationId)).toEqual([
        expect.objectContaining({
          type: "usage",
          sourceType: "usage_event",
          sourceId: event.event_id,
          amount: -419_430_400n,
          balanceAfter: 10_000_000_000n - 419_430_400n,
        }),
      ]);
      expect(
        (await billingAccountRow(testDatabase.database, organizationId))
          ?.balance,
      ).toBe(10_000_000_000n - 419_430_400n);
      expect(inserted).toEqual([
        [
          {
            eventId: event.event_id,
            organizationId,
            workspaceId,
            product: "training",
            sku: "train:qwen/qwen3-8b",
            quantity: 1_048_576n,
            amountNanoUsd: 419_430_400n,
            priceVersion: PLACEHOLDER,
            occurredAt: new Date("2026-11-27T12:00:00.000Z"),
            subjectId: "run_1",
            tags: { attempt: "1", recipe_kind: "sft" },
          },
        ],
        expect.any(Array),
      ]);
    });

    it("bills a suspended organization's usage", async () => {
      const { organizationId, workspaceId } = await customer(
        undefined,
        "suspended",
      );

      await service().ingestUsageEvents([usageEvent(workspaceId)]);

      expect(
        await ledgerRows(testDatabase.database, organizationId),
      ).toHaveLength(1);
    });

    it("records a zero-amount event without a ledger row", async () => {
      const { organizationId, workspaceId } = await customer();

      const result = await service().ingestUsageEvents([
        usageEvent(workspaceId, { quantity: 0 }),
      ]);

      expect(result).toEqual({ accepted: 1, duplicates: 0 });
      expect(await ledgerRows(testDatabase.database, organizationId)).toEqual(
        [],
      );
      expect(inserted[0]).toHaveLength(1);
    });

    it.each<
      [
        string,
        (workspaceId: string) => Partial<Record<keyof UsageEvent, unknown>>,
      ]
    >([
      ["a different amount", () => ({ amount_nano_usd: "1" })],
      ["an unknown version", () => ({ price_version: "pv_unknown" })],
      ["an unpriced SKU", () => ({ sku: "train:acme/unknown-1b" })],
    ])(
      "rejects %s as a price mismatch and bills nothing",
      async (_name, fields) => {
        const { organizationId, workspaceId } = await customer();
        const good = usageEvent(workspaceId);
        const bad = usageEvent(workspaceId, fields(workspaceId));

        await expect(
          service().ingestUsageEvents([good, bad]),
        ).rejects.toMatchObject({
          code: "price_mismatch",
          eventId: bad.event_id,
        });
        expect(await ledgerRows(testDatabase.database, organizationId)).toEqual(
          [],
        );
        expect(inserted).toEqual([]);
      },
    );

    it("rejects an unknown workspace", async () => {
      const event = usageEvent(randomUUID());

      const rejection = service().ingestUsageEvents([event]);

      await expect(rejection).rejects.toBeInstanceOf(UsageEventRejectedError);
      await expect(rejection).rejects.toMatchObject({
        code: "unknown_workspace",
        eventId: event.event_id,
      });
    });

    it("rejects a distribution channel's workspace", async () => {
      const organizationId = await seedOrganization(testDatabase.database, {
        kind: "distribution_channel",
        billing: { mode: "invoiced", balance: 0n },
      });
      const workspaceId = await seedWorkspace(testDatabase.database, {
        organizationId,
      });

      await expect(
        service().ingestUsageEvents([usageEvent(workspaceId)]),
      ).rejects.toMatchObject({ code: "unknown_workspace" });
    });

    it("rejects a replay with a different quantity as a conflict", async () => {
      const { workspaceId } = await customer();
      const event = usageEvent(workspaceId);
      await service().ingestUsageEvents([event]);

      await expect(
        billing.ingestUsageEvents([
          usageEvent(workspaceId, {
            event_id: event.event_id,
            quantity: 2_000_000,
            amount_nano_usd: amountForQuantity(
              2_000_000n,
              QWEN3_8B_NANO_USD_PER_MTOK,
            ).toString(),
          }),
        ]),
      ).rejects.toMatchObject({ code: "event_conflict" });
    });

    it("keeps the ledger when ClickHouse fails, so a retry only records", async () => {
      const { organizationId, workspaceId } = await customer();
      const event = usageEvent(workspaceId);
      const failing = service(
        vi.fn(async () => {
          throw new Error("ClickHouse is down");
        }),
      );

      await expect(failing.ingestUsageEvents([event])).rejects.toThrow(
        "ClickHouse is down",
      );
      const retry = await service().ingestUsageEvents([event]);

      expect(retry).toEqual({ accepted: 0, duplicates: 1 });
      expect(
        await ledgerRows(testDatabase.database, organizationId),
      ).toHaveLength(1);
      expect(inserted).toHaveLength(1);
    });

    it("never accepts inference or eval usage", () => {
      const event = {
        ...usageEvent(randomUUID()),
        product: "inference",
        sku: "inference:qwen/qwen3-8b:prompt",
        tags: { lane: "eval", billed_by: "gateway" },
      };

      expect(UsageEventSchema.safeParse(event).success).toBe(false);
    });
  });

  describe("balance check", () => {
    it.each<[bigint, boolean]>([
      [10_000_000_000n, true],
      [10_000_000_001n, false],
    ])(
      "allows a prepaid estimate of %s only within the balance",
      async (estimate, allowed) => {
        const { workspaceId } = await customer();

        expect(
          await service().checkBalance({
            workspace_id: workspaceId,
            estimated_amount_nano_usd: estimate,
          }),
        ).toEqual(
          allowed ? { allowed } : { allowed, reason: "insufficient_balance" },
        );
      },
    );

    it("accepts an estimate in USD", async () => {
      const { workspaceId } = await customer();

      expect(
        await service().checkBalance({
          workspace_id: workspaceId,
          estimated_cost_usd: 10.5,
        }),
      ).toEqual({ allowed: false, reason: "insufficient_balance" });
    });

    it("always allows an invoiced organization", async () => {
      const { workspaceId } = await customer({
        mode: "invoiced",
        balance: -5n,
      });

      expect(
        await service().checkBalance({
          workspace_id: workspaceId,
          estimated_amount_nano_usd: 1_000_000_000_000n,
        }),
      ).toEqual({ allowed: true });
    });

    it("refuses a suspended organization", async () => {
      const { workspaceId } = await customer(undefined, "suspended");

      expect(
        await service().checkBalance({
          workspace_id: workspaceId,
          estimated_amount_nano_usd: 0n,
        }),
      ).toEqual({ allowed: false, reason: "suspended" });
    });

    it("refuses an archived workspace", async () => {
      const { organizationId } = await customer();
      const workspaceId = await seedWorkspace(testDatabase.database, {
        organizationId,
      });
      await testDatabase.database
        .update(workspaces)
        .set({ archivedAt: new Date() })
        .where(eq(workspaces.id, workspaceId));

      expect(
        await service().checkBalance({
          workspace_id: workspaceId,
          estimated_amount_nano_usd: 0n,
        }),
      ).toEqual({ allowed: false, reason: "suspended" });
    });

    it("reports an unknown workspace as not found", async () => {
      await expect(
        service().checkBalance({
          workspace_id: randomUUID(),
          estimated_amount_nano_usd: 0n,
        }),
      ).rejects.toMatchObject({ code: "not_found" });
    });
  });
});
