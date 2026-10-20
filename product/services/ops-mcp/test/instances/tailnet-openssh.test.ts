import { execFileSync, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { readEnrollment } from "../../src/instances/in-place.js";
import { sshRunner } from "../../src/instances/ssh.js";
import { bootstrapPeer, socksConnector } from "../../src/instances/tailnet.js";

// A container stands in for a bootstrap GPU pod: OpenSSH accepts "none"
// authentication for root, as Tailscale SSH does, on a tailnet-range address,
// and OpenSSH's dynamic forwarding is the SOCKS5 proxy the sidecar provides.
const UBUNTU =
  "ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac";
const POD_ADDRESS = "100.64.0.9";
const SETUP = `set -euo pipefail
umask 022
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends openssh-server openssh-client python3 iproute2 >/dev/null
mkdir -p /run/sshd
ssh-keygen -A >/dev/null
passwd -d root >/dev/null
printf 'PermitRootLogin yes\\nPermitEmptyPasswords yes\\nPasswordAuthentication yes\\nKbdInteractiveAuthentication no\\nUsePAM no\\n' >/etc/ssh/sshd_config.d/00-none.conf
ip addr add ${POD_ADDRESS}/32 dev lo
/usr/sbin/sshd
ssh -f -N -D 0.0.0.0:1080 -o StrictHostKeyChecking=no -o BatchMode=yes root@127.0.0.1
`;
const docker = (...args: string[]) =>
  execFileSync("docker", args, { encoding: "utf8", timeout: 600_000 });
const available =
  spawnSync("docker", ["info"], { stdio: "ignore" }).status === 0;

describe.skipIf(!available)("enrollment SSH over SOCKS5 to OpenSSH", () => {
  const container = `ops-mcp-tailnet-${randomUUID()}`;
  let socksPort = 0;
  let hostKeys: readonly string[] = [];

  beforeAll(() => {
    docker(
      "run",
      "-d",
      "--name",
      container,
      "--cap-add",
      "NET_ADMIN",
      "-p",
      "127.0.0.1::1080",
      UBUNTU,
      "sleep",
      "600",
    );
    docker("exec", container, "bash", "-c", SETUP);
    socksPort = Number(
      docker("port", container, "1080").trim().split(":").at(-1),
    );
    const keys = docker(
      "exec",
      container,
      "bash",
      "-c",
      "cat /etc/ssh/ssh_host_*_key.pub",
    )
      .trim()
      .split("\n");
    hostKeys = bootstrapPeer(
      {
        Peer: {
          pod: {
            HostName: "gpu-bootstrap-pod1",
            TailscaleIPs: [POD_ADDRESS],
            Tags: ["tag:gpu-bootstrap"],
            Online: true,
            sshHostKeys: keys,
          },
        },
      },
      "pod1",
    )!.hostKeysSha256;
  }, 600_000);

  afterAll(() => {
    spawnSync("docker", ["rm", "-f", container], { stdio: "ignore" });
  });

  const run = () => sshRunner(socksConnector("127.0.0.1", socksPort));

  it("runs the enrollment command with stdin and pinned host keys", async () => {
    await expect(
      run()(
        { host: POD_ADDRESS, port: 22, hostKeySha256: hostKeys },
        `python3 -c 'import sys; print(sys.stdin.read()[::-1])'`,
        "private-bootstrap-material",
      ),
    ).resolves.toBe("lairetam-partstoob-etavirp\n");
    await expect(
      run()(
        { host: POD_ADDRESS, port: 22, hostKeySha256: hostKeys },
        readEnrollment,
      ),
    ).resolves.toBe("{}\n");
  });

  it("refuses an unpinned host key before sending the command", async () => {
    await expect(
      run()(
        { host: POD_ADDRESS, port: 22, hostKeySha256: ["0".repeat(64)] },
        "touch /tmp/should-not-exist",
        "secret",
      ),
    ).rejects.toThrow("pinned host keys");
    expect(
      spawnSync("docker", [
        "exec",
        container,
        "test",
        "-e",
        "/tmp/should-not-exist",
      ]).status,
    ).not.toBe(0);
  });

  it("reports only the exit status of a failed command", async () => {
    await expect(
      run()(
        { host: POD_ADDRESS, port: 22, hostKeySha256: hostKeys },
        "echo sensitive-output; echo sensitive-error >&2; exit 70",
      ),
    ).rejects.toThrow(/^In-place enrollment command exited with status 70$/);
  });

  it("dials only tailnet addresses", async () => {
    await expect(
      run()({ host: "127.0.0.1", port: 22, hostKeySha256: hostKeys }, "true"),
    ).rejects.toThrow("Tailnet connection");
  });
});
