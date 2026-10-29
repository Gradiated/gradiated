import { createHash, generateKeyPairSync } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import { createServer as createHttpServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { utils } from "ssh2";
import { describe, expect, it } from "vitest";

import {
  bootstrapPeer,
  localStatus,
  waitForPromotion,
  type TailnetStatus,
} from "../src/tailnet.js";

const hostKey = generateKeyPairSync("rsa", { modulusLength: 2048 })
  .privateKey.export({ type: "pkcs1", format: "pem" })
  .toString();
const parsed = utils.parseKey(hostKey);
if (parsed instanceof Error || Array.isArray(parsed))
  throw new Error("Invalid test host key");
const publicLine = `ssh-rsa ${parsed.getPublicSSH().toString("base64")}`;
const fingerprint = createHash("sha256")
  .update(parsed.getPublicSSH())
  .digest("hex");

const peer = (overrides = {}) => ({
  HostName: "gpu-bootstrap-pod1",
  TailscaleIPs: ["100.64.0.9", "fd7a::9"],
  Tags: ["tag:gpu-bootstrap"],
  Online: true,
  sshHostKeys: [publicLine],
  ...overrides,
});

describe("tailnet bootstrap peers", () => {
  it("pins the tailnet address and Tailscale SSH host keys of the bootstrap pod", () => {
    expect(bootstrapPeer({ Peer: { a: peer() } }, "pod1")).toEqual({
      ip: "100.64.0.9",
      hostKeysSha256: [fingerprint],
    });
  });

  it("ignores other pods and enrolled hosts", () => {
    for (const other of [
      peer({ HostName: "gpu-bootstrap-pod2" }),
      peer({ Tags: ["tag:gpu-inference"] }),
    ])
      expect(bootstrapPeer({ Peer: { a: other } }, "pod1")).toBeNull();
  });

  it("refuses duplicates and pods without Tailscale SSH", () => {
    expect(() =>
      bootstrapPeer({ Peer: { a: peer(), b: peer() } }, "pod1"),
    ).toThrow("Several tailnet devices");
    for (const broken of [
      peer({ sshHostKeys: [] }),
      peer({ TailscaleIPs: ["203.0.113.9"] }),
    ])
      expect(() => bootstrapPeer({ Peer: { a: broken } }, "pod1")).toThrow(
        "not online with Tailscale SSH",
      );
    expect(() => bootstrapPeer({}, "../pod")).toThrow("Invalid RunPod pod ID");
  });

  it("ignores the offline device a re-imaged pod leaves under the same name", () => {
    const stale = peer({ Online: false, TailscaleIPs: ["100.64.0.8"] });
    expect(bootstrapPeer({ Peer: { a: stale } }, "pod1")).toBeNull();
    expect(bootstrapPeer({ Peer: { a: stale, b: peer() } }, "pod1")?.ip).toBe(
      "100.64.0.9",
    );
  });

  it("waits until the bootstrap address has left the netmap", async () => {
    const statuses: TailnetStatus[] = [
      { Peer: { a: peer() } },
      { Peer: {} },
      { Peer: {} },
    ];
    await expect(
      waitForPromotion(async () => statuses.shift()!, "100.64.0.9", 1_000, 1),
    ).resolves.toBeUndefined();
  });

  it("treats the offline bootstrap device left by re-authentication as promoted", async () => {
    const left = peer({ Online: false });
    await expect(
      waitForPromotion(
        async () => ({ Peer: { a: left } }),
        "100.64.0.9",
        1_000,
        1,
      ),
    ).resolves.toBeUndefined();
  });

  it("fails when re-authentication keeps the bootstrap tag under a new name", async () => {
    const renamed = peer({
      HostName: "gpu-00000000-0000-4000-8000-000000000001",
    });
    await expect(
      waitForPromotion(
        async () => ({ Peer: { a: renamed } }),
        "100.64.0.9",
        20,
        1,
      ),
    ).rejects.toThrow("did not re-authenticate");
  });
});

describe("tailnet transport", () => {
  it("reads peers from the sidecar LocalAPI", async () => {
    const directory = mkdtempSync(join(tmpdir(), "localapi-"));
    const socketPath = join(directory, "tailscaled.sock");
    const server = createHttpServer((request, response) => {
      expect(request.url).toBe("/localapi/v0/status");
      response.end(JSON.stringify({ Peer: { a: peer() } }));
    });
    await new Promise<void>((resolve) => server.listen(socketPath, resolve));
    try {
      const status = await localStatus(socketPath);
      expect(bootstrapPeer(status, "pod1")?.ip).toBe("100.64.0.9");
    } finally {
      await new Promise<void>((resolve) => server.close(() => resolve()));
      rmSync(directory, { recursive: true, force: true });
    }
  });
});
