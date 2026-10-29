import { execFile } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { connect, createServer, type Server, type Socket } from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import type { TailnetStatus } from "@gradiated/gpu-hosts";

const exec = promisify(execFile);
const HERE = path.dirname(fileURLToPath(import.meta.url));

// Pinned like every other image the repository runs.
export const HEADSCALE_IMAGE =
  "headscale/headscale:0.29.5@sha256:780ed2f9e85719a2211277433f2c8afb45105d0d25031949a6848a485f9e216d";
// The operator's sidecar image (gpu-inference/gpu-fleet.yaml).
export const TAILSCALE_IMAGE =
  "tailscale/tailscale:unstable-v1.103.375@sha256:16d26aaa855305214759772349b99133dfeb6332abfd85746dfdb29ca027cfcf";
export const PYTHON_IMAGE =
  "python:3.12-alpine@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d";

export const DOMAIN = "tailnet.test";
export const BOOTSTRAP_TAG = "tag:gpu-bootstrap";
export const INFERENCE_TAG = "tag:gpu-inference";

export const docker = async (...args: string[]) =>
  (await exec("docker", args, { maxBuffer: 64 * 1024 * 1024 })).stdout.trim();

export const until = async (
  check: () => Promise<boolean>,
  what: string,
  seconds = 60,
) => {
  const deadline = Date.now() + seconds * 1000;
  for (;;) {
    if (await check().catch(() => false)) return;
    if (Date.now() > deadline) throw new Error(`Timed out waiting for ${what}`);
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
};

// What tests/e2e_image.py built: the GPU base image, its host bundle and TLS material.
export type Assets = {
  directory: string;
  image: string;
  hostBundle: { sha256: string; baseId: string };
};

export const assets = (): Assets | undefined => {
  const directory = process.env.GPU_FLEET_E2E;
  if (!directory) return undefined;
  const manifest = JSON.parse(
    readFileSync(path.join(directory, "manifest.json"), "utf8"),
  ) as Omit<Assets, "directory">;
  return { directory, ...manifest };
};

type Node = {
  id: number;
  name: string;
  given_name: string;
  ip_addresses: string[];
  tags: string[] | null;
  online: boolean;
  last_seen?: { seconds: number };
};

/**
 * A private tailnet run by headscale, the artifact store, and a Tailscale
 * sidecar like the one ops-mcp and the operator use: the test reaches GPU pods
 * through its SOCKS proxy and reads its LocalAPI status.
 */
export const startTailnet = async (files: Assets) => {
  const network = `gpu-fleet-e2e-${randomBytes(4).toString("hex")}`;
  const name = (role: string) => `${network}-${role}`;
  const containers: string[] = [];
  const run = async (role: string, ...args: string[]) => {
    containers.push(name(role));
    await docker(
      "run",
      "-d",
      "--name",
      name(role),
      "--network",
      network,
      ...args,
    );
  };
  const file = (relative: string) => path.join(files.directory, relative);
  // Removes every container on the network, including the test's pods.
  const stop = async () => {
    const attached = await docker(
      "ps",
      "-aq",
      "--filter",
      `network=${network}`,
    ).catch(() => "");
    await exec("docker", [
      "rm",
      "-f",
      ...containers,
      ...attached.split(/\s+/).filter(Boolean),
    ]).catch(() => undefined);
    await exec("docker", ["network", "rm", network]).catch(() => undefined);
  };
  await docker("network", "create", network);
  try {
    await run(
      "headscale",
      "--network-alias",
      "headscale",
      "-v",
      `${path.join(HERE, "headscale/config.yaml")}:/etc/headscale/config.yaml:ro`,
      "-v",
      `${path.join(HERE, "headscale/policy.hujson")}:/etc/headscale/policy.hujson:ro`,
      "-v",
      `${file("headscale.pem")}:/etc/headscale/tls.pem:ro`,
      "-v",
      `${file("headscale.key")}:/etc/headscale/tls.key:ro`,
      HEADSCALE_IMAGE,
      "serve",
    );
    const headscale = (...args: string[]) =>
      docker("exec", name("headscale"), "headscale", ...args);
    await until(
      async () => Boolean(await headscale("users", "list", "-o", "json")),
      "headscale",
    );
    const user = String(
      (
        JSON.parse(
          await headscale("users", "create", "fleet", "-o", "json"),
        ) as {
          id: number;
        }
      ).id,
    );

    await run(
      "artifacts",
      "--network-alias",
      "artifacts",
      "-v",
      `${file("artifacts")}:/srv:ro`,
      "-v",
      `${file("artifacts.pem")}:/etc/artifacts/tls.pem:ro`,
      "-v",
      `${file("artifacts.key")}:/etc/artifacts/tls.key:ro`,
      "-v",
      `${path.join(HERE, "artifacts.py")}:/artifacts.py:ro`,
      PYTHON_IMAGE,
      "python",
      "/artifacts.py",
    );

    // Single-use, tagged and pre-authorized, like the operator's Tailscale keys.
    const mint = async (tag: string) => {
      const created = JSON.parse(
        await headscale(
          "preauthkeys",
          "create",
          "--user",
          user,
          "--tags",
          tag,
          "--expiration",
          "1h",
          "-o",
          "json",
        ),
      ) as { id: number; key: string };
      return { key: created.key, id: String(created.id) };
    };

    await run(
      "sidecar",
      "-e",
      "SSL_CERT_FILE=/ca.pem",
      "-v",
      `${file("ca.pem")}:/ca.pem:ro`,
      "-p",
      "127.0.0.1::1055",
      "--entrypoint",
      "tailscaled",
      TAILSCALE_IMAGE,
      "--tun=userspace-networking",
      "--statedir=/var/lib/tailscale",
      "--socks5-server=0.0.0.0:1055",
    );
    const sidecar = (...args: string[]) =>
      docker("exec", name("sidecar"), "tailscale", ...args);
    await until(async () => {
      await sidecar(
        "up",
        "--login-server=https://headscale",
        `--auth-key=${(await mint("tag:gpu-fleet")).key}`,
        "--hostname=gpu-fleet-e2e",
        "--accept-dns=false",
        "--timeout=30s",
      );
      return true;
    }, "the sidecar to join");
    const socksPort = Number(
      (await docker("port", name("sidecar"), "1055/tcp")).split(":").pop(),
    );
    const self = JSON.parse(await sidecar("status", "--json")) as {
      Self: { TailscaleIPs: string[] };
    };

    const nodes = async () =>
      JSON.parse(await headscale("nodes", "list", "-o", "json")) as Node[];

    return {
      network,
      socksPort,
      sidecarAddress: self.Self.TailscaleIPs.find((ip) => ip.includes("."))!,
      status: async () =>
        JSON.parse(await sidecar("status", "--json")) as TailnetStatus,
      nodes,
      mint,
      expire: (id: string) =>
        headscale("preauthkeys", "expire", "--id", id, "--force"),
      deleteNode: (id: number) =>
        headscale("nodes", "delete", "--identifier", String(id), "--force"),
      renameNode: (id: number, newName: string) =>
        headscale("nodes", "rename", "--identifier", String(id), newName),
      stop,
    };
  } catch (error) {
    await stop();
    throw error;
  }
};

export type Tailnet = Awaited<ReturnType<typeof startTailnet>>;

/**
 * The operator's tailnet name rules on headscale. Tailscale makes a
 * re-authenticated pod a new device, so production claims the device created
 * since enrollment began; headscale keeps the node and retags it, so here the
 * promoted device is the online tag:gpu-inference node with the instance's
 * hostname. Removing the old device and claiming the exact name are the same.
 */
export const headscaleNames = (tailnet: Tailnet) => {
  const instanceNodes = async (instanceId: string) => {
    const hostname = `gpu-${instanceId}`;
    const label = new RegExp(`^${hostname}(-[a-z0-9]+)?$`);
    return (await tailnet.nodes()).filter(
      (node) =>
        (node.tags ?? []).includes(INFERENCE_TAG) &&
        (node.name === hostname || label.test(node.given_name)),
    );
  };
  return {
    instanceTailnet: async (instanceId: string) => {
      const nodes = await instanceNodes(instanceId);
      const seen = nodes
        .map((node) => node.last_seen?.seconds)
        .filter((value): value is number => value !== undefined)
        .sort((a, b) => a - b)
        .at(-1);
      return {
        connected: nodes.some((node) => node.online),
        ...(seen && { lastSeen: new Date(seen * 1000).toISOString() }),
      };
    },
    releaseName: async (instanceId: string) => {
      const nodes = await instanceNodes(instanceId);
      if (nodes.some((node) => node.online))
        throw new Error(
          `A connected tag:gpu-inference device already uses gpu-${instanceId}`,
        );
      for (const node of nodes) await tailnet.deleteNode(node.id);
      return nodes.length;
    },
    claimName: async (instanceId: string) => {
      const hostname = `gpu-${instanceId}`;
      const nodes = await instanceNodes(instanceId);
      const promoted = nodes.find(
        (node) => node.online && node.name === hostname,
      );
      const address = promoted?.ip_addresses.find((ip) => ip.includes("."));
      if (!promoted || !address)
        throw new Error(`${hostname} has no new tag:gpu-inference device`);
      if (nodes.some((node) => node !== promoted))
        throw new Error(
          `Another tag:gpu-inference device still uses ${hostname}`,
        );
      if (promoted.given_name !== hostname)
        await tailnet.renameNode(promoted.id, hostname);
      return address;
    },
  };
};

// A SOCKS5 CONNECT by name: tailscaled resolves the MagicDNS name, as the
// cluster's egress proxy does for gpu-<id>.<tailnet>.
const socksByName = (port: number, host: string, target: number) =>
  new Promise<Socket>((resolve, reject) => {
    const socket = connect(port, "127.0.0.1");
    const name = Buffer.from(host);
    let stage = 0;
    let received = Buffer.alloc(0);
    socket.once("error", reject);
    // TCP may split a reply; each step waits for the bytes it reads.
    const step = (data: Buffer) => {
      received = Buffer.concat([received, data]);
      if (stage === 0) {
        if (received.length < 2) return;
        if (received[0] !== 5 || received[1] !== 0)
          return reject(new Error("SOCKS proxy refused anonymous access"));
        received = received.subarray(2);
        stage = 1;
        socket.write(
          Buffer.concat([
            Buffer.from([5, 1, 0, 3, name.length]),
            name,
            Buffer.from([target >> 8, target & 255]),
          ]),
        );
      }
      if (received.length < 2) return;
      socket.off("data", step);
      socket.off("error", reject);
      if (received[1] !== 0)
        return reject(
          new Error(`SOCKS connect to ${host} failed: ${received[1]}`),
        );
      resolve(socket);
    };
    socket.on("data", step);
    socket.on("connect", () => socket.write(Buffer.from([5, 1, 0])));
  });

/**
 * A local listener per host that tunnels to gpu-<id>.tailnet.test:8888, so the
 * operator's unchanged pingHost reaches the host agent by its MagicDNS name.
 */
export const egressByName = async (socksPort: number, instanceId: string) => {
  const open = new Set<Socket>();
  const server: Server = createServer((client) => {
    open.add(client);
    client.on("close", () => open.delete(client));
    client.on("error", () => client.destroy());
    socksByName(socksPort, `gpu-${instanceId}.${DOMAIN}`, 8888).then(
      (upstream) => {
        client.pipe(upstream).pipe(client);
        upstream.on("error", () => client.destroy());
        client.on("close", () => upstream.destroy());
      },
      // Like the cluster's egress proxy, a host that is not there leaves the
      // connection open without an answer, so ping times out (a silent host).
      () => undefined,
    );
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as { port: number };
  return {
    endpoint: `http://127.0.0.1:${port}/_kubelet`,
    close: () =>
      new Promise<void>((resolve) => {
        for (const socket of open) socket.destroy();
        server.close(() => resolve());
      }),
  };
};
