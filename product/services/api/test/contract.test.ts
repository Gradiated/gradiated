import { ControlServiceError } from "@gradiated/control";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createOpenApiDocument } from "../src/openapi.js";
import {
  authenticated,
  captureServiceLogs,
  createTestApp,
  expectProblem,
  failWith,
  validationProblem,
} from "./support.js";

const allowedOrigin = "https://console.gradiated.com";

const preflight = (origin: string) =>
  createTestApp({ allowedOrigins: [allowedOrigin] }).request("/api/v1/me", {
    method: "OPTIONS",
    headers: {
      Origin: origin,
      "Access-Control-Request-Method": "GET",
    },
  });

afterEach(() => {
  vi.restoreAllMocks();
});

const problemLogs = (logs: ReturnType<typeof captureServiceLogs>) =>
  logs.events().filter((event) => event.event !== "request_completed");

describe("API contract", () => {
  it("generates the expected OpenAPI routes", () => {
    const document = createOpenApiDocument();

    expect(document.openapi).toBe("3.1.0");
    expect(document.info.title).toBe("Gradiated API");
    expect(document.paths).not.toHaveProperty("/health/live");
    expect(document.paths).not.toHaveProperty("/health/ready");
    expect(document.paths).not.toHaveProperty("/api/v1/wizard/key");
    expect(document.paths).not.toHaveProperty("/api/webhooks/stripe");
    expect(document.components?.schemas).not.toHaveProperty("HealthStatus");
    expect(document.components?.schemas).not.toHaveProperty("Readiness");
    expect(document.components?.schemas).not.toHaveProperty(
      "WizardKeyResponse",
    );
    expect(document.paths).not.toHaveProperty("/api/v1/me");
    expect(document.paths).toHaveProperty("/api/v1/organizations");
    expect(document.paths).not.toHaveProperty("/api/v1/models");
    expect(document.paths).toHaveProperty(
      "/api/v1/organizations/{organization_id}/billing",
    );
    expect(document.paths).toHaveProperty(
      "/api/v1/organizations/{organization_id}/balance-transactions",
    );
    expect(document.paths).toHaveProperty(
      "/api/v1/organizations/{organization_id}/workspaces",
    );
    expect(document.paths).toHaveProperty(
      "/api/v1/workspaces/{workspace_id}/api-keys",
    );
  });

  it("returns a problem document for an unknown route", async () => {
    const response = await createTestApp().request("/missing");

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toMatchObject({
      code: "not_found",
      status: 404,
    });
  });

  it("hides an unexpected failure behind a logged internal error", async () => {
    const logs = captureServiceLogs();
    const app = createTestApp({
      services: {
        catalogBilling: {
          listModels: failWith(new Error("Bearer secret customer@example.com")),
        },
      },
    });

    const response = await app.request("/api/v1/models");

    await expectProblem(response, {
      status: 500,
      code: "internal_error",
      type: "internal",
    });

    expect(problemLogs(logs)).toEqual([
      expect.objectContaining({
        service: "api",
        level: "error",
        event: "request_failed",
        route: "/api/v1/models",
        status: 500,
        error_type: "Error",
      }),
    ]);
    expect(logs.lines().join("\n")).not.toMatch(/secret|customer@example\.com/);
  });

  it("logs a server-side problem with the bounded code of its cause", async () => {
    const logs = captureServiceLogs();
    const cause = Object.assign(new Error("connection refused"), {
      code: "ECONNREFUSED",
    });
    const app = createTestApp({
      services: {
        catalogBilling: {
          listModels: failWith(
            new ControlServiceError("unavailable", "Unavailable.", cause),
          ),
        },
      },
    });

    const response = await app.request("/api/v1/models");

    await expectProblem(response, {
      status: 503,
      code: "unavailable",
      type: "unavailable",
    });
    expect(problemLogs(logs)).toEqual([
      expect.objectContaining({
        event: "request_problem",
        route: "/api/v1/models",
        status: 503,
        error_code: "ECONNREFUSED",
      }),
    ]);
  });

  it("does not log a client-side problem", async () => {
    const logs = captureServiceLogs();
    const app = createTestApp({
      services: {
        catalogBilling: {
          listModels: failWith(new ControlServiceError("forbidden", "No.")),
        },
      },
    });

    const response = await app.request("/api/v1/models");

    expect(response.status).toBe(403);
    expect(problemLogs(logs)).toEqual([]);
  });

  it("rejects a malformed JSON body as a validation problem", async () => {
    const logs = captureServiceLogs();

    const response = await createTestApp({ auth: authenticated }).request(
      "/api/v1/organizations",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{",
      },
    );

    await expectProblem(response, validationProblem);
    expect(problemLogs(logs)).toEqual([]);
  });

  it("allows credentialed CORS only from a configured origin", async () => {
    const allowed = await preflight(allowedOrigin);
    const unknown = await preflight("https://attacker.example");

    expect(allowed.headers.get("access-control-allow-origin")).toBe(
      allowedOrigin,
    );
    expect(allowed.headers.get("access-control-allow-credentials")).toBe(
      "true",
    );
    expect(unknown.headers.get("access-control-allow-origin")).toBeNull();
  });
});
