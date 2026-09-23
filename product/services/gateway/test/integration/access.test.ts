import { describe, expect, it } from "vitest";

import {
  expectPublicError,
  expectRejected,
  pollUntilRejected,
  PROPAGATION_DEADLINE_MS,
  type Rejection,
} from "./assertions.js";
import { useCases, type Case } from "./case.js";
import { eventually, Fatal } from "./eventually.js";
import { BROWSER_ORIGIN } from "./gateway-process.js";
import type { Headers, Response } from "./http-client.js";
import { object } from "./json.js";
import { RUNTIME_KINDS } from "./mock-runtimes/server.js";

const { makeCase } = useCases();

const PAST = new Date("2000-01-01T00:00:00Z");

interface RejectedRequest {
  request: string;
  send: (instance: Case) => Promise<Response>;
  rejection: Rejection;
}

const postWith = (instance: Case, headers: Headers): Promise<Response> =>
  instance.http.post(instance.path, {
    headers: { ...instance.headers, ...headers },
    json: instance.body(),
  });

const postRaw = (instance: Case, content: string): Promise<Response> =>
  instance.http.post(instance.path, {
    headers: { ...instance.headers, "Content-Type": "application/json" },
    content,
  });

describe.each(RUNTIME_KINDS)("%s access control", (kind) => {
  it.each<{ variant: string; headers: (instance: Case) => Promise<Headers> }>([
    { variant: "missing", headers: async () => ({}) },
    {
      variant: "wrong",
      headers: async () => ({ Authorization: "Bearer wrong-synthetic-key" }),
    },
    {
      variant: "malformed",
      headers: async () => ({ Authorization: "Basic synthetic" }),
    },
    {
      variant: "duplicate",
      headers: async (instance) => ({
        Authorization: [
          instance.headers.Authorization,
          instance.headers.Authorization,
        ],
      }),
    },
    {
      variant: "expired",
      headers: async (instance) => {
        await instance.setCredential({ expiresAt: PAST });
        return instance.headers;
      },
    },
    {
      variant: "revoked",
      headers: async (instance) => {
        await instance.setCredential({ revokedAt: PAST });
        return instance.headers;
      },
    },
  ])(
    "fails authentication ($variant) before the runtime and admission",
    async ({ headers }) => {
      const instance = await makeCase(kind);

      const response = await instance.http.post(instance.path, {
        headers: await headers(instance),
        json: instance.body(),
      });

      expectRejected(response, { code: "invalid_api_key" });
      await instance.expectNotDispatched();
    },
  );

  it("rejects a well-formed key that matches no row, also once the miss is cached", async () => {
    const instance = await makeCase(kind);
    const unknown = `grad_${crypto.randomUUID().replaceAll("-", "")}`;

    for (let attempt = 0; attempt < 2; attempt += 1) {
      const response = await postWith(instance, {
        Authorization: `Bearer ${unknown}`,
      });

      expectRejected(response, { code: "invalid_api_key" });
    }

    await instance.expectNotDispatched();
  });

  // A blocked tenant is a permanent policy decision, so it is forbidden. A cached
  // record that disagrees with itself is not the caller's fault, so it stays
  // unavailable. The api_keys foreign key guarantees the workspace exists, so only
  // a corrupt cache can make it disagree.
  it.each<{
    variant: string;
    apply: (instance: Case) => Promise<unknown>;
    rejection: Rejection;
  }>([
    {
      variant: "archived",
      apply: (instance) => instance.setTenant({ workspaceArchived: true }),
      rejection: { code: "workspace_archived" },
    },
    {
      variant: "suspended",
      apply: (instance) =>
        instance.setTenant({ organizationStatus: "suspended" }),
      rejection: { code: "organization_suspended" },
    },
    {
      variant: "corrupt_cache",
      apply: (instance) =>
        instance.redis.set(
          `workspace:${instance.workspace}`,
          "not a workspace record",
        ),
      rejection: { code: "serving_state_unavailable" },
    },
    {
      variant: "tenant_mismatch",
      apply: (instance) =>
        instance.redis.set(
          `workspace:${instance.workspace}`,
          JSON.stringify({
            organization_id: "00000000-0000-4000-8000-000000000001",
            workspace_id: instance.workspace,
            archived_at: null,
          }),
        ),
      rejection: { code: "serving_state_unavailable" },
    },
  ])(
    "fails closed for an inconsistent or blocked tenant ($variant)",
    async ({ apply, rejection }) => {
      const instance = await makeCase(kind);
      await apply(instance);

      expectRejected(await instance.post(), rejection);
      await instance.expectNotDispatched();
    },
  );

  it.each<{
    mode: "prepaid" | "invoiced";
    balance: number;
    rejection?: Rejection;
  }>([
    {
      mode: "prepaid",
      balance: 0,
      rejection: { code: "insufficient_balance" },
    },
    {
      mode: "prepaid",
      balance: -1,
      rejection: { code: "insufficient_balance" },
    },
    { mode: "invoiced", balance: -1 },
  ])(
    "applies the balance policy ($mode, $balance)",
    async ({ mode, balance, rejection }) => {
      const instance = await makeCase(kind);
      await instance.setTenant({ billingMode: mode, balance });

      const response = await instance.post();

      if (rejection) {
        expectRejected(response, rejection);
        await instance.expectNotDispatched();
      } else {
        expect(response.status).toBe(200);
        await instance.settled(response);
      }
    },
  );

  it.each<RejectedRequest>([
    {
      request: "an unknown model",
      send: (instance) => instance.post({ model: "absent/model" }),
      rejection: { code: "model_not_found", param: "model" },
    },
    {
      request: "a model that is not available",
      send: async (instance) => {
        instance.record.status = "unavailable";
        await instance.publish();
        return instance.post();
      },
      rejection: { code: "model_unavailable", param: "model" },
    },
    {
      request: "an empty model",
      send: (instance) => instance.post({ model: "" }),
      rejection: { code: "invalid_request", param: "model" },
    },
    {
      request: "a priority field",
      send: (instance) => instance.post({ priority: -10 }),
      rejection: {
        code: "invalid_request",
        param: kind === "kev" ? null : "priority",
      },
    },
    {
      request: "an unknown service tier",
      send: (instance) => instance.post({ service_tier: "invalid" }),
      rejection: { code: "invalid_request", param: null },
    },
    {
      request: "a runtime priority header",
      send: (instance) => postWith(instance, { "x-vllm-priority": "-100" }),
      rejection: { code: "invalid_request", param: "priority" },
    },
    ...["x-gradiated-session-id", "x-session-id"].flatMap(
      (header): RejectedRequest[] => [
        {
          request: `an empty ${header} header`,
          send: (instance) => postWith(instance, { [header]: "" }),
          rejection: { code: "invalid_request", param: "session_id" },
        },
        {
          request: `a ${header} header over 256 bytes`,
          send: (instance) => postWith(instance, { [header]: "s".repeat(257) }),
          rejection: { code: "invalid_request", param: "session_id" },
        },
      ],
    ),
    {
      request: "duplicate request fields",
      send: (instance) =>
        postRaw(
          instance,
          `${JSON.stringify(instance.body()).slice(0, -1)},"model":"other/model"}`,
        ),
      rejection: { code: "invalid_request" },
    },
    {
      request: "an oversized body",
      send: (instance) => postRaw(instance, "x".repeat(32_000_001)),
      rejection: { code: "payload_too_large" },
    },
  ])("rejects $request before dispatch", async ({ send, rejection }) => {
    const instance = await makeCase(kind);

    expectRejected(await send(instance), rejection);
    await instance.expectNotDispatched();
  });

  it.each(["x-api-key", "Authorization"])(
    "accepts the %s header and a public model spelling",
    async (header) => {
      const instance = await makeCase(kind);
      const headers =
        header === "x-api-key"
          ? { "x-api-key": instance.key }
          : { Authorization: `Bearer ${instance.key}` };

      const response = await instance.http.post(instance.path, {
        headers,
        json: instance.body({ model: instance.model.toUpperCase() }),
      });

      expect(response.status).toBe(200);
      expect(response.json().model).toBe(instance.model);
      await instance.settled(response);
    },
  );

  it("requires auth for the catalog and advertises the exact model", async () => {
    const instance = await makeCase(kind);
    expectPublicError(await instance.http.get("/v1/models"), {
      code: "invalid_api_key",
    });

    // The shared catalog cache deliberately has a one-second refresh interval.
    const entry = await eventually(
      async () => {
        const listed = await instance.http.get("/v1/models", {
          headers: instance.headers,
        });
        const { data } = listed.json();
        if (!Array.isArray(data)) throw new Fatal("the catalog has no data");

        return data.map(object).find((item) => item.id === instance.model);
      },
      5000,
      "model never appeared in the catalog",
    );

    expect(entry.is_ready).toBe(true);
    expect(await instance.settlements()).toEqual([]);
  });

  it.each<{
    variant: string;
    apply: (instance: Case) => Promise<void>;
    rejection: Rejection;
  }>([
    {
      variant: "stale",
      apply: (instance) =>
        instance.status({ received_at: "2000-01-01T00:00:00Z" }),
      rejection: { code: "runtime_unavailable" },
    },
    {
      variant: "unhealthy",
      apply: (instance) => instance.status({ healthy: false }),
      rejection: { code: "runtime_unavailable" },
    },
    {
      variant: "busy",
      apply: (instance) => instance.status({ accepting_requests: false }),
      rejection: { code: "capacity_exceeded" },
    },
    {
      variant: "revision",
      apply: (instance) => instance.status({ runtime_revision: "wrong" }),
      rejection: { code: "runtime_unavailable" },
    },
    {
      variant: "draining",
      apply: async (instance) => {
        instance.deployments[0]!.status = "draining";
        await instance.publish();
      },
      rejection: { code: "serving_state_unavailable" },
    },
  ])(
    "never routes to an unroutable deployment ($variant)",
    async ({ apply, rejection }) => {
      const instance = await makeCase(kind);
      await apply(instance);

      expectRejected(await instance.post(), rejection);
      await instance.expectNotDispatched();
    },
  );

  it("applies revocation after a successful authentication", async () => {
    const instance = await makeCase(kind);
    expect((await instance.post()).status).toBe(200);

    await instance.setCredential({ revokedAt: new Date() });

    expectRejected(await instance.post(), { code: "invalid_api_key" });
    expect(instance.runtimes[0]!.calls).toHaveLength(1);
    expect(await instance.settlements()).toHaveLength(1);
  });

  it.each<{
    change: string;
    write: (instance: Case) => Promise<void>;
    rejection: Rejection;
  }>([
    {
      change: "key revoked",
      write: (instance) =>
        instance.writeCredentialRow({ revokedAt: new Date() }),
      rejection: { code: "invalid_api_key" },
    },
    {
      change: "organization suspended",
      write: (instance) =>
        instance.writeTenantRows({ organizationStatus: "suspended" }),
      rejection: { code: "organization_suspended" },
    },
    {
      change: "workspace archived",
      write: (instance) =>
        instance.writeTenantRows({ workspaceArchived: true }),
      rejection: { code: "workspace_archived" },
    },
  ])(
    "a PostgreSQL change reaches the gateway within the record-cache lifetime ($change)",
    async ({ write, rejection }) => {
      const instance = await makeCase(kind);
      expect((await instance.post()).status).toBe(200);

      const since = Date.now();
      await write(instance);
      const served = await pollUntilRejected(instance, since, rejection);

      for (let attempt = 0; attempt < 3; attempt += 1) {
        expectRejected(await instance.post(), rejection);
      }
      expect(instance.totalCalls()).toBe(1 + served);
    },
  );

  it.each([
    { origin: BROWSER_ORIGIN, allowed: true },
    { origin: "https://untrusted.example.test", allowed: false },
  ])(
    "enforces the browser CORS boundary ($origin)",
    async ({ origin, allowed }) => {
      const instance = await makeCase(kind);
      const preflight = await instance.http.options(instance.path, {
        headers: {
          Origin: origin,
          "Access-Control-Request-Method": "POST",
          "Access-Control-Request-Headers": "authorization,content-type",
        },
      });

      expect(preflight.headers["access-control-allow-origin"] === origin).toBe(
        allowed,
      );
      if (!allowed) {
        expect(instance.runtimes[0]!.calls).toEqual([]);
        return;
      }

      const response = await postWith(instance, { Origin: origin });
      expect(response.status).toBe(200);
      expect(response.headers["access-control-expose-headers"]).toContain(
        "x-gradiated-service-tier",
      );
      await instance.settled(response);
    },
  );
});

