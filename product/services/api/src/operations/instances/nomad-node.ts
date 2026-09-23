import { readFile } from "node:fs/promises";
import { request } from "node:https";

import { z } from "@hono/zod-openapi";

import { requiredEnv } from "../catalog-operation.js";

const REQUEST_TIMEOUT_MS = 30_000;

const nodeSchema = z.object({
  ID: z.string(),
  Name: z.string(),
  Status: z.string(),
  Meta: z.record(z.string(), z.string()).nullish(),
});

export type NomadNode = z.infer<typeof nodeSchema>;

export type ReadNomadNode = (nodeId: string) => Promise<NomadNode | null>;

export const nomadNodeReaderFromEnvironment =
  async (): Promise<ReadNomadNode> => {
    const address = new URL(requiredEnv("NOMAD_ADDR"));
    const token = requiredEnv("NOMAD_TOKEN");
    const [ca, cert, key] = await Promise.all(
      ["NOMAD_CACERT", "NOMAD_CLIENT_CERT", "NOMAD_CLIENT_KEY"].map((name) =>
        readFile(requiredEnv(name), "utf8"),
      ),
    );
    // Nomad servers present server.<region>.nomad, not the forwarded address.
    const servername =
      process.env.NOMAD_TLS_SERVER_NAME ?? "server.global.nomad";

    return (nodeId) =>
      new Promise((resolve, reject) => {
        const outgoing = request(
          new URL(`/v1/node/${encodeURIComponent(nodeId)}`, address),
          {
            ca,
            cert,
            key,
            servername,
            headers: { "x-nomad-token": token },
            signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
          },
          (response) => {
            let body = "";
            response.setEncoding("utf8");
            response.on("data", (chunk: string) => (body += chunk));
            response.on("end", () => {
              if (response.statusCode === 404) return resolve(null);
              if (response.statusCode !== 200) {
                return reject(
                  new Error(
                    `Nomad node read failed: ${response.statusCode} ${body}`,
                  ),
                );
              }
              try {
                resolve(nodeSchema.parse(JSON.parse(body)));
              } catch (error) {
                reject(error);
              }
            });
          },
        );
        outgoing.on("error", reject);
        outgoing.end();
      });
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
    await sleep(intervalMs);
  }

  throw new Error(
    `Nomad node ${nomadNodeId} was not ready after ${timeoutMs / 1000}s (last status: ${last?.Status ?? "not registered"})`,
  );
};
