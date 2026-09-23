import type { ClickHouseClient } from "@clickhouse/client";
import {
  GenerationPropertiesSchema,
  GenerationSettledSchema,
  type GenerationSettled,
} from "@gradiated/contracts";
import { z } from "zod";

import { settlementSlotIdSchema } from "../settlement/slot.js";
import { insertDeduplicated } from "./client.js";

const settlement = {
  settlement: z.strictObject({ slot_id: settlementSlotIdSchema }),
};
const [version1, version2] = GenerationPropertiesSchema.options;

export const storedGenerationPropertiesSchema = z
  .discriminatedUnion("event_schema_version", [
    version1.extend(settlement),
    version2.extend(settlement),
  ])
  .superRefine((properties, context) => {
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

const clickHouseGenerationInsertSchema = z.strictObject({
  id: z.uuid(),
  properties: storedGenerationPropertiesSchema,
});

export type StoredGenerationProperties = z.infer<
  typeof storedGenerationPropertiesSchema
>;

export type GenerationWriter = {
  insertGeneration(
    event: GenerationSettled,
    settlementSlotId: string,
  ): Promise<void>;
};

export const createGenerationWriter = (
  client: Pick<ClickHouseClient, "insert">,
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

    await insertDeduplicated(client, {
      table: "generations",
      values: [row],
      token: validatedEvent.generation_id,
    });
  },
});
