// Every case gets unique models and tenant identities, so files can run in parallel.
// The only runtime substitute is an HTTP server; the gateway is the built binary.
import { createHash } from "node:crypto";

import { Pool } from "pg";
import { createClient } from "redis";
import { afterAll, afterEach, beforeAll, expect, inject } from "vitest";

import { Client, type Response } from "./http-client.js";
import {
  Runtime,
  SYNTHETIC,
  type Plan,
  type RuntimeKind,
  type Upstream,
} from "./mock-runtimes/server.js";
import type { JsonObject, JsonValue } from "./mock-runtimes/profile.js";

export { eventually } from "./global-setup.js";
import { eventually } from "./global-setup.js";

const BALANCE = 1_000_000_000_000;
const SETTLEMENT_STREAM = "generation-settled:{settlement-0}";

type Redis = ReturnType<typeof createClient>;
/** The gateway reads records from here; Valkey only caches them. */
type Database = Pool;

export const encoded = (value: unknown): string => JSON.stringify(value);

export interface Settlement {
  readonly generation: string;
  readonly properties: JsonObject;
}

export class Case {
  readonly organization = crypto.randomUUID();
  readonly workspace = crypto.randomUUID();
  readonly credential = crypto.randomUUID();
  // Gradiated keys are recognised by their prefix; without it the gateway
  // treats the secret as a provider credential and looks for a relay route.
  readonly key = `grad_${crypto.randomUUID().replaceAll("-", "")}`;
  readonly model: string;
  readonly runtimeModel: string;
  readonly headers: Record<string, string>;
  readonly path: string;
  readonly release: JsonObject;
  readonly digest: string;
  readonly deployments: JsonObject[];
  readonly record: JsonObject;
  readonly accountKey: string;
  readonly credentialKey: string;
  readonly credentialRecord: JsonObject;
  readonly workspaceRecord: JsonObject;
  initialBalance = BALANCE;

  private constructor(
    readonly redis: Redis,
    readonly database: Database,
    readonly http: Client,
    readonly kind: RuntimeKind,
    model: string,
    runtimeModel: string,
    readonly runtimes: Runtime[],
  ) {
    this.model = model;
    this.runtimeModel = runtimeModel;
    this.headers = { Authorization: `Bearer ${this.key}` };
    this.path = kind === "kev" ? "/v1/systemone" : "/v1/chat/completions";
    this.release = {
      schema_version: 1,
      runtime_revision: `${kind === "kev" ? "kev-" : "vllm-"}${this.model}`,
      // Field order must match the Rust struct: the release JSON is hashed.
      ...(kind === "kev" ? { protocol: "system_one" } : {}),
      model_path: this.model,
      model_revision: "synthetic-v1",
      runtime_model_name: this.runtimeModel,
      tokenizer_path: "unused/chat-owned",
      tokenizer_revision: "synthetic-v1",
    };
    this.digest = `sha256:${createHash("sha256").update(encoded(this.release)).digest("hex")}`;
    this.deployments = runtimes.map((runtime, index) => ({
      id: crypto.randomUUID(),
      status: "available",
      provider: "local",
      region: "local",
      fault_domain: String(index),
      service_url: runtime.url,
      release: this.release,
    }));
    this.record = {
      id: this.model,
      name: `Synthetic ${kind}`,
      status: "available",
      deployments: this.deployments,
      properties: {
        schema_version: 1,
        description: "Synthetic contract tests",
        released_at: "2026-01-01T00:00:00Z",
        hugging_face_id: null,
        quantization: "bf16",
        tokenizer: null,
        input_modalities: [
          {
            type: "text",
            supported_inputs: {
              max_context_length: { value: 8192, unit: "token" },
              max_prompt_length: { value: 4096, unit: "token" },
            },
            pricing: [
              { type: "prompt", unit: "token", cost: 10 },
              { type: "cached_prompt", unit: "token", cost: 2 },
            ],
          },
        ],
        output_modalities: [
          {
            type: "text",
            max_length: { value: 256, unit: "token" },
            default_length: { value: 16, unit: "token" },
            streaming: kind === "vllm",
            supported_parameters: {
              temperature: { type: "range", min: 0, max: 2 },
              tools: { type: "unknown" },
              tool_choice: { type: "unknown" },
            },
            pricing: [
              {
                type: "completion",
                unit: "token",
                cost: kind === "kev" ? 0 : 20,
              },
            ],
          },
        ],
        passthrough_parameters: {},
        deprecation_date: null,
      },
    };
    this.accountKey = `account:{settlement-0}:${this.organization}`;
    this.credentialKey = `credential:${createHash("sha256").update(this.key).digest("hex")}`;
    this.credentialRecord = {
      api_key_id: this.credential,
      organization_id: this.organization,
      workspace_id: this.workspace,
      expires_at: null,
      revoked_at: null,
    };
    this.workspaceRecord = {
      organization_id: this.organization,
      workspace_id: this.workspace,
      archived_at: null,
    };
  }

