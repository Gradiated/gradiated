import { randomUUID } from "node:crypto";

import {
  ControlServiceError,
  UsageEventRejectedError,
  type PriceListRecord,
  type TrainingBillingService,
} from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";

import {
  createTokenCheck,
  createTrainingInternalApp,
} from "../src/training-internal.js";

const token = "training-internal-test-token-with-32-characters";
const previous = "training-internal-old-token-with-32-characters";
const workspaceId = "0198ae5a-2529-7c1a-801b-dc9d5f876a94";

const priceList: PriceListRecord = {
  id: "pv_training_2026_11_27_placeholder",
  product: "training",
  effectiveAt: new Date("2026-11-27T00:00:00.000Z"),
  placeholder: true,
  items: [
    {
      sku: "train:qwen/qwen3-8b",
      unit: "token",
      priceNanoUsdPerMillion: 400_000_000n,
    },
  ],
};

const usageEvent = {
  event_id: "training:run-usage:run_1:1:1048576",
  workspace_id: workspaceId,
  product: "training",
  sku: "train:qwen/qwen3-8b",
  quantity: 1_048_576,
  amount_nano_usd: 419_430_400,
  price_version: priceList.id,
  occurred_at: "2026-11-27T12:00:00.000Z",
  subject_id: "run_1",
  tags: { attempt: "1" },
};

const testApp = (billing: Partial<TrainingBillingService> = {}) => {
  const service: TrainingBillingService = {
    ingestUsageEvents: vi.fn(async () => ({ accepted: 1, duplicates: 0 })),
    checkBalance: vi.fn(async () => ({ allowed: true })),
    priceList: vi.fn(async () => priceList),
    ...billing,
  };

  return {
    app: createTrainingInternalApp({
      tokens: [token, previous],
      billing: service,
    }),
    service,
  };
};

const send = (
  app: ReturnType<typeof testApp>["app"],
  path: string,
  init: {
    body?: unknown;
    bearer?: string | null;
    headers?: Record<string, string>;
  } = {},
) =>
  app.request(path, {
    method: init.body === undefined ? "GET" : "POST",
    headers: {
      ...(init.bearer === null
        ? {}
        : { authorization: `Bearer ${init.bearer ?? token}` }),
      ...(init.body === undefined
        ? {}
        : { "content-type": "application/json" }),
      ...init.headers,
    },
    ...(init.body === undefined ? {} : { body: JSON.stringify(init.body) }),
  });

