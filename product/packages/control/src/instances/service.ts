import { eq, sql, getTableColumns } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";
import { z } from "zod";

import type { ControlDatabase } from "../db/client.js";
import { instances } from "../db/schema/instances.js";

export { privateServingUrl } from "./endpoints.js";

const identity = z.string().trim().min(1).max(200);

export const instanceRegistrationSchema = z.strictObject({
  provider: z.string().regex(/^[a-z][a-z0-9_-]{0,99}$/),
  providerAccountId: identity,
  providerInstanceId: identity,
  region: identity.nullable(),
  faultDomain: identity.nullable(),
  sku: identity,
});

export type InstanceRegistration = z.infer<typeof instanceRegistrationSchema>;

export type InstanceRecord = typeof instances.$inferSelect;
const inventoryColumns = getTableColumns(instances);

const instanceRecordSchema = instanceRegistrationSchema.extend({
  id: z.uuid(),
  createdAt: z.date(),
  updatedAt: z.date(),
  retiredAt: z.date().nullable(),
});

export interface InstanceService {
  register(value: InstanceRegistration): Promise<InstanceRecord>;
  retire(instanceId: string): Promise<InstanceRecord>;
}

export const createInstanceService = (
  database: ControlDatabase,
): InstanceService => ({
  async register(value) {
    const input = instanceRegistrationSchema.parse(value);
    const id = uuidv7();

    const [record] = await database
      .insert(instances)
      .values({ id, ...input })
      .onConflictDoUpdate({
        target: [
          instances.provider,
          instances.providerAccountId,
          instances.providerInstanceId,
        ],
        set: {
          region: input.region,
          faultDomain: input.faultDomain,
          sku: input.sku,
          retiredAt: null,
          updatedAt: sql`now()`,
        },
      })
      .returning(inventoryColumns);

    return instanceRecordSchema.parse(record);
  },

  async retire(instanceId) {
    const [record] = await database
      .update(instances)
      .set({
        retiredAt: sql`coalesce(${instances.retiredAt}, now())`,
        updatedAt: sql`now()`,
      })
      .where(eq(instances.id, z.uuid().parse(instanceId)))
      .returning(inventoryColumns);
    if (!record) throw new Error("Instance not found");

    return instanceRecordSchema.parse(record);
  },
});
