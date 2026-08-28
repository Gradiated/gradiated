import { describe, expect, it } from "vitest";

import { createApp, openApiDocument } from "../src/app.js";

describe("API contract", () => {
  it("generates the expected OpenAPI routes", () => {
    const document = createApp().getOpenAPI31Document(openApiDocument);

    expect(document.openapi).toBe("3.1.0");
    expect(document.info.title).toBe("Gradiated Management API");
    expect(document.paths).not.toHaveProperty("/health/live");
    expect(document.paths).not.toHaveProperty("/health/ready");
    expect(document.paths).not.toHaveProperty("/api/v1/wizard/key");
    expect(document.paths).not.toHaveProperty("/api/webhooks/stripe");
    expect(document.components?.schemas).not.toHaveProperty("HealthStatus");
    expect(document.components?.schemas).not.toHaveProperty("Readiness");
    expect(document.components?.schemas).not.toHaveProperty(
      "WizardKeyResponse",
    );
    expect(document.paths).toHaveProperty("/api/v1/me");
    expect(document.paths).toHaveProperty("/api/v1/organizations");
    expect(document.paths).toHaveProperty("/api/v1/models");
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
      "/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/api-keys",
    );
  });

  it("returns a problem document for an unknown route", async () => {
    const response = await createApp().request("/missing");

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toMatchObject({
      code: "not_found",
      status: 404,
    });
  });
});
