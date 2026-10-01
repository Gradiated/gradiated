import { Pool } from "pg";
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  inject,
  it,
} from "vitest";

import { entered } from "./admission.js";
import { expectRejected } from "./assertions.js";
import { useCases } from "./case.js";
import { deferred, eventually } from "./eventually.js";
import {
  GatewayProcess,
  GENERATION_TIMEOUT_SECONDS,
  type GatewayOptions,
} from "./gateway-process.js";
import { Client } from "./http-client.js";
import { freePort } from "./ports.js";

const { makeCase } = useCases();

const gatewayOptions = async (): Promise<GatewayOptions> => {
  const stack = inject("stack");

  return {
    redisUrl: stack.redisUrl,
    databaseUrl: stack.databaseUrl,
    runtimeToken: stack.runtimeToken,
    port: await freePort(),
    generationTimeoutSeconds: GENERATION_TIMEOUT_SECONDS,
    logName: `gateway-process-${crypto.randomUUID()}`,
  };
};

const refusesConnections = async (url: string): Promise<boolean> => {
  try {
    await new Client(url).get("/health/live", { timeoutMs: 250 });
    return false;
  } catch (error) {
    return (
      error instanceof Error && "code" in error && error.code === "ECONNREFUSED"
    );
  }
};

const unreachable = async (scheme: string): Promise<string> =>
  `${scheme}://127.0.0.1:${await freePort()}`;

/** A login role that can read every table, like the gateway's production role. */
class ReaderRole {
  readonly name = `gateway_${crypto.randomUUID().replaceAll("-", "")}`;

  constructor(private readonly admin: Pool) {}

  async create(): Promise<void> {
    await this.admin.query(
      `create role ${this.name} login password '${this.name}'`,
    );
    await this.admin.query(
      `grant select on all tables in schema public to ${this.name}`,
    );
  }

  databaseUrl(adminUrl: string): string {
    const url = new URL(adminUrl);
    url.username = this.name;
    url.password = this.name;

    return url.toString();
  }

  async revokeLogin(): Promise<void> {
    await this.admin.query(`alter role ${this.name} nologin`);
    await this.admin.query(
      `select pg_terminate_backend(pid) from pg_stat_activity where usename = $1`,
      [this.name],
    );
  }

  async drop(): Promise<void> {
    await this.admin.query(`drop owned by ${this.name}`);
    await this.admin.query(`drop role ${this.name}`);
  }
}

