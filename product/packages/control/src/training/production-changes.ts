import { v7 as uuidv7 } from "uuid";
import { z } from "zod";
import { ProductionChangeSchema, UuidSchema } from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { taskProductionChanges } from "../db/schema/index.js";

type Transaction = Parameters<Parameters<ControlDatabase["transaction"]>[0]>[0];

export const ProductionChangeRecordSchema = z.object({
  id: UuidSchema,
  taskId: UuidSchema,
  fromVersionId: UuidSchema.nullable(),
  toVersionId: UuidSchema.nullable(),
  actor: ProductionChangeSchema.shape.actor.regex(
    /^(user|key|service):[A-Za-z0-9_-]{1,64}$/,
  ),
  createdAt: z.date(),
});
export type ProductionChangeRecord = z.infer<
  typeof ProductionChangeRecordSchema
>;

export const userActor = (userId: string) => `user:${userId}`;

export const recordProductionChange = async (
  tx: Transaction,
  change: {
    taskId: string;
    fromVersionId: string | null;
    toVersionId: string;
    actor: string;
  },
) => {
  await tx.insert(taskProductionChanges).values(
    ProductionChangeRecordSchema.omit({ createdAt: true }).parse({
      id: uuidv7(),
      ...change,
    }),
  );
};
