import { spawn, type ChildProcess } from "node:child_process";
import { closeSync, openSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { eventually, Fatal, within } from "./eventually.js";
import { Client } from "./http-client.js";

const HERE = fileURLToPath(new URL(".", import.meta.url));
export const BINARY = join(HERE, "../../target/debug/gradiated-gateway");
export const GATEWAY_LOG_DIR = join(
  HERE,
  "../../../../../.agents/runtime/gateway-integration",
);

export const RECORD_CACHE_TTL_SECONDS = 1;
export const GENERATION_TIMEOUT_SECONDS = 3;
export const ORGANIZATION_CONCURRENCY_CAP = 2;
export const BROWSER_ORIGIN = "https://console.example.test";

const STOP_TIMEOUT_MS = 5000;

export interface GatewayOptions {
  readonly redisUrl: string;
  readonly databaseUrl: string;
  readonly runtimeToken: string;
  readonly port: number;
  readonly generationTimeoutSeconds: number;
  readonly logName: string;
  readonly settlementBacklogLimit?: number;
  readonly verificationWorkspaceId?: string;
  readonly logLevel?: "warn" | "info";
  readonly leaseFinalizationMarginSeconds?: number;
  readonly expiredLeaseCleanupGraceSeconds?: number;
  readonly openRouter?: { readonly baseUrl: string; readonly apiKey: string };
}

export interface Exit {
  readonly code: number | null;
  readonly signal: NodeJS.Signals | null;
}

/**
 * The real gateway binary with an explicit environment, so no ambient cloud or
 * runtime credential reaches it.
 */
export class GatewayProcess {
  readonly exited: Promise<Exit>;

  private constructor(
    readonly child: ChildProcess,
    readonly url: string,
    readonly logPath: string,
  ) {
    this.exited = new Promise((resolve) =>
      child.once("exit", (code, signal) => resolve({ code, signal })),
    );
  }

  static spawn(options: GatewayOptions): GatewayProcess {
    const logPath = join(GATEWAY_LOG_DIR, `${options.logName}.log`);
    const log = openSync(logPath, "w");
    const child = spawn(BINARY, {
      stdio: ["ignore", log, log],
      env: {
        PATH: process.env.PATH ?? "",
        ...(options.verificationWorkspaceId
          ? {
              GATEWAY_VERIFICATION_WORKSPACE_ID:
                options.verificationWorkspaceId,
            }
          : {}),
        VALKEY_URL: options.redisUrl,
        DATABASE_URL: options.databaseUrl,
        GATEWAY_RECORD_CACHE_TTL_SECONDS: String(RECORD_CACHE_TTL_SECONDS),
        GATEWAY_BIND_ADDRESS: `127.0.0.1:${options.port}`,
        GATEWAY_SETTLEMENT_BACKLOG_LIMIT: String(
          options.settlementBacklogLimit ?? 10_000,
        ),
        GATEWAY_GENERATION_TIMEOUT_SECONDS: String(
          options.generationTimeoutSeconds,
        ),
        GATEWAY_ORGANIZATION_CONCURRENCY_CAP: String(
          ORGANIZATION_CONCURRENCY_CAP,
        ),
        GATEWAY_LEASE_FINALIZATION_MARGIN_SECONDS: String(
          options.leaseFinalizationMarginSeconds ?? 60,
        ),
        GATEWAY_EXPIRED_LEASE_CLEANUP_GRACE_SECONDS: String(
          options.expiredLeaseCleanupGraceSeconds ?? 300,
        ),
        GATEWAY_BROWSER_ORIGINS: BROWSER_ORIGIN,
        SGLANG_API_KEY: options.runtimeToken,
        ...(options.openRouter
          ? {
              OPENROUTER_API_KEY: options.openRouter.apiKey,
              OPENROUTER_BASE_URL: options.openRouter.baseUrl,
            }
          : {}),
        RUST_LOG: options.logLevel ?? "warn",
        AWS_EC2_METADATA_DISABLED: "true",
        HF_HUB_OFFLINE: "1",
      },
    });
    closeSync(log);

    return new GatewayProcess(
      child,
      `http://127.0.0.1:${options.port}`,
      logPath,
    );
  }

  static async start(options: GatewayOptions): Promise<GatewayProcess> {
    const gateway = GatewayProcess.spawn(options);

    try {
      await gateway.ready();
    } catch (error) {
      await gateway.stop();
      throw error;
    }

    return gateway;
  }

  get running(): boolean {
    return this.child.exitCode === null && this.child.signalCode === null;
  }

  async ready(): Promise<void> {
    const client = new Client(this.url);

    await eventually(
      async () => {
        if (!this.running) throw new Fatal("gateway exited before readiness");
        return (await client.get("/health/ready")).status === 200;
      },
      10_000,
      "gateway readiness",
    );
  }

  log(): Promise<string> {
    return readFile(this.logPath, "utf8");
  }

  /** Waits for exit, or resolves undefined when the process outlives the timeout. */
  async exit(timeoutMs = STOP_TIMEOUT_MS): Promise<Exit | undefined> {
    const outcome = await within(this.exited, timeoutMs);

    return outcome.settled ? outcome.value : undefined;
  }

  async stop(): Promise<void> {
    if (!this.running) return;

    this.child.kill("SIGTERM");
    if (await this.exit()) return;

    this.child.kill("SIGKILL");
    await this.exited;
  }
}
