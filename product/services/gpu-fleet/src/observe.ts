import { readFile } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";

import { hostEndpoint } from "./hosts.js";

export type HostVersion = {
  hostBundleSha256: string;
  previousHostBundleSha256: string;
  failedHostBundleSha256: string;
  stagingFailedHostBundleSha256: string;
  trial: boolean;
};

export type Observation =
  | ({ reachable: true; instanceId: string } & HostVersion)
  // silent: the host itself did not answer in time. A missing key, an error
  // answer, or a failure to reach the egress Service (no DNS name, nothing
  // listening) is the operator's problem, and says nothing about whether the
  // host lives.
  | { reachable: false; error: string; silent: boolean; keyMissing?: true };

const pingSchema = z.object({
  instance_id: z.string(),
  host_bundle_sha256: z.string().default(""),
  previous_host_bundle_sha256: z.string().default(""),
  host_bundle_failed_sha256: z.string().default(""),
  host_bundle_staging_failed_sha256: z.string().default(""),
  host_bundle_trial: z.boolean().default(false),
});

// Ping takes no fencing epoch, so it never competes with the controller.
export const pingHost = async (
  instanceId: string,
  keys: string,
  endpoint: (instanceId: string) => string = hostEndpoint,
  timeout = 10_000,
): Promise<Observation> => {
  let key: string;
  try {
    key = (await readFile(path.join(keys, instanceId), "utf8")).trim();
  } catch (error) {
    return {
      reachable: false,
      error: "The host management key is not mounted",
      silent: false,
      ...((error as NodeJS.ErrnoException).code === "ENOENT" && {
        keyMissing: true as const,
      }),
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
      signal: AbortSignal.timeout(timeout),
    });
    if (!response.ok)
      return {
        reachable: false,
        error: `The host agent answered ping with ${response.status}`,
        silent: false,
      };
    const parsed = pingSchema.safeParse(
      await response.json().catch(() => null),
    );
    if (!parsed.success)
      return {
        reachable: false,
        error: "The host agent answered ping with an unexpected body",
        silent: false,
      };
    const ping = parsed.data;
    return {
      reachable: true,
      instanceId: ping.instance_id,
      hostBundleSha256: ping.host_bundle_sha256,
      previousHostBundleSha256: ping.previous_host_bundle_sha256,
      failedHostBundleSha256: ping.host_bundle_failed_sha256,
      stagingFailedHostBundleSha256: ping.host_bundle_staging_failed_sha256,
      trial: ping.host_bundle_trial,
    };
  } catch (error) {
    // The egress proxy forwards to a host that is gone without answering, so
    // only a timeout means the host is silent.
    if (error instanceof Error && error.name === "TimeoutError")
      return {
        reachable: false,
        error: `The host agent did not answer ping within ${timeout / 1000} seconds`,
        silent: true,
      };
    const cause = (error as { cause?: { code?: string; message?: string } })
      .cause;
    return {
      reachable: false,
      error: `The host agent's egress Service could not be reached: ${cause?.code ?? cause?.message ?? (error as Error).message}`,
      silent: false,
    };
  }
};
