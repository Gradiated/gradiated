// Disposable serving state for the whole run: one labelled Valkey container and
// the real gateway binary. This is a projection fixture, NOT a control-plane E2E.
import { execFile } from "node:child_process";
import { spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { existsSync, openSync, closeSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { createClient } from "redis";
import type { TestProject } from "vitest/node";

import { Client } from "./http-client.js";

const run = promisify(execFile);

const HERE = fileURLToPath(new URL(".", import.meta.url));
const ROOT = join(HERE, "../../../../..");
const BINARY = join(
  ROOT,
  "product/services/gateway/target/debug/gradiated-gateway",
);
const IMAGE = "valkey/valkey:8.1.9-alpine3.24";

/**
 * Pin the daemon to this host's own unix socket. Remote contexts are deliberately
 * refused: these containers must never be created on a shared or remote engine.
 */
const dockerHost = async (): Promise<string> => {
  const configured =
    process.env.DOCKER_HOST ??
    (await run("docker", [
      "context",
      "inspect",
      "--format",
      "{{.Endpoints.docker.Host}}",
    ])
      .then(({ stdout }) => stdout.trim())
      .catch(() => "unix:///var/run/docker.sock"));
  if (!configured.startsWith("unix://")) {
    throw new Error(`refusing a non-local Docker endpoint: ${configured}`);
  }
  return configured;
};

let DOCKER: string[] = [];

/** A real OpenAI-compatible runtime on CPU, when the fidelity suite is enabled. */
export interface RealRuntime {
  readonly baseUrl: string;
  readonly model: string;
}

export interface Stack {
  readonly redisUrl: string;
  readonly gatewayUrl: string;
  /**
   * A second gateway whose generation deadline is patient enough for real CPU
   * inference. The main one deliberately runs a three second deadline so the
   * cancellation tests are quick, which real inference cannot meet.
   */
  readonly patientGatewayUrl: string | null;
  readonly runtimeToken: string;
  readonly logPath: string;
}

export type RuntimeKind = "kev" | "vllm";

/** Each runtime is independently optional: one may be usable on CPU when the other is not. */
export type RealRuntimes = Partial<Record<RuntimeKind, RealRuntime>>;

declare module "vitest" {
  interface ProvidedContext {
    stack: Stack;
    realRuntimes: RealRuntimes;
  }
}

const docker = async (...args: string[]): Promise<string> => {
  const { stdout } = await run("docker", [...DOCKER, ...args], {
    timeout: 120_000,
  });
  return stdout.trim();
};

/**
 * Both streams, for commands whose output we are reading rather than parsing.
 * `docker logs` relays the container's stderr to ours, so a server that failed
 * with a traceback says nothing at all on stdout.
 */
const dockerOutput = async (...args: string[]): Promise<string> => {
  const { stdout, stderr } = await run("docker", [...DOCKER, ...args], {
    timeout: 120_000,
    maxBuffer: 8 * 1024 * 1024,
  });
  return `${stdout}${stderr}`.trim();
};

/** Remove a container only when this run's label proves it owns it. */
const removeOwned = async (name: string, label: string, owner: string) => {
  const found = await docker(
    "inspect",
    "--format",
    `{{index .Config.Labels "${label}"}}`,
    name,
  ).catch(() => "");
  if (found === owner) await docker("rm", "-f", "-v", name).catch(() => "");
};

/**
 * Real CPU runtimes used by the fidelity suite: one ordinary LLM and one native
 * decision server, which is all the gateway needs to route both protocols. Everything
 * about which servers we run lives here, so swapping one is a one-place change.
 * Set GATEWAY_REAL_RUNTIME_URL_VLLM / _KEV to point at servers already running.
 */
interface RuntimeImage {
  readonly image: string;
  /**
   * The id the gateway addresses and that the runtime returns. vLLM answers with
   * its `--served-model-name` rather than echoing, so the two must match.
   */
  readonly model: string;
  readonly ready: string;
  /** Extra `docker run` arguments, such as port publishing and resource limits. */
  readonly docker: (port: number) => Promise<string[]>;
  readonly args: (port: number) => string[];
}

const CPU_MODEL = "gradiated/cpu-test-model";

/**
 * Both runtimes are images we build with their weights already baked in, so a run
 * never reaches Hugging Face and readiness covers engine start only. They are built
 * from product/inference/runtimes/{vllm,kev}/Dockerfile.cpu.
 */
const VLLM_CPU_IMAGE =
  process.env.GATEWAY_REAL_RUNTIME_IMAGE ?? "gradiated/vllm-cpu:ci";
const KEV_CPU_IMAGE =
  process.env.GATEWAY_REAL_KEV_IMAGE ?? "gradiated/kev-cpu:ci";
const CPU_WEIGHTS = "Qwen/Qwen2.5-0.5B-Instruct";

const REAL_RUNTIMES: Record<RuntimeKind, RuntimeImage> = {
  vllm: {
    image: VLLM_CPU_IMAGE,
    model: process.env.GATEWAY_REAL_RUNTIME_MODEL ?? CPU_MODEL,
    ready: "/v1/models",
    docker: async (port) => [
      "-p",
      `127.0.0.1:${port}:8080`,
      // vLLM's multiprocess executor puts its ring buffer in shared memory and
      // needs 160 MiB of it; Docker's default /dev/shm is 64 MiB.
      "--shm-size=1g",
      "-e",
      // Keep the footprint small: a CI runner has to hold this alongside the
      // gateway, Valkey and the decision runtime.
      "VLLM_CPU_KVCACHE_SPACE=1",
      "-e",
      "OMP_NUM_THREADS=2",
      "-e",
      // Otherwise a hard kill loses everything the server had not flushed.
      "PYTHONUNBUFFERED=1",
    ],
    args: () => [
      CPU_WEIGHTS,
      "--served-model-name",
      process.env.GATEWAY_REAL_RUNTIME_MODEL ?? CPU_MODEL,
      "--host",
      "0.0.0.0",
      "--port",
      "8080",
      "--dtype",
      "float32",
      "--max-model-len",
      "2048",
      "--max-num-seqs",
      "4",
      "--enforce-eager",
      "--scheduling-policy",
      "priority",
      "--enable-prompt-tokens-details",
      "--disable-uvicorn-access-log",
    ],
  },
  // Built from product/inference/runtimes/kev/Dockerfile.cpu, which runs the adapter
  // we actually deploy. Upstream's own server reports serialized answer tokens as
  // output and omits cached input, both of which the gateway rejects by design.
  kev: {
    image: KEV_CPU_IMAGE,
    model: process.env.GATEWAY_REAL_KEV_MODEL ?? "jaredpalmer/kev-0.5b",
    ready: "/health",
    docker: async (port) => ["-p", `127.0.0.1:${port}:8000`],
    args: () => [],
  },
};

// Weights are baked into the images, so this covers engine start only.
const RUNTIME_READY_TIMEOUT_MS = 240_000;

const startRealRuntime = async (
  kind: RuntimeKind,
  owner: string,
): Promise<{ runtime: RealRuntime; container?: string }> => {
  const spec = REAL_RUNTIMES[kind];
  const existing =
    process.env[`GATEWAY_REAL_RUNTIME_URL_${kind.toUpperCase()}`];
  if (existing) {
    return {
      runtime: { baseUrl: existing.replace(/\/$/, ""), model: spec.model },
    };
  }
  const container = `gateway-runtime-${kind}-${owner.split("-").at(-1)}`;
  const port = await freePort();
  await docker(
    "run",
    "-d",
    "--name",
    container,
    "--label",
    `gateway-contract=${owner}`,
    ...(await spec.docker(port)),
    spec.image,
    ...spec.args(port),
  );
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    await eventually(
      async () => {
        // A container that has already exited will never become ready, and its
        // logs say why. Without this the poll just times out with `fetch failed`.
        const running = await docker(
          "inspect",
          "--format",
          "{{.State.Running}}",
          container,
        );
        if (running !== "true") throw new Fatal("the runtime container exited");
        return (
          await fetch(`${baseUrl}${spec.ready}`, {
            signal: AbortSignal.timeout(2000),
          })
        ).ok;
      },
      RUNTIME_READY_TIMEOUT_MS,
      `${kind} real runtime readiness`,
    );
  } catch (error) {
    // An out-of-memory kill leaves no output at all, because Python block-buffers
    // when its stdout is not a terminal. The exit state is what names that case.
    const state = await docker(
      "inspect",
      "--format",
      "exit={{.State.ExitCode}} oomKilled={{.State.OOMKilled}} error={{.State.Error}}",
      container,
    ).catch(() => "(container state unavailable)");
    const logs = await dockerOutput("logs", "--tail", "120", container).catch(
      () => "(container logs unavailable)",
    );
    throw new Error(
      `${String(error)}\n--- ${kind} container ${state} ---\n${logs || "(no output)"}`,
    );
  }
  return { runtime: { baseUrl, model: spec.model }, container };
};

const freePort = (): Promise<number> =>
  new Promise((resolve, reject) => {
    const probe = createServer();
    probe.on("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const { port } = probe.address() as { port: number };
      probe.close(() => resolve(port));
    });
  });