  static async create(
    redis: Redis,
    database: Database,
    http: Client,
    token: string,
    kind: RuntimeKind,
    options: CaseOptions,
  ): Promise<Case> {
    const replicas = options.replicas ?? 1;
    const upstream = options.upstream ?? SYNTHETIC;
    const model = `test/${kind}-${crypto.randomUUID().replaceAll("-", "")}`;
    // A proxied case must advertise the model id the real runtime actually serves,
    // so the gateway's private-name substitution produces a request it will accept.
    const runtimeModel = options.runtimeModel ?? `private/${model}`;
    const runtimes: Runtime[] = [];
    for (let index = 0; index < replicas; index += 1) {
      runtimes.push(await Runtime.start(kind, runtimeModel, token, upstream));
    }
    const instance = new Case(
      redis,
      database,
      http,
      kind,
      model,
      runtimeModel,
      runtimes,
    );
    // The tenant exists in PostgreSQL. The gateway caches what it reads, so no
    // test seeds Valkey: that would hide a query this suite is here to exercise.
    await database.query(
      `insert into organizations (id, kind, name, status)
       values ($1, 'customer', $2, 'active')`,
      [instance.organization, `case-${instance.organization}`],
    );
    await database.query(
      `insert into billing_accounts (organization_id, mode, balance)
       values ($1, 'prepaid', $2)`,
      [instance.organization, String(BALANCE)],
    );
    await database.query(
      `insert into workspaces (id, organization_id, name, is_default)
       values ($1, $2, 'Default', true)`,
      [instance.workspace, instance.organization],
    );
    await database.query(
      `insert into api_keys (id, organization_id, workspace_id, name, digest)
       values ($1, $2, $3, 'integration', $4)`,
      [
        instance.credential,
        instance.organization,
        instance.workspace,
        createHash("sha256").update(instance.key).digest(),
      ],
    );
    await instance.publish();
    await instance.status();
    return instance;
  }

  /**
   * Changes the tenant's authoritative rows and drops the cached copies, so the
   * next request sees the change without waiting for a record lifetime to elapse.
   */
  async setTenant(changes: {
    organizationStatus?: "active" | "suspended";
    billingMode?: "prepaid" | "invoiced";
    balance?: number;
    workspaceArchived?: boolean;
  }): Promise<void> {
    if (changes.organizationStatus) {
      await this.database.query(
        `update organizations set status = $2, updated_at = now() where id = $1`,
        [this.organization, changes.organizationStatus],
      );
    }
    if (changes.billingMode || changes.balance !== undefined) {
      await this.database.query(
        `update billing_accounts
         set mode = coalesce($2, mode), balance = coalesce($3, balance), updated_at = now()
         where organization_id = $1`,
        [
          this.organization,
          changes.billingMode ?? null,
          changes.balance === undefined ? null : String(changes.balance),
        ],
      );
    }
    if (changes.workspaceArchived !== undefined) {
      // The schema forbids archiving a default workspace, so it stops being the
      // default at the same time. The projection this replaced enforced neither.
      await this.database.query(
        `update workspaces
         set archived_at = $2, is_default = $3, updated_at = now()
         where id = $1`,
        [
          this.workspace,
          changes.workspaceArchived ? new Date() : null,
          !changes.workspaceArchived,
        ],
      );
    }
    // The account hash holds the operational balance, so removing it makes the
    // gateway seed it again from these rows.
    await this.redis.del(this.accountKey);
    await this.redis.del(`workspace:${this.workspace}`);
  }

