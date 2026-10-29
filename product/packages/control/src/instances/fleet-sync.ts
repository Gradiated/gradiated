import { eq, inArray, sql } from "drizzle-orm";
import { z } from "zod";

import type { ControlDatabase } from "../db/client.js";
import { instances } from "../db/schema/instances.js";

// A row this young may belong to a host registered before its GpuHost was
// merged, so the sweep leaves it; retiring withdraws its deployments.
export const RETIRE_GRACE_MS = 24 * 60 * 60_000;

export const fleetHostSchema = z.strictObject({
  instanceId: z.uuid(),
  provider: z.string().regex(/^[a-z][a-z0-9_-]{0,99}$/),
  accountId: z.string().min(1).max(200),
  podId: z.string().min(1).max(200),
  sku: z.string().min(1).max(200),
  faultDomain: z.string().min(1).max(200).optional(),
});

export type FleetHost = z.infer<typeof fleetHostSchema>;

const rowSchema = z.object({
  id: z.uuid(),
  provider: z.string(),
  accountId: z.string(),
  podId: z.string(),
  faultDomain: z.string().nullable(),
  createdAt: z.date(),
  retiredAt: z.date().nullable(),
});

export type FleetSyncResult = {
  inserted: string[];
  restored: string[];
  retired: string[];
  updated: string[];
  conflicts: { instanceId: string; reason: string }[];
};

const identity = (host: {
  provider: string;
  accountId: string;
  podId: string;
}) => `${host.provider}/${host.accountId}/${host.podId}`;

// Rows are never deleted, and a row that disagrees with the fleet's identity is
// reported as a conflict rather than overwritten. Only rows of the fleet's
// provider accounts are retired.
export type FleetSyncOptions = {
  now?: Date;
  // Provider accounts the fleet manages, as provider/accountId. Their rows are
  // retired even after an account's last host is removed; the accounts of the
  // listed hosts are always included.
  accounts?: readonly string[];
  // Called just before commit; throwing rolls the transaction back, so a caller
  // that lost leadership mid-sync writes nothing.
  beforeCommit?: () => void;
};

export const syncFleetInstances = async (
  database: ControlDatabase,
  fleet: readonly FleetHost[],
  {
    now = new Date(),
    accounts: managed = [],
    beforeCommit,
  }: FleetSyncOptions = {},
): Promise<FleetSyncResult> => {
  const hosts = fleet.map((host) => fleetHostSchema.parse(host));
  const result: FleetSyncResult = {
    inserted: [],
    restored: [],
    retired: [],
    updated: [],
    conflicts: [],
  };
  const conflict = (instanceId: string, reason: string) =>
    result.conflicts.push({ instanceId, reason });

  const counts = new Map<string, number>();
  for (const host of hosts)
    for (const key of [host.instanceId, identity(host)])
      counts.set(key, (counts.get(key) ?? 0) + 1);
  const unique = hosts.filter((host) => {
    if (counts.get(host.instanceId)! > 1)
      conflict(host.instanceId, "Several GpuHosts use this instance ID");
    else if (counts.get(identity(host))! > 1)
      conflict(host.instanceId, `Several GpuHosts use pod ${host.podId}`);
    else return true;
    return false;
  });

  await database.transaction(async (transaction) => {
    await transaction.execute(sql`SET LOCAL statement_timeout = '5s'`);
    const rows = rowSchema.array().parse(
      await transaction
        .select({
          id: instances.id,
          provider: instances.provider,
          accountId: instances.providerAccountId,
          podId: instances.providerInstanceId,
          faultDomain: instances.faultDomain,
          createdAt: instances.createdAt,
          retiredAt: instances.retiredAt,
        })
        .from(instances),
    );
    const byId = new Map(rows.map((row) => [row.id, row]));
    const byIdentity = new Map(rows.map((row) => [identity(row), row]));

    const restore: string[] = [];
    for (const host of unique) {
      const row = byId.get(host.instanceId);
      if (row) {
        if (identity(row) !== identity(host)) {
          conflict(
            host.instanceId,
            `PostgreSQL records this instance as ${row.provider} pod ${row.podId}`,
          );
          continue;
        }
        if (row.retiredAt) restore.push(host.instanceId);
        // A host without a machine keeps the fault domain registration wrote;
        // the GpuHost schema forbids removing a machine once it is set.
        if (host.faultDomain && host.faultDomain !== row.faultDomain) {
          await transaction
            .update(instances)
            .set({ faultDomain: host.faultDomain, updatedAt: sql`now()` })
            .where(eq(instances.id, host.instanceId));
          result.updated.push(host.instanceId);
        }
        continue;
      }
      const holder = byIdentity.get(identity(host));
      if (holder) {
        conflict(
          host.instanceId,
          `PostgreSQL records pod ${host.podId} as instance ${holder.id}`,
        );
        continue;
      }
      await transaction.insert(instances).values({
        id: host.instanceId,
        provider: host.provider,
        providerAccountId: host.accountId,
        providerInstanceId: host.podId,
        region: null,
        faultDomain: host.faultDomain ?? null,
        sku: host.sku,
      });
      result.inserted.push(host.instanceId);
    }

    if (restore.length) {
      await transaction
        .update(instances)
        .set({ retiredAt: null, updatedAt: sql`now()` })
        .where(inArray(instances.id, restore));
      result.restored.push(...restore);
    }

    const inFleet = new Set(hosts.map((host) => host.instanceId));
    const accounts = new Set([
      ...managed,
      ...hosts.map((host) => `${host.provider}/${host.accountId}`),
    ]);
    const retire = rows
      .filter(
        (row) =>
          !row.retiredAt &&
          !inFleet.has(row.id) &&
          accounts.has(`${row.provider}/${row.accountId}`) &&
          now.getTime() - row.createdAt.getTime() >= RETIRE_GRACE_MS,
      )
      .map((row) => row.id);
    if (retire.length) {
      await transaction
        .update(instances)
        .set({ retiredAt: sql`now()`, updatedAt: sql`now()` })
        .where(inArray(instances.id, retire));
      result.retired.push(...retire);
    }

    beforeCommit?.();
  });

  return result;
};
