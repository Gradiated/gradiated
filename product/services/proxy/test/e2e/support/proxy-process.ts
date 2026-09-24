import { spawn, type ChildProcess } from "node:child_process";
import { closeSync, mkdirSync, openSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  eventually,
  Fatal,
  within,
} from "../../../../gateway/test/integration/eventually.js";
import type { Exit } from "../../../../gateway/test/integration/gateway-process.js";
import { Client } from "../../../../gateway/test/integration/http-client.js";
import { freePort } from "../../../../gateway/test/integration/ports.js";

const HERE = fileURLToPath(new URL(".", import.meta.url));
export const BINARY = join(HERE, "../../../target/debug/gradiated-proxy");
const LOG_DIR = join(HERE, "../../../../../../.agents/runtime/proxy-e2e");

/** Short enough that a test can watch a key change or the catalog refresh. */
export const IDENTITY_FRESH_SECONDS = 1;
export const CATALOG_REFRESH_SECONDS = 1;

export interface ProxyOptions {
  readonly gatewayUrl: string;
  readonly databaseUrl: string;
  readonly providerUrl: string;
  readonly logName: string;
  readonly env: Record<string, string>;
}

/** The real proxy binary with an explicit environment and loopback-only upstreams. */
export class ProxyProcess {
  readonly exited: Promise<Exit>;
  readonly client: Client;
  readonly admin: Client;

  private constructor(
    readonly child: ChildProcess,
    readonly url: string,
    readonly adminUrl: string,
    readonly logPath: string,
  ) {
    this.exited = new Promise((resolve) =>
      child.once("exit", (code, signal) => resolve({ code, signal })),
    );
    this.client = new Client(url);
    this.admin = new Client(adminUrl);
  }

  static async spawn(options: ProxyOptions): Promise<ProxyProcess> {
    mkdirSync(LOG_DIR, { recursive: true });
    const [port, adminPort] = [await freePort(), await freePort()];
    const logPath = join(LOG_DIR, `${options.logName}.log`);
    const log = openSync(logPath, "w");

    const child = spawn(BINARY, {
      stdio: ["ignore", log, log],
      env: {
        PATH: process.env.PATH ?? "",
        PROXY_BIND_ADDRESS: `127.0.0.1:${port}`,
        PROXY_ADMIN_ADDRESS: `127.0.0.1:${adminPort}`,
        PROXY_GATEWAY_ORIGIN: options.gatewayUrl,
        PROXY_ANTHROPIC_ORIGIN: options.providerUrl,
        PROXY_OPENAI_ORIGIN: options.providerUrl,
        DATABASE_URL: options.databaseUrl,
        PROXY_IDENTITY_FRESH_SECONDS: String(IDENTITY_FRESH_SECONDS),
        PROXY_CATALOG_REFRESH_SECONDS: String(CATALOG_REFRESH_SECONDS),
        PROXY_GATEWAY_HEADER_SECONDS: "10",
        PROXY_PROVIDER_HEADER_SECONDS: "10",
        PROXY_IDLE_SECONDS: "10",
        PROXY_TOTAL_SECONDS: "30",
        RUST_LOG: "info",
        ...options.env,
      },
    });
    closeSync(log);

    return new ProxyProcess(
      child,
      `http://127.0.0.1:${port}`,
      `http://127.0.0.1:${adminPort}`,
      logPath,
    );
  }

  static async start(options: ProxyOptions): Promise<ProxyProcess> {
    const proxy = await ProxyProcess.spawn(options);

    try {
      await proxy.ready();
    } catch (error) {
      await proxy.stop();
      throw error;
    }

    return proxy;
  }

  get running(): boolean {
    return this.child.exitCode === null && this.child.signalCode === null;
  }

  readiness(): Promise<number> {
    return this.admin.get("/health/ready").then((response) => response.status);
  }

  async ready(timeoutMs = 10_000): Promise<void> {
    await eventually(
      async () => {
        if (!this.running) throw new Fatal("proxy exited before readiness");
        return (await this.readiness()) === 200;
      },
      timeoutMs,
      "proxy readiness",
    );
  }

  /** Counter values from the admin metrics endpoint, keyed by series. */
  async metrics(): Promise<Map<string, number>> {
    const response = await this.admin.get("/metrics");
    const series = new Map<string, number>();
    for (const line of response.text.split("\n")) {
      if (line.startsWith("#") || line.trim() === "") continue;

      const split = line.lastIndexOf(" ");
      series.set(line.slice(0, split), Number(line.slice(split + 1)));
    }

    return series;
  }

  /** The sum of every series of one metric, optionally only those with one label value. */
  async count(metric: string, label?: string): Promise<number> {
    let total = 0;
    for (const [series, value] of await this.metrics()) {
      const name = series.split("{")[0];
      if (name === metric && (label === undefined || series.includes(label)))
        total += value;
    }

    return total;
  }

  /** Responses the proxy completed for one destination, across every status. */
  responses(
    destination: "gateway" | "anthropic" | "openai" | "local",
  ): Promise<number> {
    return this.count("proxy_requests_total", `destination="${destination}"`);
  }

  /** Waits for a hosted catalog load that started after `since`, a `Date.now()` value. */
  async catalogRefreshedAfter(since: number): Promise<void> {
    await eventually(
      async () => {
        const age = (await this.metrics()).get("proxy_catalog_age_seconds");
        return age !== undefined && Date.now() - age * 1000 > since;
      },
      CATALOG_REFRESH_SECONDS * 1000 + 5000,
      "the hosted catalog did not refresh",
    );
  }

  log(): Promise<string> {
    return readFile(this.logPath, "utf8");
  }

  signal(signal: NodeJS.Signals): void {
    this.child.kill(signal);
  }

  async exit(timeoutMs = 5000): Promise<Exit | undefined> {
    const outcome = await within(this.exited, timeoutMs);

    return outcome.settled ? outcome.value : undefined;
  }

  async stop(): Promise<void> {
    if (!this.running) return;

    this.child.kill("SIGKILL");
    await this.exited;
  }
}
