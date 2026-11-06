import { createHash } from "node:crypto";

import { Pool } from "pg";
import { createClient } from "redis";
import { afterAll, afterEach, beforeAll, expect, inject } from "vitest";

import {
  modelRecord,
  release,
  type Deployment,
  type DeploymentRuntimeStatus,
  type ModelRecord,
  type Release,
  type TokenPrices,
} from "./catalog.js";
import { CHAT_PROMPT } from "./chat.js";
import { eventually } from "./eventually.js";
import { Client, type Response } from "./http-client.js";
import { object, type JsonObject } from "./json.js";
import {
  Runtime,
  SYNTHETIC,
  type RuntimeKind,
  type Upstream,
} from "./mock-runtimes/server.js";

const BALANCE = 1_000_000_000_000;
const SETTLEMENT_STREAM = "generation-settled:{settlement-0}";

type Redis = ReturnType<typeof createClient>;

interface Connections {
  readonly redis: Redis;
  readonly database: Pool;
  readonly http: Client;
  readonly runtimeToken: string;
}

export interface Settlement {
  readonly generation: string;
  readonly properties: JsonObject;
}

export type SettlementStatus = "succeeded" | "failed" | "cancelled";

export interface TenantRows {
  organizationStatus?: "active" | "suspended";
  billingMode?: "prepaid" | "invoiced";
  workspaceArchived?: boolean;
}

export interface CredentialRow {
  revokedAt?: Date;
  expiresAt?: Date;
}

export type BalanceSource =
  | "stripe_checkout_session"
  | "stripe_refund"
  | "stripe_dispute"
  | "generation_settlement_batch"
  | "openrouter_payment"
  | "operator";

export class Case {
  readonly organization = crypto.randomUUID();
  readonly workspace = crypto.randomUUID();
  readonly credential = crypto.randomUUID();
  readonly key = `grad_${crypto.randomUUID().replaceAll("-", "")}`;
  readonly keyDigest = createHash("sha256").update(this.key).digest();
  readonly credentialKey = `credential:${this.keyDigest.toString("hex")}`;
  readonly accountKey = `account:{settlement-0}:${this.organization}`;
  readonly inflightKey = `inflight:{settlement-0}:${this.organization}`;
  readonly headers = { Authorization: `Bearer ${this.key}` };
  readonly path: string;
  readonly release: Release;
  readonly digest: string;
  readonly deployments: Deployment[];
  readonly record: ModelRecord;
  readonly redis: Redis;
  readonly database: Pool;
  readonly http: Client;
  creditedBalance = BALANCE;

  readonly openRouterModel: string | null;
  readonly organizationKind: OrganizationKind;
  readonly organizationName: string;

  private constructor(
    connections: Connections,
    readonly kind: RuntimeKind,
    readonly model: string,
    readonly runtimeModel: string,
    readonly runtimes: Runtime[],
    options: CaseOptions,
  ) {
    const { runtimeRevision, modelRevision } = options;
    this.openRouterModel = options.openRouterModel ?? null;
    this.organizationKind = options.organizationKind ?? "customer";
    this.organizationName =
      options.organizationName ?? `case-${this.organization}`;
    this.redis = connections.redis;
    this.database = connections.database;
    this.http = connections.http;
    this.path = kind === "kev" ? "/v1/systemone" : "/v1/chat/completions";
    this.release = {
      ...release(kind, model, runtimeModel),
      ...(runtimeRevision ? { runtime_revision: runtimeRevision } : {}),
      ...(modelRevision
        ? {
            model_path: runtimeModel,
            model_revision: modelRevision,
            tokenizer_path: runtimeModel,
            tokenizer_revision: modelRevision,
          }
        : {}),
    };
    this.digest = `sha256:${createHash("sha256").update(JSON.stringify(this.release)).digest("hex")}`;
    this.deployments = runtimes.map((runtime, index) => ({
      id: crypto.randomUUID(),
      status: "available",
      provider: "local",
      region: "local",
      fault_domain: String(index),
      service_url: runtime.url,
      release: this.release,
    }));
    this.record = modelRecord(kind, options.prices);
  }

