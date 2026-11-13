import { createHash } from "node:crypto";
import { request } from "node:http";
import { connect as connectTcp, type Socket } from "node:net";
import { z } from "zod";

import type { ConnectSocket } from "./ssh.js";

export const BOOTSTRAP_TAG = "tag:gpu-bootstrap";

const tailnetIpv4 = (ip: string) => {
  const parts = ip.split(".").map(Number);
  return (
    parts.length === 4 &&
    parts.every((part) => Number.isInteger(part) && part >= 0 && part <= 255) &&
    parts[0] === 100 &&
    parts[1]! >= 64 &&
    parts[1]! <= 127
  );
};

const statusSchema = z.object({
  Peer: z
    .record(
      z.string(),
      z.object({
        HostName: z.string(),
        Created: z.string().optional(),
        TailscaleIPs: z.array(z.string()).nullish(),
        Tags: z.array(z.string()).nullish(),
        Online: z.boolean().optional(),
        sshHostKeys: z.array(z.string()).nullish(),
      }),
    )
    .nullish(),
});

export type TailnetStatus = z.infer<typeof statusSchema>;

export type BootstrapPeer = {
  readonly ip: string;
  readonly createdAt?: string;
  readonly hostKeysSha256: readonly string[];
};

// Tailscale reports host keys in authorized_keys form; ssh2 hashes the key blob.
const hostKeyHash = (line: string) => {
  const blob = line.trim().split(/\s+/)[1];
  if (!blob) throw new Error("Invalid Tailscale SSH host key");

  return createHash("sha256").update(Buffer.from(blob, "base64")).digest("hex");
};

export const bootstrapPeer = (
  status: TailnetStatus,
  podId: string,
): BootstrapPeer | null => {
  if (!/^[a-z0-9]{1,40}$/.test(podId)) throw new Error("Invalid RunPod pod ID");

  // A re-imaged pod joins as a new device under the same name; the device from
  // its previous boot stays listed offline.
  const matches = Object.values(status.Peer ?? {}).filter(
    (peer) =>
      peer.Online !== false &&
      peer.HostName === `gpu-bootstrap-${podId}` &&
      (peer.Tags ?? []).includes(BOOTSTRAP_TAG),
  );
  if (!matches.length) return null;
  if (matches.length > 1)
    throw new Error(
      `Several tailnet devices claim gpu-bootstrap-${podId}; remove the stale ones before enrolling`,
    );

  const [peer] = matches;
  const ip = (peer!.TailscaleIPs ?? []).find(tailnetIpv4);
  const hostKeysSha256 = (peer!.sshHostKeys ?? []).map(hostKeyHash);
  if (!peer!.Online || !ip || !hostKeysSha256.length)
    throw new Error(
      `gpu-bootstrap-${podId} is not online with Tailscale SSH enabled`,
    );

  return {
    ip,
    hostKeysSha256,
    ...(peer!.Created && { createdAt: peer!.Created }),
  };
};

export const localStatus = (socketPath: string) =>
  new Promise<TailnetStatus>((resolve, reject) => {
    const call = request(
      {
        socketPath,
        path: "/localapi/v0/status",
        headers: { host: "local-tailscaled.sock" },
        timeout: 10_000,
      },
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk: string) => {
          body += chunk;
        });
        response.on("end", () => {
          try {
            if (response.statusCode !== 200)
              throw new Error(`status ${response.statusCode}`);
            resolve(statusSchema.parse(JSON.parse(body)));
          } catch {
            reject(
              new Error("The ops-mcp Tailscale sidecar status is unavailable"),
            );
          }
        });
      },
    );
    call.on("timeout", () => call.destroy());
    call.on("error", () =>
      reject(new Error("The ops-mcp Tailscale sidecar is unavailable")),
    );
    call.end();
  });

const read = (socket: Socket, length: number) =>
  new Promise<Buffer>((resolve, reject) => {
    const attempt = () => {
      const chunk = socket.read(length) as Buffer | null;
      if (!chunk) return false;

      socket.off("readable", onReadable);
      socket.off("error", reject);
      socket.off("end", onEnd);
      resolve(chunk);
      return true;
    };
    const onReadable = () => void attempt();
    const onEnd = () => reject(new Error("SOCKS proxy closed the connection"));
    if (attempt()) return;

    socket.on("readable", onReadable);
    socket.once("error", reject);
    socket.once("end", onEnd);
  });

export const socksConnector =
  (proxyHost: string, proxyPort: number): ConnectSocket =>
  async (host, port) => {
    if (!tailnetIpv4(host))
      throw new Error("Expected a Tailscale IPv4 address");

    const socket = connectTcp({ host: proxyHost, port: proxyPort });
    socket.setTimeout(15_000, () => socket.destroy(new Error("SOCKS timeout")));
    await new Promise<void>((resolve, reject) => {
      socket.once("connect", resolve);
      socket.once("error", reject);
    });
    try {
      socket.write(Buffer.from([5, 1, 0]));
      const method = await read(socket, 2);
      if (method[0] !== 5 || method[1] !== 0)
        throw new Error("SOCKS proxy refused anonymous access");

      socket.write(
        Buffer.from([
          5,
          1,
          0,
          1,
          ...host.split(".").map(Number),
          port >> 8,
          port & 255,
        ]),
      );
      const reply = await read(socket, 4);
      if (reply[0] !== 5 || reply[1] !== 0)
        throw new Error(`SOCKS connect failed with code ${reply[1]}`);

      const addressLength =
        reply[3] === 1 ? 4 : reply[3] === 4 ? 16 : (await read(socket, 1))[0]!;
      await read(socket, addressLength + 2);
    } catch (error) {
      socket.destroy();
      throw error;
    }
    socket.setTimeout(0);
    return socket;
  };

// ops-mcp may only see tag:gpu-bootstrap peers, so a promoted pod leaves its
// netmap. A failed re-authentication keeps the address and the bootstrap tag
// (possibly under the new hostname), so the address is what is tracked.
// Re-authentication registers a new device and leaves the bootstrap device
// offline, so only an online bootstrap device counts.
export const waitForPromotion = async (
  status: () => Promise<TailnetStatus>,
  address: string,
  timeoutMs = 180_000,
  pollMs = 5_000,
) => {
  const sleep = () => new Promise((resolve) => setTimeout(resolve, pollMs));
  const deadline = Date.now() + timeoutMs;
  let absent = 0;
  while (Date.now() < deadline) {
    const peers = Object.values((await status()).Peer ?? {});
    const bootstrap = peers.some(
      (peer) =>
        peer.Online !== false &&
        (peer.TailscaleIPs ?? []).includes(address) &&
        (peer.Tags ?? []).includes(BOOTSTRAP_TAG),
    );
    absent = bootstrap ? 0 : absent + 1;
    if (absent >= 2) return;

    await sleep();
  }
  throw new Error(
    `${address} is still a bootstrap device; it did not re-authenticate as tag:gpu-inference`,
  );
};
