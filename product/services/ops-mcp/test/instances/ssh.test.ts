import { createHash, generateKeyPairSync } from "node:crypto";
import type { AddressInfo } from "node:net";
import { Server, utils } from "ssh2";
import { describe, expect, it } from "vitest";

import { sshRunner } from "../../src/instances/ssh.js";

const key = () =>
  generateKeyPairSync("rsa", { modulusLength: 2048 })
    .privateKey.export({ type: "pkcs1", format: "pem" })
    .toString();
const hostKey = key();
const privateKey = key();
const parsed = utils.parseKey(hostKey);
if (parsed instanceof Error || Array.isArray(parsed))
  throw new Error("Invalid test host key");
const fingerprint = createHash("sha256")
  .update(parsed.getPublicSSH())
  .digest("hex");

const withServer = async (
  test: (
    port: number,
    calls: { command: string; input: string }[],
  ) => Promise<void>,
  code = 0,
) => {
  const calls: { command: string; input: string }[] = [];
  const server = new Server({ hostKeys: [hostKey] }, (client) => {
    client.on("error", () => {});
    client.on("authentication", (context) => context.accept());
    client.on("ready", () =>
      client.on("session", (accept) => {
        accept().on("exec", (acceptCommand, _reject, info) => {
          const stream = acceptCommand();
          let input = "";
          stream.on("data", (data: Buffer) => {
            input += data.toString();
          });
          stream.on("end", () => {
            calls.push({ command: info.command, input });
            if (code) stream.stderr.write("sensitive-remote-error-private-key");
            stream.write(code ? "sensitive-output" : "{}\n");
            stream.exit(code);
            stream.end();
          });
        });
      }),
    );
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    await test((server.address() as AddressInfo).port, calls);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
};

describe("pinned enrollment SSH", () => {
  it("verifies the host and sends bootstrap material on stdin", async () => {
    await withServer(async (port, calls) => {
      const result = await sshRunner(privateKey)(
        { host: "127.0.0.1", port, hostKeySha256: fingerprint },
        "fixed-enrollment-command",
        "private-bootstrap-material",
      );

      expect(result).toBe("{}\n");
      expect(calls).toEqual([
        {
          command: "fixed-enrollment-command",
          input: "private-bootstrap-material",
        },
      ]);
    });
  });

  it("rejects a different host key before sending any command or secret", async () => {
    await withServer(async (port, calls) => {
      await expect(
        sshRunner(privateKey)(
          { host: "127.0.0.1", port, hostKeySha256: "0".repeat(64) },
          "command",
          "secret",
        ),
      ).rejects.toThrow("pinned host key");
      expect(calls).toEqual([]);
    });
  });

  it("keeps remote stdout and stderr out of failed registration errors", async () => {
    await withServer(async (port) => {
      await expect(
        sshRunner(privateKey)(
          { host: "127.0.0.1", port, hostKeySha256: fingerprint },
          "command",
          "secret",
        ),
      ).rejects.toThrow("exited with status 70");
    }, 70);
  });
});
