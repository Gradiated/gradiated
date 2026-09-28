import { z } from "zod";

import { UpstreamError, type Backend } from "../backend.js";

const nodeSchema = z.object({
  ID: z.string(),
  Name: z.string(),
  Status: z.string(),
  Meta: z.record(z.string(), z.string()).nullish(),
});

export type NomadNode = z.infer<typeof nodeSchema>;

export type ReadNomadNode = (nodeId: string) => Promise<NomadNode | null>;

export const nomadNodeReader =
  (backend: Backend): ReadNomadNode =>
  async (nodeId) => {
    try {
      const { data } = z
        .object({ data: z.unknown() })
        .parse(
          await backend("nomad", `/v1/node/${encodeURIComponent(nodeId)}`),
        );

      return nodeSchema.parse(data);
    } catch (error) {
      if (error instanceof UpstreamError && error.status === 404) return null;

      throw error;
    }
  };

export interface NodeWait {
  readonly nomadNodeId: string;
  readonly instanceId: string;
  readonly timeoutMs: number;
  readonly intervalMs?: number;
  readonly sleep?: (ms: number) => Promise<void>;
  readonly now?: () => number;
}

export const waitForNomadNode = async (
  read: ReadNomadNode,
  {
    nomadNodeId,
    instanceId,
    timeoutMs,
    intervalMs = 5_000,
    sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    now = Date.now,
  }: NodeWait,
): Promise<NomadNode> => {
  const deadline = now() + timeoutMs;
  let last: NomadNode | null = null;

  while (now() < deadline) {
    last = await read(nomadNodeId);
    if (last) {
      const holder = last.Meta?.gradiated_instance_id;
      if (holder !== instanceId) {
        throw new Error(
          `Nomad node ${nomadNodeId} belongs to instance ${holder ?? "none"}, not ${instanceId}`,
        );
      }
      if (last.Status === "ready") return last;
    }
    await sleep(Math.min(intervalMs, Math.max(0, deadline - now())));
  }

  throw new Error(
    `Nomad node ${nomadNodeId} was not ready after ${timeoutMs / 1000}s (last status: ${last?.Status ?? "not registered"})`,
  );
};
