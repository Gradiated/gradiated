import { createRoute, OpenAPIHono } from "@hono/zod-openapi";
import { describe, expect, it } from "vitest";
import { createApp, publicOpenApiDocument } from "../src/app.js";
import {
  createOpenApiDocument,
  createOpenApiDocuments,
  unservedDependencies,
} from "../src/openapi.js";
import type { ApiEnvironment } from "../src/types.js";

const addRoute = (app: OpenAPIHono<ApiEnvironment>, path: string) => {
  app.openapi(
    createRoute({
      method: "get",
      path,
      responses: { 204: { description: "Test route" } },
    }),
    (context) => context.body(null, 204),
  );
};

describe("internal API documentation boundary", () => {
  it("excludes internal routes even without hide metadata, including mounted routers", async () => {
    const app = createApp(unservedDependencies());
    addRoute(app, "/api/internal");
    addRoute(app, "/api/internal/v1/direct");
    addRoute(app, "/api/internalized");
    const internal = new OpenAPIHono<ApiEnvironment>();
    addRoute(internal, "/v1/mounted");
    app.route("/api/internal", internal);

    expect((await app.request("/api/internal/v1/direct")).status).toBe(204);
    expect((await app.request("/api/internal/v1/mounted")).status).toBe(204);
    const response = await app.request("/api/openapi.json");
    expect(response.status).toBe(200);
    const document = await response.json();
    expect(document.paths).toEqual(publicOpenApiDocument(app).paths);
    expect(Object.keys(document.paths)).not.toEqual(
      expect.arrayContaining([
        "/api/internal",
        "/api/internal/v1/direct",
        "/api/internal/v1/mounted",
      ]),
    );
    expect(
      Object.keys(document.paths).filter(
        (path) => path === "/api/internal" || path.startsWith("/api/internal/"),
      ),
    ).toEqual([]);
    expect(document.paths).toHaveProperty("/api/internalized");
    const reference = await (await app.request("/docs")).text();
    expect(reference).toContain("/api/openapi.json");
    expect(reference).not.toContain("/api/internal/v1/direct");
  });

  it("excludes internal routes from the generated public contract", () => {
    expect(
      Object.keys(createOpenApiDocument().paths ?? {}).filter(
        (path) => path === "/api/internal" || path.startsWith("/api/internal/"),
      ),
    ).toEqual([]);
  });

  it("keeps console-only operations in the client contract only", async () => {
    const operationIds = (document: ReturnType<typeof createOpenApiDocument>) =>
      Object.values(document.paths ?? {}).flatMap((item) =>
        Object.values(item ?? {}).flatMap((operation) =>
          typeof operation === "object" && "operationId" in operation
            ? [operation.operationId]
            : [],
        ),
      );
    const consoleOperations = [
      "createTopUp",
      "createPaymentMethodSession",
      "getCurrentUser",
      "previewInvitation",
      "acceptInvitation",
    ];
    const documents = createOpenApiDocuments();
    const served = await (
      await createApp(unservedDependencies()).request("/api/openapi.json")
    ).json();

    expect(operationIds(documents.client)).toEqual(
      expect.arrayContaining(consoleOperations),
    );
    for (const document of [documents.public, served]) {
      expect(operationIds(document)).not.toEqual(
        expect.arrayContaining([expect.toBeOneOf(consoleOperations)]),
      );
      expect(operationIds(document)).toContain("getBillingAccount");
    }
  });
});