  /** Writes the catalog row, then drops the cached copy so the change is visible now. */
  async publish(): Promise<void> {
    const properties = this.record.properties as JsonObject;
    const deployments = this.record.deployments as JsonObject[];
    await this.database.query(
      `insert into models (id, name, status, properties)
       values ($1, $2, $3, $4)
       on conflict (id) do update
       set name = excluded.name, status = excluded.status,
           properties = excluded.properties, updated_at = now()`,
      [
        this.model,
        this.record.name as string,
        this.record.status as string,
        JSON.stringify(properties),
      ],
    );
    await this.database.query(
      `delete from model_deployments where model_id = $1`,
      [this.model],
    );
    for (const deployment of deployments) {
      await this.database.query(
        `insert into model_deployments
           (id, model_id, status, provider, region, fault_domain, service_url, release)
         values ($1, $2, $3, $4, $5, $6, $7, $8)`,
        [
          deployment.id as string,
          this.model,
          deployment.status as string,
          deployment.provider as string,
          deployment.region as string,
          deployment.fault_domain as string,
          deployment.service_url as string,
          JSON.stringify(deployment.release),
        ],
      );
    }
    await this.redis.del(`model:${this.model}`);
  }

  async status(overrides: JsonObject = {}): Promise<void> {
    const values: JsonObject = {
      schema_version: 1,
      runtime_revision: this.release.runtime_revision as string,
      received_at: new Date().toISOString(),
      healthy: true,
      accepting_requests: true,
      reason_code: null,
      ...overrides,
    };
    await this.redis.hSet(
      `deployment-status:{${this.digest}}`,
      Object.fromEntries(
        this.deployments.map((deployment) => [
          deployment.id as string,
          encoded({ ...values, deployment_id: deployment.id }),
        ]),
      ),
    );
  }

  body(changes: JsonObject = {}): JsonObject {
    const base: JsonObject =
      this.kind === "kev"
        ? {
            model: this.model,
            state: "Synthetic billing ticket",
            questions: {
              q: { type: "noul", instructions: "Is this billing?" },
            },
          }
        : {
            model: this.model,
            messages: [{ role: "user", content: "Synthetic billing ticket" }],
          };
    return { ...base, ...changes };
  }

  post(changes: JsonObject = {}): Promise<Response> {
    return this.http.post(this.path, {
      headers: this.headers,
      json: this.body(changes),
    });
  }

  async settlements(): Promise<Settlement[]> {
    const entries = await this.redis.xRange(SETTLEMENT_STREAM, "-", "+");
    return entries
      .map((entry) => ({
        generation: entry.message.generation_id as string,
        properties: JSON.parse(
          entry.message.properties as string,
        ) as JsonObject,
      }))
      .filter(
        (entry) => entry.properties.organization_id === this.organization,
      );
  }

  async settled(
    response: { headers: Record<string, string> },
    status = "succeeded",
    charge?: number,
  ): Promise<JsonObject> {
    const generation = response.headers["x-generation-id"];
    const rows = await eventually(
      async () => {
        const matching = (await this.settlements()).filter(
          (entry) => entry.generation === generation,
        );
        return matching.length > 0 ? matching : undefined;
      },
      5000,
      `no settlement for generation ${generation}`,
    );
    expect(rows).toHaveLength(1);
    const properties = rows[0]!.properties;
    expect(properties.status, JSON.stringify(properties)).toBe(status);
    expect(properties.model_id).toBe(this.model);
    expect(properties.workspace_id).toBe(this.workspace);
    expect(properties.served_release_digest).toBe(this.digest);
    if (charge !== undefined) {
      expect((properties.usage as JsonObject).charge).toBe(charge);
    }
    return properties;
  }

