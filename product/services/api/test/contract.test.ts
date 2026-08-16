import { describe, expect, it } from "vitest";

import { createApp, openApiDocument } from "../src/app.js";

describe("API contract", () => {
  it("generates the expected OpenAPI routes", () => {
    const document = createApp().getOpenAPI31Document(openApiDocument);

    expect(document.openapi).toBe("3.1.0");
    expect(document.paths).toHaveProperty("/health/live");
    expect(document.paths).toHaveProperty("/health/ready");
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
