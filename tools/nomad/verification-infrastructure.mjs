import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { setTimeout as delay } from "node:timers/promises";

const execute = promisify(execFile);
const run = async (args, signal) =>
  (
    await execute("kubectl", args, {
      signal,
      timeout: 30_000,
      maxBuffer: 8 * 1024 * 1024,
    })
  ).stdout;

const variables = {
  gateway: ["GATEWAY_VERIFICATION_WORKSPACE_ID"],
  worker: ["MODEL_VERIFICATION_WORKSPACE_ID", "MODEL_VERIFICATION_USER_ID"],
};

export const verificationInfrastructureReady = (desired, live) =>
  Object.entries(variables).every(([name, required]) => {
    const expected = desired.find(
      (item) =>
        item.kind === "Deployment" &&
        item.metadata.namespace === "gradiated" &&
        item.metadata.name === name,
    );
    const actual = live.find((item) => item.metadata.name === name);
    if (
      !expected ||
      !actual ||
      !(actual.status?.observedGeneration >= actual.metadata.generation)
    )
      return false;
    const replicas = actual.spec.replicas;
    if (
      !replicas ||
      ![
        "replicas",
        "updatedReplicas",
        "readyReplicas",
        "availableReplicas",
      ].every((field) => actual.status?.[field] === replicas)
    )
      return false;

    const target = expected.spec.template.spec.containers.find(
      (container) => container.name === name,
    );
    const current = actual.spec.template.spec.containers.find(
      (container) => container.name === name,
    );
    return (
      target &&
      current &&
      required.every((variable) => {
        const value = target.env?.find(
          (entry) => entry.name === variable,
        )?.value;
        return (
          value &&
          current.env?.find((entry) => entry.name === variable)?.value === value
        );
      })
    );
  });

export const waitForVerificationInfrastructure = async (signal) => {
  const rendered = await run(
    [
      "create",
      "--dry-run=client",
      "--validate=false",
      "-k",
      "infra/environments/prod/us-east-1/kubernetes/workloads",
      "-o",
      String.raw`jsonpath={@}{"\n"}`,
    ],
    signal,
  );
  const desired = rendered
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));
  while (!signal.aborted) {
    try {
      const [live, permission] = await Promise.all([
        run(
          [
            "-n",
            "gradiated",
            "get",
            "deployments",
            "gateway",
            "worker",
            "-o",
            "json",
          ],
          signal,
        ),
        run(
          [
            "auth",
            "can-i",
            "create",
            "pods",
            "--subresource=exec",
            "-n",
            "gradiated",
          ],
          signal,
        ),
      ]);
      if (
        permission.trim() === "yes" &&
        verificationInfrastructureReady(desired, JSON.parse(live).items)
      )
        return;
    } catch {
      signal.throwIfAborted();
    }
    await delay(5000, undefined, { signal });
  }
  throw new Error(
    "Verification infrastructure did not converge before its deadline",
  );
};
