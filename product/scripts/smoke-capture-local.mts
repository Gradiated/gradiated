import assert from "node:assert/strict";
import { execFile, spawn } from "node:child_process";
import { createHash, randomBytes, randomUUID } from "node:crypto";
import { once } from "node:events";
import { closeSync, openSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm } from "node:fs/promises";
import { createServer } from "node:http";
import { join, resolve } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { promisify } from "node:util";
import * as zlib from "node:zlib";

import pg from "pg";
import { parse } from "yaml";

import { freePort } from "../services/gateway/test/integration/ports.js";

const product = resolve(import.meta.dirname, "..");
const config = parse(await readFile(join(product, "mprocs.yaml"), "utf8"), {
  merge: true,
}) as { procs: Record<string, { env: Record<string, string> }> };
const collectorEnv = config.procs.collector!.env;
const proxyEnv = config.procs.proxy!.env;
const bucket = collectorEnv.COLLECTOR_BUCKET!;
const endpoint = collectorEnv.AWS_ENDPOINT_URL_S3!;
const local = (url: string) => {
  assert(
    ["127.0.0.1", "localhost", "[::1]"].includes(new URL(url).hostname),
    "Smoke tests require local endpoints",
  );
};
for (const url of [
  endpoint,
  proxyEnv.DATABASE_URL!,
  proxyEnv.PROXY_COLLECTOR_URL!,
  proxyEnv.PROXY_GATEWAY_ORIGIN!,
])
  local(url);

const runtime = resolve(product, "../.agents/runtime");
await mkdir(runtime, { recursive: true });
const directory = await mkdtemp(join(runtime, "capture-smoke-"));
const execute = promisify(execFile);
const aws = async (...args: string[]) => {
  const result = await execute(
    "mise",
    [
      "exec",
      "--",
      "env",
      "-u",
      "AWS_PROFILE",
      "-u",
      "AWS_DEFAULT_PROFILE",
      "aws",
      "--endpoint-url",
      endpoint,
      "--no-cli-pager",
      "s3api",
      ...args,
    ],
    {
      cwd: product,
      env: {
        ...process.env,
        ...collectorEnv,
        AWS_EC2_METADATA_DISABLED: "true",
      },
      timeout: 15_000,
      maxBuffer: 4 * 1024 * 1024,
    },
  );
  return result.stdout.trim()
    ? (JSON.parse(result.stdout) as Record<string, unknown>)
    : {};
};
const waitFor = async (check: () => Promise<boolean>, description: string) => {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (await check()) return;
    await sleep(250);
  }
  throw new Error(`Timed out: ${description}`);
};
const healthy = async (url: string) => {
  const response = await fetch(url, {
    signal: AbortSignal.timeout(2_000),
  }).catch(() => null);
  return response?.ok ?? false;
};

await waitFor(
  () => healthy(`http://${collectorEnv.COLLECTOR_ADMIN_ADDRESS}/health/ready`),
  "start the collector with pnpm dev",
);
await aws("head-bucket", "--bucket", bucket);

const organization = randomUUID();
const workspace = randomUUID();
const secret = `grad_${randomBytes(32).toString("hex")}`;
const task = "local-capture-smoke";
const prefix = `v1/ws=${workspace}/`;
const db = new pg.Client({ connectionString: proxyEnv.DATABASE_URL });
const provider = createServer(async (request, response) => {
  for await (const _chunk of request) {
    /* drain the synthetic request */
  }
  assert.equal(request.headers["x-gradiated-api-key"], undefined);
  response.writeHead(200, { "content-type": "text/event-stream" });
  response.end(
    'data: {"id":"synthetic","choices":[{"index":0,"delta":{"role":"assistant","content":"Local capture works"},"finish_reason":null}]}\n\ndata: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":4,"total_tokens":7}}\n\ndata: [DONE]\n\n',
  );
});
provider.listen(0, "127.0.0.1");
await once(provider, "listening");
const address = provider.address();
assert(address && typeof address !== "string");
const providerUrl = `http://127.0.0.1:${address.port}`;
const port = await freePort();
const adminPort = await freePort();
const log = openSync(join(directory, "proxy.log"), "w");
const proxy = spawn(
  join(product, "services/proxy/target/debug/gradiated-proxy"),
  [],
  {
    cwd: product,
    env: {
      PATH: process.env.PATH,
      ...proxyEnv,
      PROXY_BIND_ADDRESS: `127.0.0.1:${port}`,
      PROXY_ADMIN_ADDRESS: `127.0.0.1:${adminPort}`,
      PROXY_OPENAI_ORIGIN: providerUrl,
      PROXY_ANTHROPIC_ORIGIN: providerUrl,
      RUST_LOG: "info",
    },
    stdio: ["ignore", log, log],
  },
);
closeSync(log);
const proxyExit = new Promise<void>((resolve, reject) => {
  proxy.once("error", reject);
  proxy.once("exit", () => resolve());
});
// The startup probe below reports a missing binary without an unhandled rejection.
void proxyExit.catch(() => {});

