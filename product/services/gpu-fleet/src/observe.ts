import { readFile } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";

import { hostEndpoint } from "./hosts.js";

export type Observation =
  | { reachable: true; instanceId: string; hostBundleSha256: string }
  | { reachable: false; error: string };

const pingSchema = z.object({
  instance_id: z.string(),
  host_bundle_sha256: z.string().default(""),
});

// Ping takes no fencing epoch, so it never competes with the controller.
export const pingHost = async (
  instanceId: string,
  keys: string,
  endpoint: (instanceId: string) => string = hostEndpoint,
): Promise<Observation> => {
  let key: string;
  try {
    key = (await readFile(path.join(keys, instanceId), "utf8")).trim();
  } catch {
    return {
      reachable: false,
      error: "The host management key is not mounted",
    };
  }
  try {
    const response = await fetch(endpoint(instanceId), {
      method: "POST",
      headers: {
        authorization: `Bearer ${key}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ operation: "ping" }),
      redirect: "error",
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok)
      return {
        reachable: false,
        error: `The host agent answered ping with ${response.status}`,
      };
    const ping = pingSchema.parse(await response.json());
    return {
      reachable: true,
      instanceId: ping.instance_id,
      hostBundleSha256: ping.host_bundle_sha256,
    };
  } catch (error) {
    return {
      reachable: false,
      error:
        error instanceof Error && error.name === "TimeoutError"
          ? "The host agent did not answer ping within 10 seconds"
          : "The host agent is unreachable",
    };
  }
};
