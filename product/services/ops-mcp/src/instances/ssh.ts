import type { Duplex } from "node:stream";
import { Client } from "ssh2";

export type SshTarget = {
  readonly host: string;
  readonly port: number;
  readonly hostKeySha256: string | readonly string[];
};

export type RunSsh = (
  target: SshTarget,
  command: string,
  input?: string,
  timeoutMs?: number,
) => Promise<string>;

export type ConnectSocket = (host: string, port: number) => Promise<Duplex>;

// Without credentials ssh2 offers only "none" authentication, which Tailscale
// SSH accepts when the tailnet policy allows the connecting node.
const exceptionClass = (stderr: string) => {
  const name = stderr
    .trimEnd()
    .split("\n")
    .at(-1)
    ?.match(/^([A-Za-z_][\w.]*(?:Error|Exception|Exit))(?::|$)/)?.[1];
  return name ? ` (${name})` : "";
};

export const sshRunner =
  (connect: ConnectSocket): RunSsh =>
  (target, command, input, timeoutMs = 60_000) =>
    new Promise((resolve, reject) => {
      const client = new Client();
      const pinned = [target.hostKeySha256].flat();
      let settled = false;
      const finish = (error?: Error, output = "") => {
        if (settled) return;

        settled = true;
        clearTimeout(timeout);
        client.end();
        if (error) reject(error);
        else resolve(output);
      };
      const timeout = setTimeout(
        () => finish(new Error("In-place enrollment SSH timed out")),
        timeoutMs,
      );

      client.on("error", () =>
        finish(
          new Error(
            "Tailscale SSH to the GPU pod failed; check its pinned host keys",
          ),
        ),
      );
      client.on("close", () =>
        finish(new Error("In-place enrollment SSH closed before completing")),
      );
      client.on("ready", () => {
        client.exec(command, (error, stream) => {
          if (error) {
            finish(new Error("In-place enrollment SSH command failed"));
            return;
          }

          let output = "";
          stream.on("data", (data: Buffer) => {
            output += data.toString();
            if (output.length > 65_536)
              finish(
                new Error(
                  "In-place enrollment SSH response exceeded its limit",
                ),
              );
          });
          // Remote output can contain credentials. Errors expose only the exit
          // status and the class of a Python exception, never its message.
          let errors = "";
          stream.stderr.on("data", (data: Buffer) => {
            errors = (errors + data.toString()).slice(-4096);
          });
          stream.on("error", () =>
            finish(new Error("In-place enrollment SSH stream failed")),
          );
          stream.on("close", (code: number | null) => {
            finish(
              code === 0
                ? undefined
                : new Error(
                    `In-place enrollment command exited with status ${code}${exceptionClass(errors)}`,
                  ),
              output,
            );
          });
          stream.end(input ?? "");
        });
      });

      connect(target.host, target.port).then(
        (sock) =>
          client.connect({
            sock,
            username: "root",
            hostHash: "sha256",
            hostVerifier: (hash: string) => pinned.includes(hash),
            readyTimeout: 15_000,
          }),
        () => finish(new Error("Tailnet connection to the GPU pod failed")),
      );
    });
