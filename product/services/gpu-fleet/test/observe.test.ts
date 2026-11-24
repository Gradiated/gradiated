import { writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { pingHost } from "../src/observe.js";
import { FIRST, fakeHostAgents } from "./support/fleet.js";

// A loopback port nothing listens on.
const closedPort = async () => {
  const server = createServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as { port: number };
  await new Promise<void>((resolve) => server.close(() => resolve()));
  return port;
};

describe("host observation", () => {
  let agents: Awaited<ReturnType<typeof fakeHostAgents>>;
  afterEach(() => agents?.close());

  it("reads the host's identity and bundle with the read-only ping", async () => {
    agents = await fakeHostAgents();
    await agents.addKey(FIRST);
    agents.version.set(FIRST, {
      host_bundle_trial: true,
      previous_host_bundle_sha256: "a".repeat(64),
    });
    expect(await pingHost(FIRST, agents.keys, agents.endpoint)).toEqual({
      reachable: true,
      instanceId: FIRST,
      hostBundleSha256: "b".repeat(64),
      previousHostBundleSha256: "a".repeat(64),
      failedHostBundleSha256: "",
      stagingFailedHostBundleSha256: "",
      trial: true,
    });
    // Only ping, with no fencing epoch or term the controller owns.
    expect(agents.requests).toEqual([
      { instanceId: FIRST, body: { operation: "ping" } },
    ]);
  });

  it("tells a silent host from one the operator cannot authenticate to", async () => {
    agents = await fakeHostAgents();
    expect(await pingHost(FIRST, agents.keys, agents.endpoint)).toEqual({
      reachable: false,
      error: "The host management key is not mounted",
      silent: false,
      keyMissing: true,
    });

    await writeFile(path.join(agents.keys, FIRST), "stale-key\n");
    expect(await pingHost(FIRST, agents.keys, agents.endpoint)).toEqual({
      reachable: false,
      error: "The host agent answered ping with 403",
      silent: false,
    });

    await agents.addKey(FIRST);
    agents.down.add(FIRST);
    expect(await pingHost(FIRST, agents.keys, agents.endpoint, 200)).toEqual({
      reachable: false,
      error: "The host agent did not answer ping within 0.2 seconds",
      silent: true,
    });
  });

  it("does not take a broken egress Service for a silent host", async () => {
    agents = await fakeHostAgents();
    await agents.addKey(FIRST);
    const closed = await closedPort();

    for (const [endpoint, code] of [
      [() => "http://gpu-missing.invalid/_kubelet", /ENOTFOUND|EAI_AGAIN/],
      [() => `http://127.0.0.1:${closed}/_kubelet`, /ECONNREFUSED/],
    ] as const) {
      const observation = await pingHost(FIRST, agents.keys, endpoint, 5_000);
      expect(observation).toMatchObject({ reachable: false, silent: false });
      expect(observation.reachable || observation.error).toMatch(code);
    }
  });
});
