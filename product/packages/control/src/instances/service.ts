import { eq } from "drizzle-orm";
import { z } from "zod";
import type { ControlDatabase } from "../db/client.js";
import { instances } from "../db/schema/instances.js";

const identity = z.string().trim().min(1).max(200);
export const instanceInventorySchema = z.strictObject({
  id: z.uuid(),
  provider: z.string().regex(/^[a-z][a-z0-9_-]{0,99}$/),
  providerAccountId: identity,
  providerInstanceId: identity,
  region: identity.nullable(),
  faultDomain: identity.nullable(),
  sku: identity,
});

// Internal inventory operations. Authentication and credential revocation are separate.
export const createInstanceService = (database: ControlDatabase) => ({
  register: async (value: unknown) => {
    const input = instanceInventorySchema.parse(value);
    const [record] = await database.insert(instances).values(input).returning();
    return record!;
  },
  setNomadNode: async (instanceId: string, nomadNodeId: string | null) => {
    const id = z.uuid().parse(instanceId);
    const nodeId = z.uuid().nullable().parse(nomadNodeId);
    const [record] = await database
      .update(instances)
      .set({ nomadNodeId: nodeId, updatedAt: new Date() })
      .where(eq(instances.id, id))
      .returning();
    if (!record) throw new Error("Instance not found");
    return record;
  },
});
