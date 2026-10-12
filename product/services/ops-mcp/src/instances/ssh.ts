import { Client } from "ssh2";

export type SshTarget = {
  readonly host: string;
  readonly port: number;
  readonly hostKeySha256: string;
};

export type RunSsh = (
  target: SshTarget,
  command: string,
  input?: string,
  timeoutMs?: number,
) => Promise<string>;

export const sshRunner =
  (privateKey: string): RunSsh =>
  (target, command, input, timeoutMs = 60_000) =>
    new Promise((resolve, reject) => {
      const client = new Client();
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
            "In-place enrollment SSH failed; check the pinned host key and credentials",
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
          // Remote output can contain credentials; errors expose only the exit status.
          stream.stderr.resume();
          stream.on("error", () =>
            finish(new Error("In-place enrollment SSH stream failed")),
          );
          stream.on("close", (code: number | null) => {
            finish(
              code === 0
                ? undefined
                : new Error(
                    `In-place enrollment command exited with status ${code}`,
                  ),
              output,
            );
          });
          stream.end(input ?? "");
        });
      });
      client.connect({
        host: target.host,
        port: target.port,
        username: "root",
        privateKey,
        hostHash: "sha256",
        hostVerifier: (hash: string) => hash === target.hostKeySha256,
        readyTimeout: 15_000,
      });
    });
