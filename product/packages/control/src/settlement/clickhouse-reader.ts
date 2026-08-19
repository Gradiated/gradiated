import type { ClickHouseClient } from "@clickhouse/client";
import { z } from "zod";

const settlementSlotIdPattern = /^\d{8}T\d{6}Z-300s-v1$/;
const unsignedIntegerSchema = z
  .union([z.string().regex(/^\d+$/), z.number().int().nonnegative()])
  .transform((value) => BigInt(value));

const settlementRowSchema = z.strictObject({
  settlement_slot_id: z.string().regex(settlementSlotIdPattern),
  organization_id: z.uuid(),
  total_charge: unsignedIntegerSchema,
  generation_count: unsignedIntegerSchema,
  max_financial_variants: z.coerce.number().int().positive(),
});

const earliestSlotRowSchema = z.strictObject({
  slot_id: z.string().regex(settlementSlotIdPattern).nullable(),
});

export type OrganizationSettlement = {
  generationCount: bigint;
  organizationId: string;
  slotId: string;
  totalCharge: bigint;
};

export type GenerationSettlementReader = {
  getEarliestSlot(upperSlotId: string): Promise<string | null>;
  getOrganizationSettlements(slotId: string): Promise<OrganizationSettlement[]>;
};

export class SettlementFinancialConflictError extends Error {
  constructor(slotId: string) {
    super(`Generation financial values conflict in slot ${slotId}`);
    this.name = "SettlementFinancialConflictError";
  }
}

export const createGenerationSettlementReader = (
  client: ClickHouseClient,
): GenerationSettlementReader => ({
  async getEarliestSlot(upperSlotId) {
    const result = await client.query({
      query: `
        SELECT minOrNull(settlement_slot_id) AS slot_id
        FROM generations
        WHERE settlement_slot_id <= {upper_slot_id:String}
      `,
      query_params: { upper_slot_id: upperSlotId },
      format: "JSONEachRow",
    });
    const rows = earliestSlotRowSchema.array().parse(await result.json());
    return rows[0]?.slot_id ?? null;
  },

  async getOrganizationSettlements(slotId) {
    const result = await client.query({
      query: `
        SELECT
          settlement_slot_id,
          organization_id,
          sum(charge) AS total_charge,
          countIf(charge > 0) AS generation_count,
          max(financial_variants) AS max_financial_variants
        FROM
        (
          SELECT
            id,
            any(settlement_slot_id) AS settlement_slot_id,
            any(organization_id) AS organization_id,
            any(charge) AS charge,
            uniqExact(tuple(settlement_slot_id, organization_id, charge)) AS financial_variants
          FROM generations
          WHERE settlement_slot_id = {slot_id:String}
          GROUP BY id
        )
        GROUP BY settlement_slot_id, organization_id
      `,
      query_params: { slot_id: slotId },
      format: "JSONEachRow",
    });
    const rows = settlementRowSchema.array().parse(await result.json());
    if (rows.some((row) => row.max_financial_variants !== 1)) {
      throw new SettlementFinancialConflictError(slotId);
    }
    return rows.map((row) => ({
      generationCount: row.generation_count,
      organizationId: row.organization_id,
      slotId: row.settlement_slot_id,
      totalCharge: row.total_charge,
    }));
  },
});
