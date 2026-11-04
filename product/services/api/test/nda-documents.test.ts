import { describe, expect, it, vi } from "vitest";
import { createPandaDocNda } from "../src/legal/pandadoc.js";
import {
  authenticated,
  anonymous,
  createTestApp,
  organizationId,
  organizationSummary,
  postJson,
  user,
} from "./support.js";

const details = {
  company: "Example Inc.",
  address: "123 Example Street",
  name: user.name,
  title: "CEO",
  email: user.email,
};
const configuration = {
  apiKey: "test-key",
  templateId: "test-template",
  templateVersion: "v1",
  dateField: "Agreement.Date",
};
const owner = { organizationId, userId: user.id, email: user.email };
const providerDocument = (status = "document.draft", overrides = {}) => ({
  id: "test-document",
  status,
  metadata: {
    gradiated_purpose: "mutual-nda",
    gradiated_organization_id: organizationId,
    gradiated_user_id: user.id,
    gradiated_template_id: configuration.templateId,
    gradiated_template_version: configuration.templateVersion,
    gradiated_details: JSON.stringify(details),
  },
  recipients: [{ email: user.email, has_completed: false }],
  fields: [
    {
      type: "signature",
      assigned_to: { email: user.email },
      value: status === "document.completed" ? "test-signature" : "",
    },
  ],
  ...overrides,
});
const json = (value: unknown) =>
  new Response(JSON.stringify(value), {
    headers: { "Content-Type": "application/json" },
  });
const collection = `/api/v1/organizations/${organizationId}/nda-documents`;

describe("PandaDoc NDA", () => {
  it("creates a customer-specific document without sending email and fills the configured date", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(json(providerDocument("document.uploaded")));
    const provider = createPandaDocNda(configuration, request);
    const created = await provider.create(owner, details);
    const [, options] = request.mock.calls[0]!;
    const body = JSON.parse(String(options?.body));
    expect(created.status).toBe("preparing");
    expect(request).toHaveBeenCalledOnce();
    expect(body).toMatchObject({
      template_uuid: "test-template",
      recipients: [{ email: user.email, role: "Customer" }],
    });
    expect(body.metadata.gradiated_organization_id).toBe(organizationId);
    expect(body.fields["Agreement.Date"].value).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(body.tokens).toContainEqual({
      name: "Customer.Company",
      value: details.company,
    });
    expect(JSON.stringify(body)).not.toContain(configuration.apiKey);
  });

  it("silently prepares a draft and creates a short-lived session for the signed-in signer", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(providerDocument()))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(json({ id: "temporary-session" }));
    const provider = createPandaDocNda(configuration, request);
    await expect(provider.session(owner, "test-document")).resolves.toEqual({
      session_id: "temporary-session",
    });
    expect(
      String(request.mock.calls[1]?.[0]).endsWith("/test-document/send"),
    ).toBe(true);
    expect(JSON.parse(String(request.mock.calls[1]?.[1]?.body))).toEqual({
      silent: true,
    });
    expect(JSON.parse(String(request.mock.calls[2]?.[1]?.body))).toEqual({
      recipient: user.email,
      lifetime: 900,
    });
  });

  it("keeps completion pending until all required signers finish", async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(
      json(
        providerDocument("document.viewed", {
          recipients: [{ email: user.email, has_completed: true }],
        }),
      ),
    );
    const provider = createPandaDocNda(configuration, request);
    expect(await provider.read(owner, "test-document")).toMatchObject({
      status: "ready",
      customer_completed: true,
    });
    request.mockResolvedValueOnce(
      json(
        providerDocument("document.completed", {
          recipients: [{ email: user.email, has_completed: true }],
        }),
      ),
    );
    expect(await provider.read(owner, "test-document")).toMatchObject({
      status: "completed",
    });
  });

  it.each([
    { owner: { ...owner, organizationId: "another-organization" } },
    { owner: { ...owner, userId: "another-user" } },
    {
      document: {
        metadata: {
          ...providerDocument().metadata,
          gradiated_template_version: "old-version",
        },
      },
    },
  ])("rejects foreign ownership or an obsolete template", async (testCase) => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        json(providerDocument("document.draft", testCase.document)),
      );
    const provider = createPandaDocNda(configuration, request);
    await expect(
      provider.session(testCase.owner ?? owner, "test-document"),
    ).rejects.toMatchObject({ problem: { status: 404 } });
    expect(request).toHaveBeenCalledOnce();
  });

  it("cannot create a signing session impersonating a different signer", async () => {
    const request = vi.fn<typeof fetch>();
    await expect(
      createPandaDocNda(configuration, request).create(owner, {
        ...details,
        email: "someone-else@example.com",
      }),
    ).rejects.toMatchObject({ problem: { status: 403 } });
    expect(request).not.toHaveBeenCalled();
  });

  it("requires a customer signature field and does not treat text-only completion as signing", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        json(providerDocument("document.completed", { fields: [] })),
      );
    await expect(
      createPandaDocNda(configuration, request).read(owner, "test-document"),
    ).rejects.toMatchObject({ problem: { status: 503 } });
  });

  it("does not accept a completed document with an unfilled optional signature", async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(
      json(
        providerDocument("document.completed", {
          recipients: [{ email: user.email, has_completed: true }],
          fields: [
            {
              type: "signature",
              assigned_to: { email: user.email },
              value: {},
            },
          ],
        }),
      ),
    );
    await expect(
      createPandaDocNda(configuration, request).read(owner, "test-document"),
    ).rejects.toMatchObject({ problem: { status: 503 } });
  });

  it("returns a safe unavailable error without leaking the provider response or API key", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        new Response("sensitive provider response", { status: 401 }),
      );
    await expect(
      createPandaDocNda(configuration, request).create(owner, details),
    ).rejects.toMatchObject({
      problem: {
        status: 503,
        detail: "NDA signing is temporarily unavailable. Please retry.",
      },
    });
  });
});

describe("NDA document authorization", () => {
  const provider = {
    create: vi.fn(async () => ({
      id: "test-document",
      status: "preparing" as const,
      details,
      customer_completed: false,
    })),
    read: vi.fn(),
    session: vi.fn(),
  };
  const app = (auth = authenticated, membership = organizationSummary) =>
    createTestApp({
      auth,
      ndaDocuments: provider,
      services: { organizations: { listForUser: async () => [membership] } },
    });

  it("requires a human session", async () => {
    expect((await postJson(app(anonymous), collection, details)).status).toBe(
      401,
    );
  });
  it("requires organization management access", async () => {
    expect(
      (
        await postJson(
          app(authenticated, { ...organizationSummary, role: "member" }),
          collection,
          details,
        )
      ).status,
    ).toBe(403);
  });
  it("requires a verified signer email", async () => {
    expect(
      (
        await postJson(
          app({
            ...authenticated,
            resolveSession: async () => ({ ...user, emailVerified: false }),
          }),
          collection,
          details,
        )
      ).status,
    ).toBe(403);
  });
  it("has a safe missing-configuration state", async () => {
    const unconfigured = createTestApp({
      auth: authenticated,
      services: {
        organizations: { listForUser: async () => [organizationSummary] },
      },
    });
    expect((await postJson(unconfigured, collection, details)).status).toBe(
      503,
    );
  });
  it("returns a non-cacheable document owned by the current user and organization", async () => {
    const response = await postJson(app(), collection, details);
    expect(response.status).toBe(201);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(provider.create).toHaveBeenLastCalledWith(owner, details);
  });
});
