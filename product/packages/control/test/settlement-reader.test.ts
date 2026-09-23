import { describe, expect, it, vi } from "vitest";
import { ZodError } from "zod";

import {
  createGenerationSettlementReader,
  SettlementFinancialConflictError,
} from "../src/settlement/clickhouse-reader.js";
import { slotId } from "./support/settlement.js";

const organizationId = "0198ad73-a200-7000-8000-000000000002";

const clientReturning = (rows: unknown[]) => ({
  query: vi.fn(async (_params: unknown) => ({ json: async () => rows })),
});

const settlementRow = (overrides: Record<string, unknown> = {}) => ({
  settlement_slot_id: slotId,
  organization_id: organizationId,
  total_charge: "9007199254740993",
  generation_count: 2,
  max_financial_variants: 1,
  ...overrides,
});

describe("ClickHouse settlement reader", () => {
  it("parses organization totals as exact bigint values", async () => {
    const client = clientReturning([settlementRow()]);

    const settlements =
      await createGenerationSettlementReader(client).getOrganizationSettlements(
        slotId,
      );

    expect(settlements).toEqual([
      {
        generationCount: 2n,
        organizationId,
        slotId,
        totalCharge: 9_007_199_254_740_993n,
      },
    ]);
    expect(client.query).toHaveBeenCalledWith(
      expect.objectContaining({
        query_params: { slot_id: slotId },
        format: "JSONEachRow",
      }),
    );
  });

  it("refuses a slot whose generations disagree on financial values", async () => {
    const reader = createGenerationSettlementReader(
      clientReturning([settlementRow({ max_financial_variants: 2 })]),
    );

    await expect(
      reader.getOrganizationSettlements(slotId),
    ).rejects.toBeInstanceOf(SettlementFinancialConflictError);
  });

  it("rejects a malformed slot id", async () => {
    const reader = createGenerationSettlementReader(
      clientReturning([settlementRow({ settlement_slot_id: "20260815" })]),
    );

    await expect(
      reader.getOrganizationSettlements(slotId),
    ).rejects.toBeInstanceOf(ZodError);
  });

  it("returns the earliest slot up to the upper bound", async () => {
    const client = clientReturning([{ slot_id: slotId }]);

    expect(
      await createGenerationSettlementReader(client).getEarliestSlot(slotId),
    ).toBe(slotId);
    expect(client.query).toHaveBeenCalledWith(
      expect.objectContaining({ query_params: { upper_slot_id: slotId } }),
    );
  });

  it("returns no earliest slot when ClickHouse has none", async () => {
    const reader = createGenerationSettlementReader(
      clientReturning([{ slot_id: null }]),
    );

    expect(await reader.getEarliestSlot(slotId)).toBeNull();
  });

  it("rejects a malformed earliest slot id", async () => {
    const reader = createGenerationSettlementReader(
      clientReturning([{ slot_id: "not-a-slot" }]),
    );

    await expect(reader.getEarliestSlot(slotId)).rejects.toBeInstanceOf(
      ZodError,
    );
  });
});