describe("gateway process", () => {
  const started: GatewayProcess[] = [];
  const roles: ReaderRole[] = [];
  let admin: Pool;

  beforeAll(() => {
    admin = new Pool({ connectionString: inject("stack").databaseUrl });
  });

  afterEach(async () => {
    for (const gateway of started.splice(0)) {
      if (gateway.running) gateway.child.kill("SIGKILL");
      await gateway.exited;
    }

    for (const role of roles.splice(0)) await role.drop();
  });

  afterAll(async () => {
    await admin.end();
  });

  it.each<NodeJS.Signals>(["SIGTERM", "SIGINT"])(
    "stops accepting on %s and settles the generation in flight",
    async (signal) => {
      const gateway = await GatewayProcess.start(await gatewayOptions());
      started.push(gateway);
      const instance = await makeCase("vllm", { gatewayUrl: gateway.url });
      const gate = deferred();
      const plan = instance.runtimes[0]!.enqueue({ gate });

      const request = instance.post();
      try {
        await entered(plan);
        gateway.child.kill(signal);
        await eventually(
          () => refusesConnections(gateway.url),
          5000,
          "the draining gateway kept accepting connections",
        );
      } finally {
        gate.resolve();
      }

      const response = await request;

      expect(response.status).toBe(200);
      await instance.settled(response);
      expect(await instance.settlements()).toHaveLength(1);
      expect(await gateway.exit(5000)).toEqual({ code: 0, signal: null });
    },
  );

  it.each([
    {
      dependency: "PostgreSQL",
      cause: "postgres",
      options: async (): Promise<Partial<GatewayOptions>> => ({
        databaseUrl: `${await unreachable("postgres")}/gradiated?sslmode=disable`,
      }),
    },
    {
      dependency: "Valkey",
      cause: "valkey",
      options: async (): Promise<Partial<GatewayOptions>> => ({
        redisUrl: await unreachable("redis"),
      }),
    },
  ])(
    "exits before readiness when $dependency is unreachable",
    async ({ cause, options }) => {
      const gateway = GatewayProcess.spawn({
        ...(await gatewayOptions()),
        ...(await options()),
      });
      started.push(gateway);

      const exit = await gateway.exit(5000);

      expect(exit, "the gateway kept running").toBeDefined();
      expect(exit!.code).not.toBe(0);
      expect(exit!.code).not.toBeNull();
      expect(await gateway.log()).toContain(`"error_code":"${cause}"`);
    },
  );

  it("refuses a generation it could not settle without dispatching it", async () => {
    const gateway = await GatewayProcess.start({
      ...(await gatewayOptions()),
      settlementBacklogLimit: 1,
    });
    started.push(gateway);
    const settled = await makeCase("vllm");
    const refused = await makeCase("vllm", { gatewayUrl: gateway.url });

    await settled.settled(await settled.post());
    const response = await refused.post();

    expectRejected(response, { code: "settlement_backlog" });
    await refused.expectNotDispatched();
  });

  it("enforces one organization concurrency cap across two gateway processes", async () => {
    const first = await GatewayProcess.start({
      ...(await gatewayOptions()),
      generationTimeoutSeconds: 10,
    });
    const second = await GatewayProcess.start({
      ...(await gatewayOptions()),
      generationTimeoutSeconds: 10,
    });
    started.push(first, second);
    const instance = await makeCase("vllm", { gatewayUrl: first.url });
    const gates = [deferred(), deferred()];
    const plans = gates.map((gate) => instance.runtimes[0]!.enqueue({ gate }));
    const send = (url: string) =>
      new Client(url).post(instance.path, {
        headers: instance.headers,
        json: instance.body(),
      });
    const held = [send(first.url), send(second.url)];

    try {
      await Promise.all(plans.map(entered));
      expect(await instance.redis.zCard(instance.inflightKey)).toBe(2);
      const refused = await Promise.all(
        Array.from({ length: 6 }, (_, index) =>
          send(index % 2 ? first.url : second.url),
        ),
      );
      for (const response of refused)
        expectRejected(response, { code: "concurrency_exceeded" });
      expect(instance.totalCalls()).toBe(2);
    } finally {
      for (const gate of gates) gate.resolve();
    }

    for (const response of await Promise.all(held)) {
      expect(response.status).toBe(200);
      await instance.settled(response);
    }
    expect(await instance.settlements()).toHaveLength(2);
  });

  it("recovers capacity from a crashed gateway after its leases expire without inventing charges", async () => {
    const settings = {
      leaseFinalizationMarginSeconds: 1,
      expiredLeaseCleanupGraceSeconds: 1,
    };
    const crashed = await GatewayProcess.start({
      ...(await gatewayOptions()),
      ...settings,
    });
    const survivor = await GatewayProcess.start({
      ...(await gatewayOptions()),
      ...settings,
    });
    started.push(crashed, survivor);
    const instance = await makeCase("vllm", { gatewayUrl: crashed.url });
    const gates = [deferred(), deferred()];
    const plans = gates.map((gate) => instance.runtimes[0]!.enqueue({ gate }));
    const held = plans.map(() =>
      instance.post().catch((error: unknown) => error),
    );
    const send = () =>
      new Client(survivor.url).post(instance.path, {
        headers: instance.headers,
        json: instance.body(),
      });

    try {
      await Promise.all(plans.map(entered));
      const leases = await instance.redis.zRangeWithScores(
        instance.inflightKey,
        0,
        -1,
      );
      expect(leases).toHaveLength(2);
      const balance = await instance.operationalBalance();
      crashed.child.kill("SIGKILL");
      await crashed.exited;
      expectRejected(await send(), { code: "concurrency_exceeded" });
      expect(await instance.operationalBalance()).toBe(balance);
      expect(await instance.settlements()).toEqual([]);

      const expires = Math.max(...leases.map((lease) => lease.score));
      await eventually(
        () => Date.now() > expires + 1_000,
        7_000,
        "abandoned lease expiry and cleanup grace",
      );
      for (const gate of gates) gate.resolve();
      const response = await send();
      expect(response.status).toBe(200);
      await instance.settled(response);
      expect(await instance.redis.zCard(instance.inflightKey)).toBe(0);
      expect(await instance.settlements()).toHaveLength(1);
      for (const result of await Promise.all(held))
        expect(result).toBeInstanceOf(Error);
    } finally {
      for (const gate of gates) gate.resolve();
      await Promise.all(held);
    }
  });

  it("fails closed when PostgreSQL rejects a read-through after startup", async () => {
    const options = await gatewayOptions();
    const role = new ReaderRole(admin);
    await role.create();
    roles.push(role);
    const gateway = await GatewayProcess.start({
      ...options,
      databaseUrl: role.databaseUrl(options.databaseUrl),
    });
    started.push(gateway);
    const instance = await makeCase("vllm", { gatewayUrl: gateway.url });

    await role.revokeLogin();
    const response = await instance.post();

    expectRejected(response, { code: "serving_state_unavailable" });
    await instance.expectNotDispatched();
    await eventually(
      async () => (await gateway.log()).includes('"error_code":"postgres"'),
      5000,
      "the gateway never logged the PostgreSQL cause",
    );
  });
});
