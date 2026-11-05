import { describe, it } from "vitest";

import {
  apiKeyId,
  createTestApp,
  expectProblem,
  organizationId,
  unauthenticatedProblem,
  workspaceId,
} from "./support.js";

const publicRoutes = new Set([
  "GET /api/auth/*",
  "POST /api/auth/*",
  "GET /api/openapi.json",
  "GET /docs",
  "GET /health/live",
  "GET /health/ready",
  "GET /api/v1/models",
  "POST /api/v1/waitlist",
  "POST /api/v1/invitations/preview",
  "POST /api/webhooks/stripe",
]);

const validInputs: Record<string, { query?: string; body?: unknown }> = {
  "POST /api/v1/organizations/:organization_id/slack-invitations": {
    body: { nda_document_id: "test-document" },
  },
  "POST /api/v1/organizations/:organization_id/nda-documents": {
    body: {
      company: "Example Inc.",
      address: "123 Example Street",
      name: "Ada Lovelace",
      title: "CEO",
      email: "ada@example.com",
    },
  },
  "POST /api/v1/workspaces/:workspace_id/training-runs": {
    body: { task_id: "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b8c" },
  },
  "POST /api/v1/admin/impersonations": {
    body: { user_id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774" },
  },
  "POST /api/v1/admin/organizations": { body: { name: "Acme" } },
  "POST /api/v1/organizations": { body: { name: "Acme" } },
  "PATCH /api/v1/organizations/:organization_id": { body: { name: "Acme" } },
  "POST /api/v1/organizations/:organization_id/workspaces": {
    body: { name: "Research" },
  },
  "PATCH /api/v1/organizations/:organization_id/billing": {
    body: { auto_top_up: { enabled: false } },
  },
  "POST /api/v1/organizations/:organization_id/billing/card": {
    body: { setup_intent_id: "seti_123" },
  },
  "POST /api/v1/organizations/:organization_id/billing/top-ups": {
    body: { amount: "50000000000" },
  },
  "PATCH /api/v1/organizations/:organization_id/members/:user_id": {
    body: { role: "member" },
  },
  "POST /api/v1/organizations/:organization_id/invitations": {
    body: { emails: ["new@example.com"], role: "member" },
  },
  "POST /api/v1/invitations/accept": { body: { token: "a".repeat(43) } },
  "PATCH /api/v1/workspaces/:workspace_id": {
    body: { trace_capture_enabled: false },
  },
  "POST /api/v1/workspaces/:workspace_id/api-keys": { body: { name: "CI" } },
  "GET /api/v1/workspaces/:workspace_id/usage": {
    query: "from=2026-09-01T00:00:00.000Z&to=2026-09-02T00:00:00.000Z",
  },
  "GET /api/v1/workspaces/:workspace_id/generations": { query: "task_id=test" },
  "GET /api/v1/workspaces/:workspace_id/generations/:generation_id": {
    query: "content_ref=contents%2Fbatch.jsonl",
  },
};

const pathParameters: Record<string, string> = {
  document_id: "example-nda",
  organization_id: organizationId,
  workspace_id: workspaceId,
  api_key_id: apiKeyId,
  generation_id: "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b8c",
  version_id: "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b8e",
  run_id: "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b8d",
  task: "support-triage",
  user_id: "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b8f",
  invitation_id: "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b90",
};

const sessionRoutes = [
  ...new Set(
    createTestApp()
      .routes.filter(({ method }) => method !== "ALL")
      .map(({ method, path }) => `${method} ${path}`),
  ),
].filter((route) => !publicRoutes.has(route));

const requestWithoutSession = (route: string) => {
  const [method, template] = route.split(" ") as [string, string];
  const path = template.replace(
    /:([a-z_]+)/g,
    (_match, name: string) => pathParameters[name]!,
  );
  const { query, body } = validInputs[route] ?? {};

  return createTestApp().request(query ? `${path}?${query}` : path, {
    method,
    ...(body === undefined
      ? {}
      : {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
  });
};

describe("session boundary", () => {
  it.each(sessionRoutes)(
    "rejects %s without a session before any service runs",
    async (route) => {
      await expectProblem(
        await requestWithoutSession(route),
        unauthenticatedProblem,
      );
    },
  );
});
