import { createClient } from "redis";

import { eventually } from "../eventually.js";
import { portAvailable } from "../ports.js";
import type { LocalDocker } from "./docker.js";

const IMAGE = "valkey/valkey:8.1.9-alpine3.24";

/**
 * A cluster node also needs its bus port, which is always the data port plus 10,000.
 * The ephemeral range sits above that ceiling on some hosts, so pick explicitly.
 */
const clusterPort = async (): Promise<number> => {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    const port = 20_000 + Math.floor(Math.random() * 25_000);
    if ((await portAvailable(port)) && (await portAvailable(port + 10_000))) {
      return port;
    }
  }

  throw new Error("could not find a free cluster port pair");
};

/** An empty one-node cluster that holds every slot, on a random port. */
export const startValkey = async (docker: LocalDocker): Promise<string> => {
  const port = await clusterPort();
  const container = await docker.run("valkey", [
    "--network",
    "host",
    "--tmpfs",
    "/data:rw,nosuid,nodev,size=64m",
    IMAGE,
    "valkey-server",
    "--bind",
    "127.0.0.1",
    "--port",
    String(port),
    "--save",
    "",
    "--appendonly",
    "no",
    "--cluster-enabled",
    "yes",
    "--cluster-config-file",
    "/data/nodes.conf",
    "--cluster-announce-ip",
    "127.0.0.1",
    "--cluster-announce-port",
    String(port),
    "--cluster-announce-bus-port",
    String(port + 10_000),
  ]);

  const url = `redis://127.0.0.1:${port}`;
  const client = createClient({ url, socket: { reconnectStrategy: false } });

  try {
    await eventually(
      async () => {
        if (!client.isOpen) await client.connect();
        return (await client.ping()) === "PONG";
      },
      10_000,
      "valkey did not accept connections",
    );

    const info = await docker.command(
      "exec",
      container,
      "valkey-cli",
      "-p",
      String(port),
      "INFO",
      "server",
    );
    const runId = /run_id:(\S+)/.exec(await client.info("server"))?.[1];
    if (!runId || !info.includes(`run_id:${runId}`)) {
      throw new Error(
        "connected to a Valkey server other than this run's container",
      );
    }
    if ((await client.dbSize()) !== 0) {
      throw new Error("disposable serving state is not empty");
    }

    await client.sendCommand(["CLUSTER", "ADDSLOTSRANGE", "0", "16383"]);
    await eventually(
      async () =>
        String(await client.sendCommand(["CLUSTER", "INFO"])).includes(
          "cluster_state:ok",
        ),
      10_000,
      "cluster did not reach a serving state",
    );
  } finally {
    if (client.isOpen) await client.close();
  }

  return url;
};
