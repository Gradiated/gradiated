import { execFileSync } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { withFreshTokenRetry } from "../../../../tools/nomad/api.mjs";
const image =
  "hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9";
const network = "token-visibility-" + process.pid;
const nodes = [0, 1, 2].map((i) => network + "-" + i);
const emit = (event, data = {}) =>
  console.log(JSON.stringify({ at: new Date().toISOString(), event, ...data }));
const docker = (args, options = {}) =>
  execFileSync("docker", args, {
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
    timeout: 15000,
    ...options,
  });
const cli = (node, args, token, input) =>
  docker(
    [
      "exec",
      ...(input ? ["-i"] : []),
      ...(token ? ["-e", "NOMAD_TOKEN"] : []),
      node,
      "nomad",
      ...args,
    ],
    {
      env: { ...process.env, ...(token ? { NOMAD_TOKEN: token } : {}) },
      ...(input ? { input } : {}),
    },
  );
const signal = AbortSignal.timeout(180000);
let reconnect;
try {
  docker(["network", "create", "--subnet", "198.18.253.0/24", network]);
  for (const node of nodes) {
    docker([
      "run",
      "-d",
      "--name",
      node,
      "--network",
      network,
      "--entrypoint",
      "/bin/sh",
      image,
      "-c",
      `printf 'acl { enabled = true }\n' >/tmp/acl.hcl; exec nomad agent -server -bootstrap-expect=3 -data-dir=/tmp/nomad -bind=0.0.0.0 -config=/tmp/acl.hcl -retry-join=${nodes[0]}`,
    ]);
  }
  let root;
  for (let i = 0; i < 45; i++) {
    try {
      root = JSON.parse(cli(nodes[0], ["acl", "bootstrap", "-json"]));
      if (root.SecretID) break;
    } catch {}
    await delay(1000);
  }
  if (!root) throw new Error("No fixture ACL bootstrap");
  let leaderAddress;
  for (let i = 0; i < 45; i++) {
    try {
      leaderAddress = JSON.parse(
        cli(nodes[0], ["operator", "api", "/v1/status/leader"], root.SecretID),
      );
      if (leaderAddress) break;
    } catch {}
    await delay(1000);
  }
  if (!leaderAddress) throw new Error("No fixture leader");
  const ips = nodes.map((node) =>
    docker([
      "inspect",
      "--format",
      `{{(index .NetworkSettings.Networks "${network}").IPAddress}}`,
      node,
    ]).trim(),
  );
  const leader = nodes[ips.indexOf(leaderAddress.split(":")[0])];
  const follower = nodes.find((n) => n !== leader);

  cli(
    leader,
    ["acl", "policy", "apply", "fixture-reader", "-"],
    root.SecretID,
    'namespace "default" { capabilities = ["list-jobs", "read-job"] }',
  );
  for (const node of nodes) {
    let ready = false;
    for (let i = 0; i < 30; i++) {
      try {
        signal.throwIfAborted();
        JSON.parse(
          cli(node, ["operator", "api", "/v1/jobs?stale=true"], root.SecretID),
        );
        ready = true;
        break;
      } catch {
        await delay(100);
      }
    }
    if (!ready) throw new Error("Fixture ACLs did not converge");
  }
  docker(["network", "disconnect", network, follower]);
  const token = JSON.parse(
    cli(
      leader,
      [
        "acl",
        "token",
        "create",
        "-name=fixture-fresh-token",
        "-policy=fixture-reader",
        "-ttl=2m",
        "-json",
      ],
      root.SecretID,
    ),
  );
  const issuedAt = Date.now();
  let rejected = 0;
  const read = async () => {
    try {
      const body = cli(
        follower,
        ["operator", "api", "/v1/jobs?stale=true"],
        token.SecretID,
      );
      if (body.trim() === "Permission denied") {
        rejected++;
        throw Object.assign(new Error("Follower has not received token"), {
          statusCode: 403,
        });
      }
      return JSON.parse(body);
    } catch (e) {
      if (e.statusCode === 403) throw e;
      if (String(e.stderr).includes("403")) {
        rejected++;
        throw Object.assign(new Error("Follower has not received token"), {
          statusCode: 403,
        });
      }
      throw new Error(
        "Unexpected follower response: " +
          String(e.stderr ?? e.message).slice(0, 400),
      );
    }
  };
  try {
    await read();
    throw new Error("Fixture did not reproduce the rejection");
  } catch (e) {
    if (e.statusCode !== 403) throw e;
  }
  emit("original_fresh_token_rejection_reproduced");
  reconnect = (async () => {
    await delay(600);
    docker([
      "network",
      "connect",
      "--ip",
      ips[nodes.indexOf(follower)],
      network,
      follower,
    ]);
    emit("follower_replication_restored");
  })();
  // Keep a failed reconnect handled until cleanup awaits it.
  reconnect.catch(() => {});
  const result = await withFreshTokenRetry(read, issuedAt, signal);
  await reconnect;
  if (!Array.isArray(result)) throw new Error("Invalid follower result");
  emit("fresh_token_retry_recovery_verified", {
    rejected,
    elapsed_ms: Date.now() - issuedAt,
  });
} catch (e) {
  emit("fixture_failed", { message: e.message });
  process.exitCode = 1;
} finally {
  if (reconnect) await reconnect.catch(() => {});
  for (const node of nodes) {
    try {
      docker(["rm", "-f", node]);
    } catch {
      process.exitCode = 1;
      emit("fixture_cleanup_failed", { node });
    }
  }
  try {
    docker(["network", "rm", network]);
  } catch {
    process.exitCode = 1;
    emit("fixture_network_cleanup_failed");
  }
  emit("fixture_cleanup_complete");
}
