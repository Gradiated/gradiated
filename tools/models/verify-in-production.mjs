import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const verifyOnce = (input, signal, spawnProcess) =>
  new Promise((resolve, reject) => {
    const child = spawnProcess(
      "kubectl",
      [
        "-n",
        "gradiated",
        "exec",
        "-i",
        "-c",
        "worker",
        "deployment/worker",
        "--",
        "node",
        "services/worker/dist/verify-model.js",
      ],
      { signal, timeout: 8 * 60_000, stdio: ["pipe", "inherit", "inherit"] },
    );
    child.on("error", reject);
    child.stdin.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve();
      else
        reject(
          Object.assign(
            new Error(`Production SDK verification exited with ${code}`),
            { exitCode: code },
          ),
        );
    });
    child.stdin.end(JSON.stringify(input));
  });

export const verifyInProduction = async (
  input,
  signal,
  { spawnProcess = spawn, pause = delay } = {},
) => {
  for (let attempt = 1; ; attempt++) {
    signal?.throwIfAborted();
    try {
      await verifyOnce(input, signal, spawnProcess);
      return;
    } catch (error) {
      // A rolling worker deployment can terminate kubectl exec. Re-run the
      // complete SDK check on a current worker; never retry assertion failures.
      if (
        signal?.aborted ||
        attempt >= 3 ||
        ![137, 143].includes(error.exitCode)
      )
        throw error;
      await pause(5000, undefined, { signal });
    }
  }
};
