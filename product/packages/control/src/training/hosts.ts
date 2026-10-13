import { z } from "zod";
import { and, eq, inArray, isNull } from "drizzle-orm";
import type { ControlDatabase } from "../db/client.js";
import { instances } from "../db/schema/index.js";

export const trainingNodes = async (
  database: ControlDatabase,
  podIds: string[],
) => {
  if (!podIds.length || podIds.length > 4)
    throw new Error("Training requires one to four registered hosts.");
  const rows = await database
    .select({
      nodeId: instances.id,
      url: instances.servingUrl,
      podId: instances.providerInstanceId,
    })
    .from(instances)
    .where(
      and(
        eq(instances.provider, "runpod"),
        inArray(instances.providerInstanceId, podIds),
        isNull(instances.retiredAt),
      ),
    );
  if (rows.length !== podIds.length || rows.some((row) => !row.url))
    throw new Error("Training hosts require private Kubernetes enrollment.");
  return z
    .array(
      z.object({
        nodeId: z.uuid(),
        url: z.string().url(),
        podId: z.string().min(1),
      }),
    )
    .parse(rows);
};