  static async create(
    connections: Connections,
    kind: RuntimeKind,
    options: CaseOptions,
  ): Promise<Case> {
    const { database, runtimeToken } = connections;
    const upstream = options.upstream ?? SYNTHETIC;
    const model = `test/${kind}-${crypto.randomUUID().replaceAll("-", "")}`;
    const runtimeModel =
      upstream.kind === "proxy" ? upstream.model : `private/${model}`;

    const runtimes: Runtime[] = [];
    for (let index = 0; index < (options.replicas ?? 1); index += 1) {
      runtimes.push(
        await Runtime.start(kind, runtimeModel, runtimeToken, upstream),
      );
    }
    const instance = new Case(
      connections,
      kind,
      model,
      runtimeModel,
      runtimes,
      options,
    );

    // The tenant exists in PostgreSQL. The gateway caches what it reads, so no
    // test seeds Valkey: that would hide a query this suite is here to exercise.
    await database.query(
      `insert into organizations (id, kind, name, status)
       values ($1, $2, $3, 'active')`,
      [
        instance.organization,
        instance.organizationKind,
        instance.organizationName,
      ],
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
        instance.keyDigest,
      ],
    );

    await instance.publish();
    await instance.status();

    return instance;
  }

  /** Writes the tenant's rows only; the gateway sees them once its cached copies expire. */
  async writeTenantRows(changes: TenantRows): Promise<void> {
    if (changes.organizationStatus) {
      await this.database.query(
        `update organizations set status = $2, updated_at = now() where id = $1`,
        [this.organization, changes.organizationStatus],
      );
    }

    if (changes.billingMode) {
      await this.database.query(
        `update billing_accounts set mode = $2, updated_at = now()
         where organization_id = $1`,
        [this.organization, changes.billingMode],
      );
    }

    if (changes.workspaceArchived !== undefined) {
      // The schema forbids archiving a default workspace, so it stops being the
      // default at the same time.
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
  }

  /** Writes the tenant's rows and drops the cached copies, so the next request sees them. */
  async setTenant(changes: TenantRows & { balance?: number }): Promise<void> {
    await this.writeTenantRows(changes);

    if (changes.balance !== undefined) {
      await this.database.query(
        `update billing_accounts set balance = $2, updated_at = now()
         where organization_id = $1`,
        [this.organization, String(changes.balance)],
      );
      this.creditedBalance = changes.balance;
    }

    // The account hash holds the operational balance and is seeded from the row
    // only when it is absent, so removing it is what makes a new balance visible.
    await this.redis.del(this.accountKey);
    await this.redis.del(`workspace:${this.workspace}`);
  }

  async writeCredentialRow(changes: CredentialRow): Promise<void> {
    // api_keys_expiry_after_creation_check requires a past expiry to follow creation.
    await this.database.query(
      `update api_keys
       set revoked_at = coalesce($2::timestamptz, revoked_at),
           expires_at = coalesce($3::timestamptz, expires_at),
           created_at = least(created_at, $3::timestamptz - interval '1 second'),
           updated_at = now()
       where id = $1`,
      [this.credential, changes.revokedAt ?? null, changes.expiresAt ?? null],
    );
  }

  async setCredential(changes: CredentialRow): Promise<void> {
    await this.writeCredentialRow(changes);
    await this.redis.del(this.credentialKey);
  }

  /**
   * Appends a ledger entry. The gateway applies every entry except settlement
   * batches, which record debits it already made to the operational balance.
   */
  async recordBalanceTransaction(entry: {
    amount: number;
    sourceType: BalanceSource;
  }): Promise<void> {
    await this.database.query(
      `insert into balance_transactions
         (id, organization_id, type, amount, balance_after, source_type, source_id)
       select $1, $2, 'adjustment', $3, balance + $3, $4, $5
       from billing_accounts where organization_id = $2`,
      [
        crypto.randomUUID(),
        this.organization,
        String(entry.amount),
        entry.sourceType,
        crypto.randomUUID(),
      ],
    );

    if (entry.sourceType !== "generation_settlement_batch") {
      this.creditedBalance += entry.amount;
    }
  }

  async publish(): Promise<void> {
    await this.database.query(
      `insert into models (id, name, status, properties, openrouter_model_id)
       values ($1, $2, $3, $4, $5)
       on conflict (id) do update
       set name = excluded.name, status = excluded.status,
           properties = excluded.properties,
           openrouter_model_id = excluded.openrouter_model_id, updated_at = now()`,
      [
        this.model,
        this.record.name,
        this.record.status,
        JSON.stringify(this.record.properties),
        this.openRouterModel,
      ],
    );
    await this.database.query(
      `delete from model_deployments where model_id = $1`,
      [this.model],
    );
    for (const deployment of this.deployments) {
      await this.database.query(
        `insert into model_deployments
           (id, model_id, status, provider, region, fault_domain, service_url, release)
         values ($1, $2, $3, $4, $5, $6, $7, $8)`,
        [
          deployment.id,
          this.model,
          deployment.status,
          deployment.provider,
          deployment.region,
          deployment.fault_domain,
          deployment.service_url,
          JSON.stringify(deployment.release),
        ],
      );
    }

    await this.redis.del(`model:${this.model}`);
  }

  async status(
    overrides: Partial<Omit<DeploymentRuntimeStatus, "deployment_id">> = {},
    each: (
      index: number,
    ) => Partial<Omit<DeploymentRuntimeStatus, "deployment_id">> = () => ({}),
  ): Promise<void> {
    const values: Omit<DeploymentRuntimeStatus, "deployment_id"> = {
      schema_version: 1,
      runtime_revision: this.release.runtime_revision,
      received_at: new Date().toISOString(),
      healthy: true,
      accepting_requests: true,
      reason_code: null,
      ...overrides,
    };

    for (const [index, deployment] of this.deployments.entries()) {
      const digest = `sha256:${createHash("sha256").update(JSON.stringify(deployment.release)).digest("hex")}`;
      await this.redis.hSet(
        `deployment-status:{${digest}}`,
        deployment.id,
        JSON.stringify({
          ...values,
          runtime_revision: deployment.release.runtime_revision,
          ...overrides,
          ...each(index),
          deployment_id: deployment.id,
        }),
      );
    }
  }

  async ready(
    matches: (entry: JsonObject) => boolean = () => true,
  ): Promise<JsonObject> {
    return eventually(
      async () => {
        const response = await this.http.get("/v1/models", {
          headers: this.headers,
        });
        if (response.status !== 200)
          throw new Error("catalog readiness request failed");
        const data = response.json().data;
        if (!Array.isArray(data)) throw new Error("catalog has no model list");
        const entry = data.map(object).find((model) => model.id === this.model);

        return entry?.is_ready === true && matches(entry) ? entry : undefined;
      },
      5000,
      "new deployment never became ready through the gateway catalog",
    );
  }

  body(changes: JsonObject = {}): JsonObject {
    const base: JsonObject =
      this.kind === "kev"
        ? {
            model: this.model,
            state: CHAT_PROMPT,
            questions: {
              q: { type: "noul", instructions: "Is this billing?" },
            },
          }
        : {
            model: this.model,
            messages: [{ role: "user", content: CHAT_PROMPT }],
          };
    return { ...base, ...changes };
  }

  post(changes: JsonObject = {}): Promise<Response> {
    return this.http.post(this.path, {
      headers: this.headers,
      json: this.body(changes),
    });
  }

  totalCalls(): number {
    return this.runtimes.reduce(
      (total, runtime) => total + runtime.calls.length,
      0,
    );
  }

  async settlements(): Promise<Settlement[]> {
    const entries = await this.redis.xRange(SETTLEMENT_STREAM, "-", "+");
    return entries
      .map(({ id, message: { generation_id, properties } }) => {
        if (generation_id === undefined || properties === undefined) {
          throw new Error(`settlement ${id} lacks a generation or properties`);
        }

        return {
          generation: generation_id,
          properties: object(JSON.parse(properties)),
        };
      })
      .filter(
        (entry) => entry.properties.organization_id === this.organization,
      );
  }

  async settled(
    response: { headers: Record<string, string> },
    {
      status = "succeeded",
      charge,
      releaseDigest = this.digest,
    }: {
      status?: SettlementStatus;
      charge?: number;
      releaseDigest?: string;
    } = {},
  ): Promise<JsonObject> {
    const generation = response.headers["x-gradiated-generation-id"];
    expect(
      generation,
      "response has no x-gradiated-generation-id",
    ).toBeTruthy();

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
    expect(properties.served_release_digest).toBe(releaseDigest);
    if (charge !== undefined) {
      expect(properties.usage).toMatchObject({ charge });
    }

    return properties;
  }

  async expectNotDispatched(): Promise<void> {
    for (const runtime of this.runtimes) expect(runtime.calls).toEqual([]);
    expect(await this.settlements()).toEqual([]);
  }

  /**
   * The gateway creates the account hash when it first reads the account, so an
   * absent hash means no request ever reached the balance.
   */
  async operationalBalance(): Promise<number | undefined> {
    const stored = await this.redis.hGet(this.accountKey, "balance");
    return stored === null || stored === undefined ? undefined : Number(stored);
  }

  async charged(): Promise<number> {
    return (await this.settlements()).reduce(
      (total, row) => total + Number(object(row.properties.usage).charge),
      0,
    );
  }

  async assertClean(): Promise<void> {
    for (const runtime of this.runtimes) expect(runtime.errors).toEqual([]);
    expect(
      await this.redis.zCard(this.inflightKey),
      "admission lease leaked",
    ).toBe(0);

    const rows = await this.settlements();
    expect(
      new Set(rows.map((row) => row.generation)).size,
      "duplicate settlement",
    ).toBe(rows.length);

    const balance = (await this.operationalBalance()) ?? this.creditedBalance;
    expect(balance).toBe(this.creditedBalance - (await this.charged()));
  }

  async close(): Promise<void> {
    await Promise.all(this.runtimes.map((runtime) => runtime.close()));
  }
}

