import {
  createGenerationSettlementReader,
  SettlementFinancialConflictError,
} from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";

const slotId = "20260815T123000Z-300s-v1";
const organizationId = "0198ad73-a200-7000-8000-000000000002";

const clientWithRows = (rows: unknown[]) =>
  ({
    query: vi.fn(async () => ({ json: async () => rows })),
  }) as never;

describe("ClickHouse generation settlement reader", () => {
  it("parses financial aggregates as bigint values", async () => {
    const reader = createGenerationSettlementReader(
      clientWithRows([
        {
          settlement_slot_id: slotId,
          organization_id: organizationId,
          total_charge: "42",
          generation_count: "2",
          max_financial_variants: 1,
        },
      ]),
    );

    await expect(reader.getOrganizationSettlements(slotId)).resolves.toEqual([
      {
        generationCount: 2n,
        organizationId,
        slotId,
        totalCharge: 42n,
      },
    ]);
  });

  it("blocks a slot with conflicting financial variants", async () => {
    const reader = createGenerationSettlementReader(
      clientWithRows([
        {
          settlement_slot_id: slotId,
          organization_id: organizationId,
          total_charge: "42",
          generation_count: "2",
          max_financial_variants: 2,
        },
      ]),
    );

    await expect(
      reader.getOrganizationSettlements(slotId),
    ).rejects.toBeInstanceOf(SettlementFinancialConflictError);
  });
});
