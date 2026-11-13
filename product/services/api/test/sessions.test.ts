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
  "GET /api/v1/shared-reports/:version_id/:signature",
  "GET /api/v1/shared-reports/:version_id/:signature/files/:file_id/content",
  "GET /api/v1/shared-reports/:version_id/:signature/files/:file_id/download",
  "POST /api/v1/invitations/preview",
  "POST /api/webhooks/stripe",
  "GET /.well-known/oauth-authorization-server",
  "GET /.well-known/oauth-authorization-server/api/auth",
]);

const validInputs: Record<string, { query?: string; body?: unknown }> = {
  "POST /api/v1/organizations/:organization_id/slack-invitations": {
    body: {},
  },
  "POST /api/v1/organizations/:organization_id/engineer-onboarding/submission":
    {
      body: { contact_channel: "email", github_installation_id: 42 },
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
  "POST /api/v1/workspaces/:workspace_id/tasks/:task/versions/:version_id/files":
    {
      body: {
        name: "report.md",
        size_bytes: 100,
        content_type: "text/markdown",
      },
    },
  "POST /api/v1/workspaces/:workspace_id/model-uploads": {
    body: {
      task: "triage",
      create_task: true,
      name: "triage-v1",
      base_model_id: "Qwen/Qwen3-0.6B",
      base_model_revision: "a".repeat(40),
      config_size: 200,
      weights_size: 500,
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
  "PUT /api/v1/me/oauth-workspace": {
    body: { workspace_id: "0198ae5a-2529-7c1a-801b-dc9d5f876a94" },
  },
  "POST /api/v1/workspaces/:workspace_id/playground/mcp-tool-lists": {
    body: { server: { url: "https://mcp.example.com/mcp" } },
  },
  "POST /api/v1/workspaces/:workspace_id/playground/mcp-tool-calls": {
    body: { server: { url: "https://mcp.example.com/mcp" }, name: "search" },
  },
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
  upload_id: "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b8c",
  file_id: "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b91",
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