describe("prepaid balance ledger", () => {
  /** Serves requests until the operational balance includes every ledger entry the case expects. */
  const awaitLedger = async (instance: Case): Promise<void> => {
    await eventually(
      async () => {
        const response = await instance.post();
        if (response.status !== 200) {
          throw new Fatal(`request failed with ${response.status}`);
        }
        const expected = instance.creditedBalance - (await instance.charged());
        return (await instance.operationalBalance()) === expected;
      },
      PROPAGATION_DEADLINE_MS,
      "the ledger entry never reached the operational balance",
    );
  };

  it("applies a debit to the operational balance within the record-cache lifetime", async () => {
    const instance = await makeCase("vllm");
    expect((await instance.post()).status).toBe(200);
    const balance = (await instance.operationalBalance())!;

    const since = Date.now();
    await instance.recordBalanceTransaction({
      amount: -balance,
      sourceType: "operator",
    });
    const rejection: Rejection = { code: "insufficient_balance" };
    const served = await pollUntilRejected(instance, since, rejection);

    expectRejected(await instance.post(), rejection);
    expect(instance.totalCalls()).toBe(1 + served);
  });

  // A settlement batch records debits the gateway already made to the operational
  // balance, so applying it would charge the tenant twice.
  it("never applies a generation settlement batch", async () => {
    const instance = await makeCase("vllm");
    expect((await instance.post()).status).toBe(200);

    await instance.recordBalanceTransaction({
      amount: -instance.creditedBalance,
      sourceType: "generation_settlement_batch",
    });
    await instance.recordBalanceTransaction({
      amount: 1,
      sourceType: "operator",
    });
    await awaitLedger(instance);

    expect((await instance.post()).status).toBe(200);
  });

  it("keeps the operational balance when the balance row changes", async () => {
    const instance = await makeCase("vllm");
    expect((await instance.post()).status).toBe(200);

    await instance.database.query(
      `update billing_accounts set balance = 0, updated_at = now()
       where organization_id = $1`,
      [instance.organization],
    );
    await instance.recordBalanceTransaction({
      amount: 1,
      sourceType: "operator",
    });
    await awaitLedger(instance);

    expect((await instance.post()).status).toBe(200);
  });
});
