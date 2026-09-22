/**
 * Exercise the real gateway with disposable local serving state and real Kev replicas.
 *
 * Run: pnpm e2e:kev (configuration via environment; see inference/runtimes/kev/E2E.md)
 */
import { spawn, type ChildProcess } from "node:child_process";
import { execFile } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import {
  closeSync,
  existsSync,
  openSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { createClient } from "redis";

const run = promisify(execFile);

const ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "../..");
const MODEL = "jaredpalmer/kev-9b";
const IMAGE = "valkey/valkey:8.1.9-alpine3.24";
const VALKEY_PORT = 16_379;
const INITIAL_BALANCE = 1_000_000_000_000;

// Keep insertion order identical to ModelDeploymentRelease's serde serialization.
// Both runtime_model_name and tokenizer_mode are None and must be OMITTED.
const RELEASE = {
  schema_version: 1,
  runtime_revision: "kev-f0ae8fb9-systemone-v1",
  protocol: "system_one",
  model_path: MODEL,
  model_revision: "2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c",
  tokenizer_path: "Qwen/Qwen3.5-9B-Base",
  tokenizer_revision: "68c46c4b3498877f3ef123c856ecfde50c39f404",
};

const encoded = (value: unknown): string => JSON.stringify(value);
const RELEASE_DIGEST = `sha256:${createHash("sha256").update(encoded(RELEASE)).digest("hex")}`;

const require_ = (condition: unknown, message: string): void => {
  if (!condition) throw new Error(message);
};

/** Do not inherit production gateway, IAM, proxy, telemetry, SDK or runtime auth. */
const localEnvironment = (): Record<string, string> => {
  const names = [
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
  ];
  return Object.fromEntries(
    names
      .filter((name) => process.env[name])
      .map((name) => [name, process.env[name]!]),
  );
};

let DOCKER: string[] = [];

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
  require_(
    configured.startsWith("unix://"),
    `Refusing a non-local Docker endpoint: ${configured}`,
  );
  return configured;
};

const docker = async (args: string[], timeoutMs = 30_000): Promise<string> => {
  const { stdout } = await run("docker", [...DOCKER, ...args], {
    timeout: timeoutMs,
    env: localEnvironment(),
  });
  return stdout.trim();
};

/** Bind the exact port to prove it is free; port 0 selects an available one. */
const availablePort = (port: number): Promise<number> =>
  new Promise((resolve, reject) => {
    const probe = createServer();
    probe.on("error", () => reject(new Error(`Port ${port} is not available`)));
    probe.listen(port, "127.0.0.1", () => {
      const { port: bound } = probe.address() as { port: number };
      probe.close(() => resolve(bound));
    });
  });

