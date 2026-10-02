import { eq, sql, getTableColumns } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";
import { z } from "zod";

import type { ControlDatabase } from "../db/client.js";
import { instances } from "../db/schema/instances.js";

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

export type InstanceRecord = Omit<typeof instances.$inferSelect, "certificate">;
const { certificate: _certificate, ...inventoryColumns } =
  getTableColumns(instances);

export interface InstanceService {
  register(value: InstanceRegistration): Promise<InstanceRecord>;
  bindNomadNode(
    instanceId: string,
    nomadNodeId: string,
  ): Promise<InstanceRecord>;
  retire(instanceId: string): Promise<InstanceRecord>;
}

export const createInstanceService = (
  database: ControlDatabase,
): InstanceService => ({
  async register(value) {
    const input = instanceRegistrationSchema.parse(value);

    const [record] = await database
      .insert(instances)
      .values({ id: uuidv7(), ...input })
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

    return record!;
  },

  async bindNomadNode(instanceId, nomadNodeId) {
    const [record] = await database
      .update(instances)
      .set({ nomadNodeId: z.uuid().parse(nomadNodeId), updatedAt: sql`now()` })
      .where(eq(instances.id, z.uuid().parse(instanceId)))
      .returning(inventoryColumns);
    if (!record) throw new Error("Instance not found");

    return record;
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

    return record;
  },
});
