import type { ClickHouseClient } from "@clickhouse/client";
import {
  GenerationPropertiesSchema,
  GenerationSettledSchema,
  type GenerationSettled,
} from "@gradiated/contracts";
import { z } from "zod";

export const storedGenerationPropertiesSchema =
  GenerationPropertiesSchema.extend({
    settlement: z.strictObject({
      slot_id: z.string().regex(/^\d{8}T\d{6}Z-300s-v1$/),
    }),
  }).superRefine((properties, context) => {
    let calculatedCharge = 0n;
    for (const [index, component] of properties.pricing.components.entries()) {
      const calculatedAmount =
        BigInt(component.quantity) * BigInt(component.unit_price);
      if (BigInt(component.amount) !== calculatedAmount) {
        context.addIssue({
          code: "custom",
          message: "amount must equal quantity multiplied by unit_price",
          path: ["pricing", "components", index, "amount"],
        });
      }
      calculatedCharge += BigInt(component.amount);
    }
    if (BigInt(properties.usage.charge) !== calculatedCharge) {
      context.addIssue({
        code: "custom",
        message: "charge must equal the sum of pricing component amounts",
        path: ["usage", "charge"],
      });
    }
  });

export const clickHouseGenerationInsertSchema = z.strictObject({
  id: z.uuid(),
  properties: storedGenerationPropertiesSchema,
});

export type StoredGenerationProperties = z.infer<
  typeof storedGenerationPropertiesSchema
>;

export type ClickHouseGenerationInsert = z.infer<
  typeof clickHouseGenerationInsertSchema
>;

/*
 * This interface uses the transport event because the worker derives the
 * settlement slot from the Valkey Stream ID.
 */
export type GenerationWriter = {
  insertGeneration(
    event: GenerationSettled,
    settlementSlotId: string,
  ): Promise<void>;
};

export const createGenerationWriter = (
  client: ClickHouseClient,
): GenerationWriter => ({
  async insertGeneration(event, settlementSlotId) {
    const validatedEvent = GenerationSettledSchema.parse(event);
    const row = clickHouseGenerationInsertSchema.parse({
      id: validatedEvent.generation_id,
      properties: {
        ...validatedEvent.properties,
        settlement: { slot_id: settlementSlotId },
      },
    });
    const result = await client.insert({
      table: "generations",
      columns: ["id", "properties"],
      values: [row],
      format: "JSONEachRow",
      clickhouse_settings: {
        async_insert: 1,
        async_insert_deduplicate: 1,
        insert_deduplication_token: validatedEvent.generation_id,
        wait_for_async_insert: 1,
      },
    });

    if (!result.executed) {
      throw new Error(
        `ClickHouse did not execute insert ${validatedEvent.generation_id}`,
      );
    }
  },
});
