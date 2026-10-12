import { and, eq, isNotNull, isNull, sql, getTableColumns } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";
import { z } from "zod";

import { NOMAD_RECONCILE_LOCK } from "../deployments/nomad.js";
import type { ControlDatabase } from "../db/client.js";
import { instances } from "../db/schema/instances.js";
import { modelDeployments } from "../db/schema/organizations.js";

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

export const privateServingUrl = (instanceId: string): string =>
  `http://gpu-${z.uuid().parse(instanceId).toLowerCase()}.tailscale-inference.svc.cluster.local:8888`;

const instanceRecordSchema = instanceRegistrationSchema
  .extend({
    id: z.uuid(),
    nomadNodeId: z.uuid().nullable(),
    servingUrl: z.string().nullable(),
    createdAt: z.date(),
    updatedAt: z.date(),
    retiredAt: z.date().nullable(),
  })
  .refine(
    (record) =>
      record.servingUrl === null ||
      record.servingUrl === privateServingUrl(record.id),
    { message: "Invalid private serving endpoint" },
  );

export interface InstanceService {
  register(value: InstanceRegistration): Promise<InstanceRecord>;
  bindNomadNode(
    instanceId: string,
    nomadNodeId: string,
  ): Promise<InstanceRecord>;
  retire(instanceId: string): Promise<InstanceRecord>;
  setServingUrl(
    instanceId: string,
    servingUrl: string | null,
    expected?: {
      nomadNodeId: string;
      servingUrl: string | null;
      allocationIds: string[];
    },
  ): Promise<InstanceRecord>;
  servingState(
    instanceId: string,
  ): Promise<{ host: InstanceRecord; allocationIds: string[] }>;
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

    return instanceRecordSchema.parse(record);
  },

  async setServingUrl(instanceId, servingUrl, expected) {
    const id = z.uuid().parse(instanceId);
    const url = z.literal(privateServingUrl(id)).nullable().parse(servingUrl);

    return database.transaction(async (tx) => {
      if (expected)
        await tx.execute(
          sql`select pg_advisory_xact_lock(hashtext(${NOMAD_RECONCILE_LOCK}))`,
        );

      const allocationIds = expected
        ? z.array(z.uuid()).parse(expected.allocationIds).sort()
        : undefined;
      const [record] = await tx
        .update(instances)
        .set({ servingUrl: url, updatedAt: sql`now()` })
        .where(
          and(
            eq(instances.id, id),
            isNull(instances.retiredAt),
            isNotNull(instances.nomadNodeId),
            allocationIds
              ? sql`array(select ${modelDeployments.id} from ${modelDeployments}
            where ${modelDeployments.instanceId} = ${id} and ${modelDeployments.status} = 'available'
            order by ${modelDeployments.id}) = ${`{${allocationIds.join(",")}}`}::uuid[]`
              : undefined,
            expected
              ? eq(instances.nomadNodeId, z.uuid().parse(expected.nomadNodeId))
              : undefined,
            expected
              ? expected.servingUrl === null
                ? isNull(instances.servingUrl)
                : eq(
                    instances.servingUrl,
                    z.literal(privateServingUrl(id)).parse(expected.servingUrl),
                  )
              : undefined,
          ),
        )
        .returning(inventoryColumns);

      if (!record) throw new Error("Active bound instance not found");

      return instanceRecordSchema.parse(record);
    });
  },

  async servingState(instanceId) {
    const id = z.uuid().parse(instanceId);
    const [row] = await database
      .select(inventoryColumns)
      .from(instances)
      .where(
        and(
          eq(instances.id, id),
          isNull(instances.retiredAt),
          isNotNull(instances.nomadNodeId),
        ),
      );
    if (!row) throw new Error("Active bound instance not found");

    const rows = await database
      .select({ id: modelDeployments.id })
      .from(modelDeployments)
      .where(
        and(
          eq(modelDeployments.instanceId, id),
          eq(modelDeployments.status, "available"),
        ),
      );

    return {
      host: instanceRecordSchema.parse(row),
      allocationIds: z.array(z.uuid()).parse(rows.map((row) => row.id)),
    };
  },

  async bindNomadNode(instanceId, nomadNodeId) {
    const [record] = await database
      .update(instances)
      .set({ nomadNodeId: z.uuid().parse(nomadNodeId), updatedAt: sql`now()` })
      .where(eq(instances.id, z.uuid().parse(instanceId)))
      .returning(inventoryColumns);
    if (!record) throw new Error("Instance not found");

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