describe("training internal listener", () => {
  describe("service credential", () => {
    it.each([
      ["no token", null],
      ["a wrong token", "x".repeat(48)],
      ["a prefix of the token", token.slice(0, -1)],
    ])("refuses %s on every route", async (_name, bearer) => {
      const { app, service } = testApp();

      for (const path of [
        "/api/internal/v1/billing/prices?product=training",
        "/api/internal/v1/billing/check",
        "/api/internal/v1/billing/usage-events",
      ]) {
        const response = await send(app, path, {
          bearer,
          ...(path.endsWith("prices?product=training")
            ? {}
            : { body: { workspace_id: workspaceId } }),
        });
        expect(response.status).toBe(401);
      }
      expect(service.priceList).not.toHaveBeenCalled();
      expect(service.checkBalance).not.toHaveBeenCalled();
      expect(service.ingestUsageEvents).not.toHaveBeenCalled();
    });

    it("accepts the previous token during a rotation", async () => {
      const response = await send(
        testApp().app,
        "/api/internal/v1/billing/prices?product=training",
        { bearer: previous },
      );

      expect(response.status).toBe(200);
    });

    it("matches whole tokens only", () => {
      const check = createTokenCheck([token]);

      expect(check(`Bearer ${token}`)).toBe(true);
      expect(check(`bearer ${token}`)).toBe(false);
      expect(check(`Bearer ${token} `)).toBe(false);
      expect(check(`Bearer ${token}x`)).toBe(false);
      expect(check(undefined)).toBe(false);
    });

    it("serves liveness without a token", async () => {
      const response = await testApp().app.request("/health/live");

      expect(response.status).toBe(200);
    });
  });

  describe("prices", () => {
    it("returns the current price list with its version as the ETag", async () => {
      const { app, service } = testApp();

      const response = await send(
        app,
        "/api/internal/v1/billing/prices?product=training",
      );

      expect(response.status).toBe(200);
      expect(response.headers.get("etag")).toBe(`"${priceList.id}"`);
      expect(await response.json()).toEqual({
        price_version: priceList.id,
        product: "training",
        effective_at: "2026-11-27T00:00:00.000Z",
        placeholder: true,
        skus: [
          {
            sku: "train:qwen/qwen3-8b",
            unit: "token",
            price_nano_usd_per_mtok: 400_000_000,
          },
        ],
      });
      expect(service.priceList).toHaveBeenCalledWith({
        product: "training",
        priceVersion: undefined,
      });
    });

    it("answers 304 while the caller holds the current version", async () => {
      const response = await send(
        testApp().app,
        "/api/internal/v1/billing/prices?product=training",
        { headers: { "if-none-match": `"${priceList.id}"` } },
      );

      expect(response.status).toBe(304);
    });

    it("serves a named version", async () => {
      const { app, service } = testApp();

      await send(
        app,
        `/api/internal/v1/billing/prices?product=training&price_version=${priceList.id}`,
      );

      expect(service.priceList).toHaveBeenCalledWith({
        product: "training",
        priceVersion: priceList.id,
      });
    });

    it("reports an unknown version as 404", async () => {
      const { app } = testApp({
        priceList: async () => {
          throw new ControlServiceError("not_found", "No such version.");
        },
      });

      const response = await send(
        app,
        "/api/internal/v1/billing/prices?product=training&price_version=pv_nope",
      );

      expect(response.status).toBe(404);
    });
  });

  describe("balance check", () => {
    it("passes an integer estimate through", async () => {
      const { app, service } = testApp({
        checkBalance: vi.fn(async () => ({
          allowed: false,
          reason: "insufficient_balance" as const,
        })),
      });

      const response = await send(app, "/api/internal/v1/billing/check", {
        body: {
          workspace_id: workspaceId,
          estimated_amount_nano_usd: "5000000000",
        },
      });

      expect(await response.json()).toEqual({
        allowed: false,
        reason: "insufficient_balance",
      });
      expect(service.checkBalance).toHaveBeenCalledWith({
        workspace_id: workspaceId,
        estimated_amount_nano_usd: 5_000_000_000n,
      });
    });

    it("accepts a USD estimate", async () => {
      const { app, service } = testApp();

      const response = await send(app, "/api/internal/v1/billing/check", {
        body: { workspace_id: workspaceId, estimated_cost_usd: 1.25 },
      });

      expect(await response.json()).toEqual({ allowed: true });
      expect(service.checkBalance).toHaveBeenCalledWith({
        workspace_id: workspaceId,
        estimated_cost_usd: 1.25,
      });
    });

    it.each([
      [{ workspace_id: workspaceId }],
      [
        {
          workspace_id: workspaceId,
          estimated_cost_usd: 1,
          estimated_amount_nano_usd: 1,
        },
      ],
    ])("requires exactly one estimate", async (body) => {
      const response = await send(
        testApp().app,
        "/api/internal/v1/billing/check",
        {
          body,
        },
      );

      expect(response.status).toBe(422);
    });
  });

  describe("usage ingest", () => {
    it("bills a batch", async () => {
      const { app, service } = testApp();

      const response = await send(
        app,
        "/api/internal/v1/billing/usage-events",
        {
          body: { events: [usageEvent] },
        },
      );

      expect(response.status).toBe(200);
      expect(await response.json()).toEqual({ accepted: 1, duplicates: 0 });
      expect(service.ingestUsageEvents).toHaveBeenCalledWith([
        { ...usageEvent, amount_nano_usd: 419_430_400n },
      ]);
    });

    it.each([
      ["price_mismatch", 422],
      ["unknown_workspace", 422],
      ["event_conflict", 409],
    ] as const)("answers %s with %s and the event", async (code, status) => {
      const { app } = testApp({
        ingestUsageEvents: async () => {
          throw new UsageEventRejectedError(
            code,
            usageEvent.event_id,
            "Rejected.",
          );
        },
      });

      const response = await send(
        app,
        "/api/internal/v1/billing/usage-events",
        {
          body: { events: [usageEvent] },
        },
      );

      expect(response.status).toBe(status);
      expect(await response.json()).toEqual({
        code,
        event_id: usageEvent.event_id,
        message: "Rejected.",
      });
    });

    it.each([
      ["inference usage", { product: "inference" }],
      ["an inference SKU", { sku: "inference:qwen/qwen3-8b:prompt" }],
      [
        "an event ID outside the training namespace",
        { event_id: "inference:gen:1" },
      ],
    ])("refuses %s before billing", async (_name, fields) => {
      const { app, service } = testApp();

      const response = await send(
        app,
        "/api/internal/v1/billing/usage-events",
        {
          body: { events: [{ ...usageEvent, ...fields }] },
        },
      );

      expect(response.status).toBe(422);
      expect(service.ingestUsageEvents).not.toHaveBeenCalled();
    });

    it("refuses more than 500 events", async () => {
      const events = Array.from({ length: 501 }, () => ({
        ...usageEvent,
        event_id: `training:run-usage:${randomUUID()}:1:1`,
      }));

      const response = await send(
        testApp().app,
        "/api/internal/v1/billing/usage-events",
        { body: { events } },
      );

      expect(response.status).toBe(422);
    });
  });

  it("describes every route in OpenAPI", () => {
    const document = testApp().app.getOpenAPI31Document({
      openapi: "3.1.0",
      info: { title: "Training internal", version: "1" },
    });

    expect(Object.keys(document.paths ?? {}).sort()).toEqual([
      "/api/internal/v1/billing/check",
      "/api/internal/v1/billing/prices",
      "/api/internal/v1/billing/usage-events",
    ]);
  });
});
