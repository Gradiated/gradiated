import { servedReleaseDigest, type ModelReplica } from "@gradiated/control";
import { z } from "zod";

const FRESH_MS = 15_000;

const statusSchema = z.object({
  healthy: z.boolean(),
  runtime_revision: z.string(),
  received_at: z.iso.datetime(),
});

export type ReplicaCounts = Record<string, { replicas: number; ready: number }>;

export const countReadyReplicas = async (
  replicas: readonly ModelReplica[],
  statusesFor: (digest: string) => Promise<Record<string, string>>,
  now = Date.now(),
): Promise<ReplicaCounts> => {
  const byDigest = new Map<string, Record<string, string>>();
  const counts: ReplicaCounts = {};

  for (const replica of replicas) {
    const digest = servedReleaseDigest(replica.release);
    if (!byDigest.has(digest)) byDigest.set(digest, await statusesFor(digest));
    const model = (counts[replica.modelId] ??= { replicas: 0, ready: 0 });
    model.replicas += 1;

    const status = parseStatus(byDigest.get(digest)?.[replica.id]);
    if (
      status?.healthy &&
      status.runtime_revision === replica.release.runtime_revision &&
      now - Date.parse(status.received_at) <= FRESH_MS
    ) {
      model.ready += 1;
    }
  }

  return counts;
};

const parseStatus = (value: string | undefined) => {
  try {
    return statusSchema.safeParse(JSON.parse(value ?? "")).data;
  } catch {
    return undefined;
  }
};
