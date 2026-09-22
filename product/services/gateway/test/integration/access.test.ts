import { describe, expect, it } from "vitest";

import type { Headers } from "./http-client.js";
import type { RuntimeKind } from "./mock-runtimes/server.js";
import { encoded, eventually, useCases, type JsonObject } from "./support.js";

const { makeCase } = useCases();

describe.each(["kev", "vllm"] as RuntimeKind[])("%s access control", (kind) => {
  it.each(["missing", "wrong", "malformed", "duplicate", "expired", "revoked"])(
    "fails authentication (%s) before the runtime and admission",
    async (variant) => {
      const instance = await makeCase(kind);
      let headers: Headers = instance.headers;
      if (variant === "missing") headers = {};
      else if (variant === "wrong")
        headers = { Authorization: "Bearer wrong-synthetic-key" };
      else if (variant === "malformed")
        headers = { Authorization: "Basic synthetic" };
      else if (variant === "duplicate") {
        headers = {
          Authorization: [
            instance.headers.Authorization!,
            instance.headers.Authorization!,
          ],
        };
      } else {
        instance.credentialRecord[
          variant === "expired" ? "expires_at" : "revoked_at"
        ] = "2000-01-01T00:00:00Z";
        await instance.redis.set(
          instance.credentialKey,
          encoded(instance.credentialRecord),
        );
      }
      const response = await instance.http.post(instance.path, {
        headers,
        json: instance.body(),
      });
      expect(response.status).toBe(401);
      expect(response.json().error.code).toBe("invalid_api_key");
      expect(response.headers["x-generation-id"]).toBeTruthy();
      expect(instance.runtimes[0]!.calls).toEqual([]);
      expect(await instance.settlements()).toEqual([]);
    },
  );

  // A blocked tenant is a permanent policy decision, so it is forbidden. A cached
  // record that disagrees with itself is not the caller's fault, so it stays
  // unavailable. A workspace cannot go missing under a key any more: the foreign
  // key from api_keys guarantees it exists, so only a corrupt cache can produce it.
  it.each([
    { variant: "archived", expected: 403 },
    { variant: "suspended", expected: 403 },
    { variant: "corrupt_cache", expected: 503 },
    { variant: "tenant_mismatch", expected: 503 },
  ])(
    "fails closed for an inconsistent or blocked tenant ($variant)",
    async ({ variant, expected }) => {
      const instance = await makeCase(kind);
      if (variant === "suspended") {
        await instance.setTenant({ organizationStatus: "suspended" });
      } else if (variant === "archived") {
        await instance.setTenant({ workspaceArchived: true });
      } else if (variant === "corrupt_cache") {
        await instance.redis.set(
          `workspace:${instance.workspace}`,
          "not a workspace record",
        );
      } else {
        instance.workspaceRecord.organization_id =
          "00000000-0000-4000-8000-000000000001";
        await instance.redis.set(
          `workspace:${instance.workspace}`,
          encoded(instance.workspaceRecord),
        );
      }
      const response = await instance.post();
      expect(response.status).toBe(expected);
      expect(instance.runtimes[0]!.calls).toEqual([]);
      expect(await instance.settlements()).toEqual([]);
    },
  );

  it.each([
    { mode: "prepaid", balance: 0, status: 402 },
    { mode: "prepaid", balance: -1, status: 402 },
    { mode: "invoiced", balance: -1, status: 200 },
  ])(
    "applies the balance policy ($mode, $balance)",
    async ({ mode, balance, status }) => {
      const instance = await makeCase(kind);
      instance.initialBalance = balance;
      await instance.setTenant({
        billingMode: mode as "prepaid" | "invoiced",
        balance,
      });
      const response = await instance.post();
      expect(response.status).toBe(status);
      if (status === 200) {
        await instance.settled(response);
      } else {
        expect(instance.runtimes[0]!.calls).toEqual([]);
        expect(await instance.settlements()).toEqual([]);
      }
    },
  );

  it.each([
    { model: "absent/model" },
    { model: "" },
    { priority: -10 },
    { service_tier: "invalid" },
  ])("rejects the request (%o) before dispatch", async (change) => {
    const instance = await makeCase(kind);
    const response = await instance.post(change);
    expect(response.status).toBe(change.model === "absent/model" ? 404 : 400);
    expect(instance.runtimes[0]!.calls).toEqual([]);
    expect(await instance.settlements()).toEqual([]);
  });

  it("does not accept duplicate request fields", async () => {
    const instance = await makeCase(kind);
    const body = `${JSON.stringify(instance.body()).slice(0, -1)},"model":"other/model"}`;
    const response = await instance.http.post(instance.path, {
      headers: { ...instance.headers, "Content-Type": "application/json" },
      content: body,
    });
    expect(response.status).toBe(400);
    expect(instance.runtimes[0]!.calls).toEqual([]);
    expect(await instance.settlements()).toEqual([]);
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
    expect((await instance.http.get("/v1/models")).status).toBe(401);
    // The shared catalog cache deliberately has a one-second refresh interval.
    const entry = await eventually(
      async () => {
        const listed = await instance.http.get("/v1/models", {
          headers: instance.headers,
        });
        return listed
          .json()
          .data.find((item: { id: string }) => item.id === instance.model);
      },
      5000,
      "model never appeared in the catalog",
    );
    expect(entry.is_ready).toBe(true);
    expect(await instance.settlements()).toEqual([]);
  });

  it.each([
    { variant: "stale", expected: 503 },
    { variant: "unhealthy", expected: 503 },
    { variant: "busy", expected: 429 },
    { variant: "revision", expected: 503 },
    { variant: "draining", expected: 503 },
  ])(
    "never routes to an unroutable deployment ($variant)",
    async ({ variant, expected }) => {
      const instance = await makeCase(kind);
      const overrides: Record<string, JsonObject> = {
        stale: { received_at: "2000-01-01T00:00:00Z" },
        unhealthy: { healthy: false },
        busy: { accepting_requests: false },
        revision: { runtime_revision: "wrong" },
      };
      if (variant === "draining") {
        instance.deployments[0]!.status = "draining";
        await instance.publish();
      } else {
        await instance.status(overrides[variant]!);
      }
      expect((await instance.post()).status).toBe(expected);
      expect(instance.runtimes[0]!.calls).toEqual([]);
      expect(await instance.settlements()).toEqual([]);
    },
  );

  it("applies revocation after a successful authentication", async () => {
    const instance = await makeCase(kind);
    expect((await instance.post()).status).toBe(200);
    instance.credentialRecord.revoked_at = new Date().toISOString();
    await instance.redis.set(
      instance.credentialKey,
      encoded(instance.credentialRecord),
    );
    expect((await instance.post()).status).toBe(401);
    expect(instance.runtimes[0]!.calls).toHaveLength(1);
    expect(await instance.settlements()).toHaveLength(1);
  });

  it.each([
    { origin: "https://console.example.test", allowed: true },
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
      if (allowed) {
        const response = await instance.http.post(instance.path, {
          headers: { ...instance.headers, Origin: origin },
          json: instance.body(),
        });
        expect(response.status).toBe(200);
        expect(response.headers["access-control-expose-headers"]).toContain(
          "x-gradiated-service-tier",
        );
        await instance.settled(response);
      } else {
        expect(instance.runtimes[0]!.calls).toEqual([]);
      }
    },
  );

  it("rejects an oversized request before admission", async () => {
    const instance = await makeCase(kind);
    const response = await instance.http.post(instance.path, {
      headers: { ...instance.headers, "Content-Type": "application/json" },
      content: "x".repeat(32_000_001),
    });
    expect(response.status).toBe(413);
    expect(instance.runtimes[0]!.calls).toEqual([]);
    expect(await instance.settlements()).toEqual([]);
  });
});