const available = (port: number): Promise<boolean> =>
  new Promise((resolve) => {
    const probe = createServer();
    probe.on("error", () => resolve(false));
    probe.listen(port, "127.0.0.1", () => probe.close(() => resolve(true)));
  });

/**
 * A cluster node also needs its bus port, which is always the data port plus 10,000.
 * The ephemeral range sits above that ceiling on some hosts, so pick explicitly.
 */
const clusterPort = async (): Promise<number> => {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    const port = 20_000 + Math.floor(Math.random() * 25_000);
    if ((await available(port)) && (await available(port + 10_000)))
      return port;
  }
  throw new Error("could not find a free cluster port pair");
};

/** Thrown by a check that can never succeed, so polling stops rather than waits out. */
export class Fatal extends Error {}

export const eventually = async <T>(
  check: () => T | Promise<T>,
  timeoutMs = 5000,
  description = "condition did not become true before deadline",
): Promise<NonNullable<T>> => {
  const deadline = Date.now() + timeoutMs;
  let last: unknown;
  while (Date.now() < deadline) {
    try {
      const result = await check();
      if (result) return result as NonNullable<T>;
    } catch (error) {
      if (error instanceof Fatal) throw error;
      last = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new Error(last ? `${description}: ${String(last)}` : description);
};

export default async (project: TestProject) => {
  if (!existsSync(BINARY)) {
    throw new Error(
      `Build the gateway binary before running integration tests: ${BINARY}`,
    );
  }
  const name = `gateway-contract-${crypto.randomUUID().replaceAll("-", "")}`;
  const redisPort = await clusterPort();
  const gatewayPort = await freePort();
  const runtimeToken = crypto.randomUUID().replaceAll("-", "");
  const logDir = await mkdtemp(join(tmpdir(), "gateway-integration-"));
  const logPath = join(logDir, "gateway.log");
  DOCKER = ["--host", await dockerHost()];

  let gateway: ChildProcess | undefined;
  const gateways: ChildProcess[] = [];
  let created = false;
  const runtimeContainers: string[] = [];
  const client = createClient({
    url: `redis://127.0.0.1:${redisPort}`,
    socket: { reconnectStrategy: false },
  });

  const teardown = async () => {
    for (const child of gateways.filter((c) => c !== gateway)) {
      if (child.exitCode === null) child.kill("SIGKILL");
    }
    if (gateway && gateway.exitCode === null) {
      gateway.kill("SIGTERM");
      // The gateway drains on SIGTERM; nothing is in flight here, so cut it short.
      const exited = new Promise<boolean>((resolve) =>
        gateway!.once("exit", () => resolve(true)),
      );
      const stopped = await Promise.race([
        exited,
        new Promise<boolean>((resolve) =>
          setTimeout(() => resolve(false), 5000),
        ),
      ]);
      if (!stopped) {
        gateway.kill("SIGKILL");
        await exited;
      }
    }
    if (client.isOpen) await client.close();
    if (created) await removeOwned(name, "gateway-contract", name);
    for (const container of runtimeContainers) {
      await removeOwned(container, "gateway-contract", name);
    }
    await rm(logDir, { recursive: true, force: true });
  };

  try {
    // Single-node cluster on a random port; never attach to an existing database.
    await docker(
      "run",
      "-d",
      "--name",
      name,
      "--label",
      `gateway-contract=${name}`,
      "--network",
      "host",
      "--tmpfs",
      "/data:rw,nosuid,nodev,size=64m",
      IMAGE,
      "valkey-server",
      "--bind",
      "127.0.0.1",
      "--port",
      String(redisPort),
      "--save",
      "",
      "--appendonly",
      "no",
      "--cluster-enabled",
      "yes",
      "--cluster-config-file",
      "/data/nodes.conf",
      "--cluster-announce-ip",
      "127.0.0.1",
      "--cluster-announce-port",
      String(redisPort),
      "--cluster-announce-bus-port",
      String(redisPort + 10_000),
    );
    created = true;

    await eventually(
      async () => {
        if (!client.isOpen) await client.connect();
        return (await client.ping()) === "PONG";
      },
      10_000,
      "valkey did not accept connections",
    );

    const info = await docker(
      "exec",
      name,
      "valkey-cli",
      "-p",
      String(redisPort),
      "INFO",
      "server",
    );
    const runId = /run_id:(\S+)/.exec(await client.info("server"))?.[1];
    if (!runId || !info.includes(`run_id:${runId}`)) {
      throw new Error(
        "connected to a Valkey server other than this run's container",
      );
    }
    if ((await client.dbSize()) !== 0)
      throw new Error("disposable serving state is not empty");

    await client.sendCommand(["CLUSTER", "ADDSLOTSRANGE", "0", "16383"]);
    await eventually(
      async () =>
        String(await client.sendCommand(["CLUSTER", "INFO"])).includes(
          "cluster_state:ok",
        ),
      10_000,
      "cluster did not reach a serving state",
    );

    const startGateway = async (
      port: number,
      generationTimeoutSeconds: string,
      file: string,
    ): Promise<ChildProcess> => {
      const log = openSync(file, "w");
      const child = spawn(BINARY, {
        stdio: ["ignore", log, log],
        env: {
          PATH: process.env.PATH ?? "",
          VALKEY_URL: `redis://127.0.0.1:${redisPort}`,
          GATEWAY_BIND_ADDRESS: `127.0.0.1:${port}`,
          GATEWAY_SETTLEMENT_BACKLOG_LIMIT: "10000",
          GATEWAY_GENERATION_TIMEOUT_SECONDS: generationTimeoutSeconds,
          GATEWAY_PREPAID_ORGANIZATION_CONCURRENCY_CAP: "2",
          GATEWAY_BROWSER_ORIGINS: "https://console.example.test",
          SGLANG_API_KEY: runtimeToken,
          RUST_LOG: "warn",
          AWS_EC2_METADATA_DISABLED: "true",
          HF_HUB_OFFLINE: "1",
        },
      });
      closeSync(log);
      gateways.push(child);
      const client = new Client(`http://127.0.0.1:${port}`);
      await eventually(
        async () => {
          if (child.exitCode !== null)
            throw new Fatal("gateway exited before readiness");
          return (await client.get("/health/ready")).status === 200;
        },
        10_000,
        "gateway readiness",
      );
      return child;
    };

    gateway = await startGateway(gatewayPort, "3", logPath);

    const gatewayUrl = `http://127.0.0.1:${gatewayPort}`;
    const http = new Client(gatewayUrl);
    await eventually(
      async () => {
        if (gateway!.exitCode !== null)
          throw new Error("gateway exited before readiness");
        return (await http.get("/health/ready")).status === 200;
      },
      10_000,
      "gateway did not become ready",
    );

    // GATEWAY_REAL_RUNTIME names which real runtimes to start, e.g. "vllm" or
    // "vllm,kev". Anything not named stays synthetic and its fidelity tests skip.
    const enabled = (process.env.GATEWAY_REAL_RUNTIME ?? "")
      .split(",")
      .map((kind) => kind.trim())
      .filter(Boolean) as RuntimeKind[];
    const realRuntimes: RealRuntimes = {};
    for (const kind of enabled) {
      if (!(kind in REAL_RUNTIMES)) {
        throw new Error(`Unknown real runtime "${kind}"; expected vllm or kev`);
      }
      const started = await startRealRuntime(kind, name);
      realRuntimes[kind] = started.runtime;
      if (started.container) runtimeContainers.push(started.container);
    }
    const patientGatewayUrl = enabled.length
      ? await (async () => {
          const port = await freePort();
          await startGateway(port, "120", join(logDir, "gateway-patient.log"));
          return `http://127.0.0.1:${port}`;
        })()
      : null;

    project.provide("realRuntimes", realRuntimes);
    project.provide("stack", {
      redisUrl: `redis://127.0.0.1:${redisPort}`,
      gatewayUrl,
      patientGatewayUrl,
      runtimeToken,
      logPath,
    });
  } catch (error) {
    await teardown();
    throw error;
  }

  return teardown;
};