export type OrganizationKind = "customer" | "distribution_channel";

export interface CaseOptions {
  replicas?: number;
  /** Maps the case's model to this OpenRouter model. */
  openRouterModel?: string;
  prices?: TokenPrices;
  organizationKind?: OrganizationKind;
  /** OpenRouter's own organization is the distribution channel named "OpenRouter". */
  organizationName?: string;
  upstream?: Upstream;
  gatewayUrl?: string;
  runtimeRevision?: string;
  modelRevision?: string;
}

type MakeCase = (kind: RuntimeKind, options?: CaseOptions) => Promise<Case>;

export const useCases = (): { makeCase: MakeCase } => {
  let redis: Redis;
  let database: Pool;
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

  const client = (options: CaseOptions): Client => {
    if (options.gatewayUrl) return new Client(options.gatewayUrl);

    // Real inference cannot meet the short generation deadline the synthetic
    // cases rely on, so a proxied case talks to the patient gateway instead.
    if (options.upstream?.kind !== "proxy") return http;
    if (!patient) throw new Error("no patient gateway; enable a real runtime");

    return patient;
  };

  return {
    makeCase: async (kind, options = {}) => {
      const instance = await Case.create(
        { redis, database, http: client(options), runtimeToken: token },
        kind,
        options,
      );
      created.push(instance);

      return instance;
    },
  };
};
