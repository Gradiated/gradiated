import { z } from "zod";

import { clickHouseUInt64Schema } from "../clickhouse/client.js";
import { settlementSlotIdSchema } from "./slot.js";

type JsonRowsClient = {
  query(params: {
    query: string;
    query_params: Record<string, unknown>;
    format: "JSONEachRow";
  }): Promise<{ json(): Promise<unknown> }>;
};

const unsignedIntegerSchema = clickHouseUInt64Schema.transform((value) =>
  BigInt(value),
);

const settlementRowSchema = z.strictObject({
  settlement_slot_id: settlementSlotIdSchema,
  organization_id: z.uuid(),
  total_charge: unsignedIntegerSchema,
  generation_count: unsignedIntegerSchema,
  max_financial_variants: z.coerce.number().int().positive(),
});

const earliestSlotRowSchema = z.strictObject({
  slot_id: settlementSlotIdSchema.nullable(),
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
  client: JsonRowsClient,
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
          slot_id AS settlement_slot_id,
          organization_id,
          sum(charge) AS total_charge,
          countIf(charge > 0) AS generation_count,
          max(financial_variants) AS max_financial_variants
        FROM
        (
          SELECT
            id,
            any(g.settlement_slot_id) AS slot_id,
            any(g.organization_id) AS organization_id,
            any(g.charge) AS charge,
            uniqExact(tuple(g.settlement_slot_id, g.organization_id, g.charge)) AS financial_variants
          FROM generations AS g
          WHERE g.settlement_slot_id = {slot_id:String}
          GROUP BY id
        )
        GROUP BY slot_id, organization_id
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