try {
  await db.connect();
  await db.query(
    "insert into organizations (id, kind, name, status) values ($1, 'customer', 'Local capture smoke', 'active')",
    [organization],
  );
  await db.query(
    "insert into workspaces (id, organization_id, name, is_default, trace_capture_enabled) values ($1, $2, 'Local capture smoke', false, true)",
    [workspace, organization],
  );
  await db.query(
    "insert into api_keys (id, organization_id, workspace_id, name, digest) values ($1, $2, $3, 'Local capture smoke', $4)",
    [
      randomUUID(),
      organization,
      workspace,
      createHash("sha256").update(secret).digest(),
    ],
  );
  await db.query(
    "insert into billing_accounts (organization_id, mode, balance) values ($1, 'prepaid', 1000000000)",
    [organization],
  );
  const catalog = await fetch(
    `http://${proxyEnv.PROXY_BIND_ADDRESS}/v1/models`,
    {
      headers: { authorization: `Bearer ${secret}` },
      signal: AbortSignal.timeout(5_000),
    },
  );
  assert.equal(
    catalog.status,
    200,
    "The running dev proxy must forward hosted catalog requests to the gateway",
  );

  await waitFor(
    () => healthy(`http://127.0.0.1:${adminPort}/health/ready`),
    "temporary proxy readiness",
  );

  const response = await fetch(`http://127.0.0.1:${port}/v1/chat/completions`, {
    method: "POST",
    headers: {
      authorization: "Bearer sk-proj-local-synthetic-provider",
      "x-gradiated-api-key": secret,
      "x-gradiated-task": task,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: "gpt-local-synthetic",
      messages: [{ role: "user", content: "Synthetic local smoke" }],
      stream: true,
    }),
    signal: AbortSignal.timeout(5_000),
  });
  assert.equal(response.status, 200);
  assert.match(await response.text(), /Local capture works/);
  const generation = response.headers.get("x-gradiated-generation-id");
  assert(generation);

  let manifestKey: string | undefined;
  await waitFor(async () => {
    const listed = await aws(
      "list-objects-v2",
      "--bucket",
      bucket,
      "--prefix",
      prefix,
    );
    manifestKey = (listed.Contents as { Key: string }[] | undefined)?.find(
      (row) => row.Key.endsWith(".manifest.json"),
    )?.Key;
    return Boolean(manifestKey);
  }, "captured generation in SeaweedFS");
  const manifestPath = join(directory, "manifest.json");
  await aws(
    "get-object",
    "--bucket",
    bucket,
    "--key",
    manifestKey!,
    manifestPath,
  );
  const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as {
    generations: {
      generation_id: string;
      offset: number;
      length: number;
      trainable: boolean;
    }[];
  };
  const row = manifest.generations.find(
    (row) => row.generation_id === generation,
  );
  assert(row);
  assert.equal(row.trainable, false);
  const dataKey = manifestKey!.replace(/\.manifest\.json$/, ".jsonl.zst");
  const dataPath = join(directory, "frame.zst");
  await aws(
    "get-object",
    "--bucket",
    bucket,
    "--key",
    dataKey,
    "--range",
    `bytes=${row.offset}-${row.offset + row.length - 1}`,
    dataPath,
  );
  const decompress = (
    zlib as unknown as { zstdDecompressSync: (data: Buffer) => Buffer }
  ).zstdDecompressSync;
  const record = JSON.parse(decompress(await readFile(dataPath)).toString());
  assert.equal(record.generation_id, generation);
  assert.equal(
    record.raw.response.choices[0].message.content,
    "Local capture works",
  );
  assert.equal(record.raw.request.messages[0].content, "Synthetic local smoke");
  const tags = await aws(
    "get-object-tagging",
    "--bucket",
    bucket,
    "--key",
    dataKey,
  );
  assert.deepEqual(
    new Set(
      (tags.TagSet as { Key: string; Value: string }[]).map(
        (tag) => `${tag.Key}=${tag.Value}`,
      ),
    ),
    new Set(["retention=90d", "trainable=false"]),
  );
  console.log(
    "PASS: dev proxy → gateway catalog; proxy streaming relay → native collector → S3 batch/manifest → tagged range read and zstd decode",
  );
} finally {
  proxy.kill("SIGTERM");
  await Promise.race([proxyExit.catch(() => {}), sleep(5_000)]);
  if (proxy.exitCode === null && proxy.signalCode === null) {
    proxy.kill("SIGKILL");
    await proxyExit.catch(() => {});
  }
  provider.closeAllConnections();
  await new Promise<void>((resolve) => provider.close(() => resolve()));
  try {
    const listed = await aws(
      "list-objects-v2",
      "--bucket",
      bucket,
      "--prefix",
      prefix,
    );
    for (const { Key } of (listed.Contents as { Key: string }[] | undefined) ??
      []) {
      await aws("delete-object", "--bucket", bucket, "--key", Key);
    }
    await db.query("delete from organizations where id = $1", [organization]);
  } finally {
    await db.end();
  }
  await rm(directory, { recursive: true, force: true });
}