const waitFor = async (
  check: () => unknown | Promise<unknown>,
  label: string,
  timeoutMs = 60_000,
): Promise<void> => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      if (await check()) return;
    } catch {
      // Keep polling until the deadline.
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Timed out waiting for ${label}`);
};

const measure = (value: number) => ({ value, unit: "token" });
const price = (type: string, cost: number) => ({ type, unit: "token", cost });

interface Deployment {
  id: string;
  status: string;
  provider: string;
  region: string;
  fault_domain: string;
  service_url: string;
  release: typeof RELEASE;
}

const modelProjection = (urls: string[]) => ({
  id: MODEL,
  name: "Kev 9B (isolated E2E)",
  status: "available",
  properties: {
    schema_version: 1,
    description: "Disposable E2E; synthetic nano-USD prices",
    released_at: null,
    hugging_face_id: MODEL,
    quantization: "bf16",
    tokenizer: null,
    input_modalities: [
      {
        type: "text",
        supported_inputs: {
          max_context_length: measure(32_768),
          max_prompt_length: measure(32_768),
        },
        pricing: [price("prompt", 10), price("cached_prompt", 2)],
      },
    ],
    output_modalities: [
      {
        type: "text",
        max_length: measure(1),
        default_length: measure(1),
        streaming: false,
        supported_parameters: {},
        pricing: [price("completion", 0)],
      },
    ],
    passthrough_parameters: {},
    deprecation_date: null,
  },
  deployments: urls.map((url, index): Deployment => ({
    id: randomUUID(),
    status: "available",
    provider: "local",
    region: "local",
    fault_domain: `kev-e2e:${index}`,
    service_url: url,
    release: RELEASE,
  })),
});

type Model = ReturnType<typeof modelProjection>;
type Redis = ReturnType<typeof createClient>;

const seed = async (
  client: Redis,
  model: Model,
  key: string,
): Promise<string> => {
  const [organization, workspace, credential] = [
    randomUUID(),
    randomUUID(),
    randomUUID(),
  ];
  await client.set(
    `credential:${createHash("sha256").update(key).digest("hex")}`,
    encoded({
      api_key_id: credential,
      organization_id: organization,
      workspace_id: workspace,
      expires_at: null,
      revoked_at: null,
    }),
  );
  await client.set(
    `workspace:${workspace}`,
    encoded({
      organization_id: organization,
      workspace_id: workspace,
      archived_at: null,
    }),
  );
  await client.hSet(`account:{settlement-0}:${organization}`, {
    organization_id: organization,
    organization_kind: "customer",
    organization_status: "active",
    billing_mode: "prepaid",
    balance: String(INITIAL_BALANCE),
  });
  await client.set(`model:${MODEL}`, encoded(model));
  await client.sAdd("gateway-model-ids", MODEL);
  return organization;
};

const refreshStatuses = async (client: Redis, model: Model): Promise<void> => {
  const now = new Date().toISOString();
  await client.hSet(
    `deployment-status:{${RELEASE_DIGEST}}`,
    Object.fromEntries(
      model.deployments.map((deployment) => [
        deployment.id,
        encoded({
          schema_version: 1,
          deployment_id: deployment.id,
          runtime_revision: RELEASE.runtime_revision,
          received_at: now,
          healthy: true,
          accepting_requests: true,
          reason_code: null,
        }),
      ]),
    ),
  );
};

const verifySettlements = async (
  client: Redis,
  organization: string,
  ledger: string,
  model: Model,
): Promise<void> => {
  const successes = readFileSync(ledger, "utf8")
    .split("\n")
    .filter(Boolean)
    .map(
      (line) => (JSON.parse(line) as { generation_id: string }).generation_id,
    );
  require_(
    successes.length > 0,
    "No successful SDK HTTP responses were recorded",
  );
  require_(
    successes.length === new Set(successes).size,
    "Duplicate successful generation IDs",
  );

  const rows = await client.xRange(
    "generation-settled:{settlement-0}",
    "-",
    "+",
  );
  const counts = new Map<string, number>();
  for (const row of rows) {
    const id = row.message.generation_id as string;
    counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  require_(
    [...counts.values()].every((count) => count === 1),
    "Duplicate settlement events",
  );

  const succeeded = new Set<string>();
  const deployments = new Set<string>();
  let cached = 0;
  let charge = 0;
  for (const row of rows) {
    const properties = JSON.parse(row.message.properties as string);
    const usage = properties.usage;
    require_(
      properties.organization_id === organization &&
        properties.model_id === MODEL,
      "Settlement identity mismatch",
    );
    require_(
      properties.served_release_digest === RELEASE_DIGEST,
      "Release digest mismatch",
    );
    require_(
      usage.output_tokens === 0 && usage.reasoning_tokens === 0,
      "Decision protocol was charged generated output",
    );
    const expected =
      (usage.input_tokens - usage.cached_input_tokens) * 10 +
      usage.cached_input_tokens * 2;
    require_(usage.charge === expected, "Synthetic pricing mismatch");
    const components = properties.pricing.components as { amount: number }[];
    require_(
      components.reduce((total, item) => total + item.amount, 0) === expected,
      "Pricing components do not match charge",
    );
    charge += usage.charge;
    if (properties.status === "succeeded") {
      succeeded.add(row.message.generation_id as string);
      if (usage.cached_input_tokens > 0) cached += 1;
      if ("deployment_id" in properties)
        deployments.add(properties.deployment_id);
    }
  }
  require_(
    succeeded.size === successes.length &&
      successes.every((id) => succeeded.has(id)),
    "Successful HTTP responses and settlements differ",
  );
  require_(cached > 0, "No successful cached-input settlement");
  require_(
    (await client.zCard(`inflight:{settlement-0}:${organization}`)) === 0,
    "Admission leases remain after suite completion",
  );
  const balance = Number(
    await client.hGet(`account:{settlement-0}:${organization}`, "balance"),
  );
  require_(
    balance === INITIAL_BALANCE - charge,
    "Account debit differs from event charges",
  );
  if (deployments.size > 0) {
    const expectedIds = new Set(model.deployments.map((item) => item.id));
    require_(
      deployments.size === expectedIds.size &&
        [...deployments].every((id) => expectedIds.has(id)),
      "Not all deployments have successful settlement evidence",
    );
  }
  console.log(
    `Verified ${successes.length} successful generations exactly once; ${cached} cached; ` +
      `${charge} nano-USD charged; balance ${balance}.`,
  );
  if (deployments.size === 0) {
    console.log(
      "Deployment coverage skipped: settlement identity has no deployment_id.",
    );
  }
};

const stopProcess = async (child: ChildProcess | undefined): Promise<void> => {
  if (!child || child.exitCode !== null || child.pid === undefined) return;
  const exited = new Promise<boolean>((resolve) =>
    child.once("exit", () => resolve(true)),
  );
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    return;
  }
  const stopped = await Promise.race([
    exited,
    new Promise<boolean>((resolve) => setTimeout(() => resolve(false), 10_000)),
  ]);
  if (!stopped) {
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch {
      return;
    }
    await exited;
  }
};

const redact = (text: string, key: string): string =>
  text.split(key).join("[REDACTED]");

const main = async (): Promise<void> => {
  DOCKER = ["--host", await dockerHost()];
  const binary =
    process.env.KEV_GATEWAY_EXECUTABLE ??
    join(ROOT, "product/services/gateway/target/debug/gradiated-gateway");
  require_(
    existsSync(binary),
    "Build gateway first or set KEV_GATEWAY_EXECUTABLE",
  );
  const harness = join(ROOT, "product/scripts/test-kev-gateway.test.ts");
  require_(existsSync(harness), "SDK harness is missing");

  const urls = (
    process.env.KEV_RUNTIME_URLS ??
    "http://127.0.0.1:18009,http://127.0.0.1:18010"
  )
    .split(",")
    .map((url) => url.trim().replace(/\/$/, ""));
  require_(
    urls.length === 2 && new Set(urls).size === 2,
    "Provide two distinct Kev replica URLs",
  );
  for (const url of urls) {
    const parsed = new URL(url);
    require_(
      parsed.protocol === "http:" &&
        parsed.hostname === "127.0.0.1" &&
        parsed.port !== "" &&
        ["", "/"].includes(parsed.pathname) &&
        parsed.search === "" &&
        parsed.hash === "" &&
        parsed.username === "" &&
        parsed.password === "",
      "Runtime URLs must be plain HTTP 127.0.0.1 SSH forwards",
    );
  }

  await availablePort(VALKEY_PORT);
  await availablePort(VALKEY_PORT + 10_000);
  const gatewayPort = await availablePort(
    Number(process.env.KEV_GATEWAY_PORT ?? "18080"),
  );
  require_(
    ![VALKEY_PORT, VALKEY_PORT + 10_000].includes(gatewayPort),
    "Gateway port conflicts with Valkey",
  );
  const suiteTimeout =
    Number(process.env.KEV_E2E_TIMEOUT_SECONDS ?? "900") * 1000;
  require_(suiteTimeout > 0, "Suite timeout must be positive");

  for (const [index, url] of urls.entries()) {
    await waitFor(
      async () =>
        (await fetch(`${url}/health`, { signal: AbortSignal.timeout(2000) }))
          .status === 200,
      `Kev replica ${index + 1} /health readiness`,
    );
  }
  console.log(
    "Both Kev replicas passed /health readiness; model warmup is a separate prerequisite.",
  );

  const model = modelProjection(urls);
  const key = `grad_${randomUUID().replaceAll("-", "")}${randomUUID().replaceAll("-", "")}`;
  const runId = randomUUID().replaceAll("-", "");
  const container = `kev-gateway-e2e-${runId}`;
  // Explicit /tmp prevents TMPDIR from placing runtime artifacts in the repo.
  const directory = await mkdtemp("/tmp/kev-gateway-e2e-");
  const gatewayLog = join(directory, "gateway.log");
  const suiteLog = join(directory, "suite.log");
  const ledger = join(directory, "responses.jsonl");
  writeFileSync(ledger, "", { mode: 0o600 });

  let gateway: ChildProcess | undefined;
  let suite: ChildProcess | undefined;
  let client: Redis | undefined;
  let refresher: NodeJS.Timeout | undefined;
  const refreshErrors: string[] = [];

  try {
    await docker(
      [
        "create",
        "--name",
        container,
        "--label",
        `kev-e2e=${runId}`,
        "--network",
        "host",
        "--tmpfs",
        "/data:rw,nosuid,nodev,size=64m",
        IMAGE,
        "valkey-server",
        "--bind",
        "127.0.0.1",
        "--port",
        String(VALKEY_PORT),
        "--save",
        "",
        "--appendonly",
        "no",
        "--cluster-enabled",
        "yes",
        "--cluster-config-file",
        "/data/nodes.conf",
        "--cluster-node-timeout",
        "5000",
        "--cluster-announce-ip",
        "127.0.0.1",
        "--cluster-announce-port",
        String(VALKEY_PORT),
        "--cluster-announce-bus-port",
        String(VALKEY_PORT + 10_000),
      ],
      180_000,
    );
    await docker(["start", container]);
    require_(
      (await docker([
        "inspect",
        "--format",
        "{{.State.Running}}",
        container,
      ])) === "true",
      "Disposable Valkey container is not running",
    );

    client = createClient({
      url: `redis://127.0.0.1:${VALKEY_PORT}`,
      socket: { reconnectStrategy: false, connectTimeout: 2000 },
    });
    await waitFor(async () => {
      if (!client!.isOpen) await client!.connect();
      return (await client!.ping()) === "PONG";
    }, "disposable Valkey");

    // Check this very container owns the responding server before any seeding.
    const cli = [
      "exec",
      container,
      "valkey-cli",
      "-h",
      "127.0.0.1",
      "-p",
      String(VALKEY_PORT),
    ];
    const info = await docker([...cli, "INFO", "server"]);
    const runIdLine = /run_id:(\S+)/.exec(await client.info("server"))?.[1];
    require_(
      runIdLine && info.includes(`run_id:${runIdLine}`),
      "Valkey ownership mismatch",
    );
    const clusterInfo = String(await client.sendCommand(["CLUSTER", "INFO"]));
    require_(
      (await client.dbSize()) === 0 &&
        clusterInfo.includes("cluster_slots_assigned:0"),
      "Disposable Valkey must start empty with no slots",
    );
    await docker([...cli, "CLUSTER", "ADDSLOTSRANGE", "0", "16383"]);
    await waitFor(
      async () =>
        String(await client!.sendCommand(["CLUSTER", "INFO"])).includes(
          "cluster_state:ok",
        ),
      "cluster slots",
    );

    const organization = await seed(client, model, key);
    await refreshStatuses(client, model);
    refresher = setInterval(() => {
      void refreshStatuses(client!, model).catch((error) => {
        refreshErrors.push(String(error));
        clearInterval(refresher);
      });
    }, 1000);

    const log = openSync(gatewayLog, "w");
    gateway = spawn(binary, {
      cwd: ROOT,
      detached: true,
      stdio: ["ignore", log, log],
      env: {
        ...localEnvironment(),
        VALKEY_URL: `redis://127.0.0.1:${VALKEY_PORT}`,
        GATEWAY_BIND_ADDRESS: `127.0.0.1:${gatewayPort}`,
        GATEWAY_SETTLEMENT_BACKLOG_LIMIT: "100000",
        RUST_LOG: "warn",
        AWS_EC2_METADATA_DISABLED: "true",
      },
    });
    closeSync(log);
    const base = `http://127.0.0.1:${gatewayPort}`;
    await waitFor(async () => {
      require_(gateway!.exitCode === null, "Gateway exited before readiness");
      return (
        (
          await fetch(`${base}/health/ready`, {
            signal: AbortSignal.timeout(2000),
          })
        ).status === 200
      );
    }, "gateway readiness");

    console.log(
      "Running SDK suite against isolated gateway and two forwarded Kev replicas.",
    );
    const suiteOut = openSync(suiteLog, "w");
    suite = spawn(
      join(ROOT, "product/node_modules/.bin/vitest"),
      ["run", "--config", "scripts/vitest.kev-sdk.config.mts"],
      {
        cwd: join(ROOT, "product"),
        detached: true,
        stdio: ["ignore", suiteOut, suiteOut],
        env: {
          ...localEnvironment(),
          KEV_GATEWAY_API_KEY: key,
          KEV_GATEWAY_BASE_URL: base,
          KEV_GATEWAY_MODEL: MODEL,
          KEV_RUNTIME_URLS: urls.join(","),
          KEV_E2E_RESPONSE_LEDGER: ledger,
          TMPDIR: directory,
        },
      },
    );
    closeSync(suiteOut);

    const deadline = Date.now() + suiteTimeout;
    const code = await new Promise<number>((resolve, reject) => {
      suite!.once("exit", (status) => resolve(status ?? 1));
      const poll = setInterval(() => {
        const failure =
          gateway!.exitCode !== null
            ? "Gateway exited during SDK suite"
            : refreshErrors.length > 0
              ? "Deployment status refresher failed"
              : Date.now() >= deadline
                ? "SDK suite timeout exceeded"
                : undefined;
        if (failure) {
          clearInterval(poll);
          reject(new Error(failure));
        }
      }, 200);
      suite!.once("exit", () => clearInterval(poll));
    });
    process.stdout.write(redact(readFileSync(suiteLog, "utf8"), key));
    require_(code === 0, `SDK suite failed (exit ${code})`);
    require_(refreshErrors.length === 0, "Deployment status refresher failed");

    await waitFor(
      async () =>
        (await client!.zCard(`inflight:{settlement-0}:${organization}`)) === 0,
      "generation finalization",
      30_000,
    );
    await verifySettlements(client, organization, ledger, model);
  } catch (error) {
    if (existsSync(gatewayLog)) {
      console.error(
        redact(readFileSync(gatewayLog, "utf8").slice(-12_000), key),
      );
    }
    throw error;
  } finally {
    clearInterval(refresher);
    await stopProcess(suite);
    await stopProcess(gateway);
    if (client?.isOpen) await client.close();
    // Never remove an unrelated container, even after partial startup failure.
    const owner = await docker([
      "inspect",
      "--format",
      '{{index .Config.Labels "kev-e2e"}}',
      container,
    ]).catch(() => "");
    if (owner === runId)
      await docker(["rm", "-f", "-v", container]).catch(() => "");
    await rm(directory, { recursive: true, force: true });
  }
};

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    console.error(`Kev E2E interrupted by ${signal}`);
    process.exit(1);
  });
}

main().catch((error: unknown) => {
  console.error(
    `Kev E2E failed: ${error instanceof Error ? error.message : String(error)}`,
  );
  process.exit(1);
});
