import { writeFile } from "node:fs/promises";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { pingHost } from "../src/observe.js";
import { FIRST, fakeHostAgents } from "./support/fleet.js";

describe("host observation", () => {
  let agents: Awaited<ReturnType<typeof fakeHostAgents>>;
  afterEach(() => agents?.close());

  it("reads the host's identity and bundle with the read-only ping", async () => {
    agents = await fakeHostAgents();
    await agents.addKey(FIRST);
    expect(await pingHost(FIRST, agents.keys, agents.endpoint)).toEqual({
      reachable: true,
      instanceId: FIRST,
      hostBundleSha256: "b".repeat(64),
    });
    // Only ping, with no fencing epoch or term the controller owns.
    expect(agents.requests).toEqual([
      { instanceId: FIRST, body: { operation: "ping" } },
    ]);
  });

  it("reports a host it cannot authenticate to, or reach, as unreachable", async () => {
    agents = await fakeHostAgents();
    expect(await pingHost(FIRST, agents.keys, agents.endpoint)).toEqual({
      reachable: false,
      error: "The host management key is not mounted",
    });

    await writeFile(path.join(agents.keys, FIRST), "stale-key\n");
    expect(await pingHost(FIRST, agents.keys, agents.endpoint)).toEqual({
      reachable: false,
      error: "The host agent answered ping with 403",
    });

    await agents.addKey(FIRST);
    agents.down.add(FIRST);
    expect(await pingHost(FIRST, agents.keys, agents.endpoint)).toEqual({
      reachable: false,
      error: "The host agent is unreachable",
    });
  });
});