  async assertClean(): Promise<void> {
    for (const runtime of this.runtimes) expect(runtime.errors).toEqual([]);
    expect(
      await this.redis.zCard(`inflight:{settlement-0}:${this.organization}`),
      "admission lease leaked",
    ).toBe(0);
    const rows = await this.settlements();
    expect(
      new Set(rows.map((row) => row.generation)).size,
      "duplicate settlement",
    ).toBe(rows.length);
    // The gateway creates the account hash when it first reads the account, so an
    // absent hash means no request ever reached the balance and nothing was charged.
    const stored = await this.redis.hGet(this.accountKey, "balance");
    const balance =
      stored === null || stored === undefined
        ? this.initialBalance
        : Number(stored);
    const charged = rows.reduce(
      (total, row) =>
        total + Number((row.properties.usage as JsonObject).charge),
      0,
    );
    expect(balance).toBe(this.initialBalance - charged);
  }

  async close(): Promise<void> {
    await Promise.all(this.runtimes.map((runtime) => runtime.close()));
  }
}

export interface CaseOptions {
  /** Number of independent runtime replicas behind the model. Defaults to one. */
  replicas?: number;
  /** Where successful responses come from. Defaults to the synthetic wire profile. */
  upstream?: Upstream;
  /** Model id the upstream serves; required when proxying to a real runtime. */
  runtimeModel?: string;
}

export type MakeCase = (
  kind: RuntimeKind,
  options?: CaseOptions,
) => Promise<Case>;

/** Per-file fixture: a redis connection, the gateway client, and cleanup between tests. */
export const useCases = (): { makeCase: MakeCase; http: () => Client } => {
  let redis: Redis;
  let database: Database;
  let http: Client;
  let patient: Client | null;
  let token: string;
  const created: Case[] = [];

  beforeAll(async () => {
    const stack = inject("stack");
    redis = createClient({
      url: stack.redisUrl,
      socket: { reconnectStrategy: false },
    });
    await redis.connect();
    database = new Pool({ connectionString: stack.databaseUrl });
    http = new Client(stack.gatewayUrl);
    patient = stack.patientGatewayUrl
      ? new Client(stack.patientGatewayUrl, 180_000)
      : null;
    token = stack.runtimeToken;
  });

  afterAll(async () => {
    if (redis?.isOpen) await redis.close();
    await database?.end();
  });

  afterEach(async () => {
    try {
      for (const instance of created) await instance.assertClean();
    } finally {
      await Promise.all(created.map((instance) => instance.close()));
      created.length = 0;
    }
  });

  return {
    makeCase: async (kind, options = {}) => {
      // Real inference cannot meet the short generation deadline the synthetic
      // cases rely on, so a proxied case talks to the patient gateway instead.
      const client = options.upstream?.kind === "proxy" ? patient : http;
      if (!client) throw new Error("no patient gateway; enable a real runtime");
      const instance = await Case.create(
        redis,
        database,
        client,
        token,
        kind,
        options,
      );
      created.push(instance);
      return instance;
    },
    http: () => http,
  };
};

export type { JsonObject, JsonValue };

/** Assert the runtime actually received the gated request. */
export const entered = async (plan: Plan, timeoutMs = 2000): Promise<void> => {
  const arrived = await Promise.race([
    plan.entered.promise.then(() => true),
    new Promise<boolean>((resolve) =>
      setTimeout(() => resolve(false), timeoutMs),
    ),
  ]);
  expect(arrived, "runtime never received the gated request").toBe(true);
};
