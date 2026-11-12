import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createPandaDocNda,
  NDA_SIGNING_UNAVAILABLE,
} from "../src/legal/pandadoc.js";
import { onboardingOrganizations, recordedNda } from "./onboarding-support.js";
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
  countersigner: {
    company: "Example Countersigner Inc.",
    name: "Grace Hopper",
    title: "Rear Admiral",
  },
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
    ...Object.fromEntries(
      Object.entries(details).flatMap(([field, value]) => [
        [`gradiated_${field}_parts`, "1"],
        [`gradiated_${field}_0`, value],
      ]),
    ),
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

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("PandaDoc NDA", () => {
  it("does not retry a conflicting document creation", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ id: "test-document", status: "document.uploaded" }),
          { status: 409 },
        ),
      );

    await expect(
      createPandaDocNda(configuration, request).create(owner, details),
    ).rejects.toMatchObject({ problem: { status: 503 } });
    expect(request).toHaveBeenCalledOnce();
  });

  it("waits through PandaDoc's processing conflict before reading a new document", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "test-document",
            status: "document.uploaded",
          }),
          { status: 409 },
        ),
      )
      .mockResolvedValueOnce(json(providerDocument()));

    expect(
      await createPandaDocNda(configuration, request).read(
        owner,
        "test-document",
      ),
    ).toMatchObject({ status: "ready" });
    expect(request).toHaveBeenCalledTimes(2);
    expect(
      request.mock.calls.every(([, options]) => options?.method === "GET"),
    ).toBe(true);
  });

  it("reports a document PandaDoc is still preparing after a bounded wait", async () => {
    vi.useFakeTimers();
    const request = vi.fn<typeof fetch>(
      async () =>
        new Response(
          JSON.stringify({ id: "test-document", status: "document.uploaded" }),
          { status: 409 },
        ),
    );
    const pending = createPandaDocNda(configuration, request).read(
      owner,
      "test-document",
    );
    await vi.advanceTimersByTimeAsync(10_000);

    await expect(pending).resolves.toEqual({
      id: "test-document",
      status: "preparing",
      details: null,
      completed_at: null,
      customer_completed: false,
    });
    expect(request.mock.calls.length).toBeLessThanOrEqual(20);
  });

  it("does not open signing for a document PandaDoc is still preparing", async () => {
    vi.useFakeTimers();
    const request = vi.fn<typeof fetch>(
      async () =>
        new Response(JSON.stringify({ status: "document.uploaded" }), {
          status: 409,
        }),
    );
    const pending = createPandaDocNda(configuration, request).session(
      owner,
      "test-document",
    );
    const rejection = expect(pending).rejects.toMatchObject({
      problem: { status: 409 },
    });
    await vi.advanceTimersByTimeAsync(10_000);

    await rejection;
    expect(
      request.mock.calls.every(([url]) => String(url).endsWith("/details")),
    ).toBe(true);
  });

  it("creates a customer-specific draft with the configured date and countersigner", async () => {
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
    expect(body.fields).toMatchObject({
      "Customer.Company": { value: details.company },
      "Customer.Address": { value: details.address },
      "Customer.Name": { value: details.name },
      "Customer.Title": { value: details.title },
      "Customer.Email": { value: details.email },
      "PostHog.Company": { value: "Example Countersigner Inc." },
      "PostHog.Signer": { value: "Grace Hopper" },
      "PostHog.Title": { value: "Rear Admiral" },
    });
    expect(body.fields["Agreement.Date"].value).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(body.tokens).toContainEqual({
      name: "Customer.Company",
      value: details.company,
    });
    expect(JSON.stringify(body)).not.toContain(configuration.apiKey);
  });

  it("sends the draft with PandaDoc email notifications and creates a short-lived session for the signed-in signer", async () => {
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
      silent: false,
    });
    expect(JSON.parse(String(request.mock.calls[2]?.[1]?.body))).toEqual({
      recipient: user.email,
      lifetime: 900,
    });
  });

  it("round-trips long Unicode details within PandaDoc's metadata value limit", async () => {
    const longDetails = {
      ...details,
      company: "Company ".repeat(25).trim(),
      address: "🏠 office ".repeat(100).trim(),
    };
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(providerDocument("document.uploaded")));
    const provider = createPandaDocNda(configuration, request);
    await provider.create(owner, longDetails);
    const body = JSON.parse(String(request.mock.calls[0]?.[1]?.body));

    for (const value of Object.values(body.metadata))
      expect(Array.from(String(value)).length).toBeLessThanOrEqual(100);

    request.mockResolvedValueOnce(
      json(
        providerDocument("document.draft", {
          metadata: body.metadata,
        }),
      ),
    );
    expect((await provider.read(owner, "test-document")).details).toEqual(
      longDetails,
    );
  });

  it("rejects incomplete details metadata", async () => {
    const document = providerDocument();
    delete (document.metadata as Record<string, unknown>).gradiated_company_0;
    const request = vi.fn<typeof fetch>().mockResolvedValue(json(document));

    await expect(
      createPandaDocNda(configuration, request).read(owner, "test-document"),
    ).rejects.toMatchObject({ problem: { status: 404 } });
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
          date_completed: "2026-08-16T12:00:00Z",
        }),
      ),
    );
    expect(await provider.read(owner, "test-document")).toMatchObject({
      status: "completed",
      completed_at: "2026-08-16T12:00:00.000Z",
    });
  });

  it.each([undefined, null, "not a date"])(
    "refuses a completed NDA without a provider completion time (%s)",
    async (date_completed) => {
      vi.spyOn(console, "log").mockImplementation(() => undefined);
      const request = vi.fn<typeof fetch>().mockResolvedValue(
        json(
          providerDocument("document.completed", {
            recipients: [{ email: user.email, has_completed: true }],
            date_completed,
          }),
        ),
      );
      await expect(
        createPandaDocNda(configuration, request).read(owner, "test-document"),
      ).rejects.toMatchObject({ problem: { status: 503 } });
    },
  );

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

  it("returns a safe unavailable error and logs only the provider status", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        new Response("sensitive provider response", { status: 401 }),
      );
    await expect(
      createPandaDocNda(configuration, request).create(owner, details),
    ).rejects.toMatchObject({
      problem: { status: 503, detail: NDA_SIGNING_UNAVAILABLE },
    });

    const lines = log.mock.calls.map(([line]) => JSON.parse(String(line)));
    expect(lines).toContainEqual(
      expect.objectContaining({
        level: "warn",
        event: "provider_request_failed",
        dependency: "pandadoc",
        route: "/documents",
        status: 401,
      }),
    );
    expect(JSON.stringify(lines)).not.toContain("sensitive provider response");
    expect(JSON.stringify(lines)).not.toContain(configuration.apiKey);
  });

  it("asks a customer to retry only provider failures that can recover", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const failing = (status: number) =>
      vi.fn<typeof fetch>().mockResolvedValue(new Response("{}", { status }));

    await expect(
      createPandaDocNda(configuration, failing(503)).create(owner, details),
    ).rejects.toMatchObject({
      problem: {
        detail: "NDA signing is temporarily unavailable. Please retry.",
      },
    });
    await expect(
      createPandaDocNda(configuration, failing(403)).session(owner, "doc-1"),
    ).rejects.toMatchObject({ problem: { detail: NDA_SIGNING_UNAVAILABLE } });
  });

  it("logs which PandaDoc call failed without the document ID", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    await expect(
      createPandaDocNda(
        configuration,
        vi
          .fn<typeof fetch>()
          .mockResolvedValue(new Response("{}", { status: 403 })),
      ).session(owner, "secret-document-id"),
    ).rejects.toBeDefined();

    const lines = log.mock.calls.map(([line]) => JSON.parse(String(line)));
    expect(lines).toContainEqual(
      expect.objectContaining({ route: "/documents/:id/details", status: 403 }),
    );
    expect(JSON.stringify(lines)).not.toContain("secret-document-id");
  });
});

describe("NDA document authorization", () => {
  const provider = {
    templateVersion: "v1",
    create: vi.fn(async () => ({
      id: "test-document",
      status: "preparing" as const,
      details,
      completed_at: null,
      customer_completed: false,
    })),
    read: vi.fn(),
    session: vi.fn(),
  };
  const app = (
    auth = authenticated,
    membership = organizationSummary,
    organizations = onboardingOrganizations({}, membership),
  ) =>
    createTestApp({
      auth,
      ndaDocuments: provider,
      services: { organizations },
    });

  it("requires a human session", async () => {
    expect((await postJson(app(anonymous), collection, details)).status).toBe(
      401,
    );
  });
  it.each([
    { method: "POST", suffix: "", body: details },
    { method: "GET", suffix: "/test-document", body: null },
    { method: "POST", suffix: "/test-document/signing-sessions", body: {} },
  ])(
    "rejects impersonation before calling PandaDoc: $method $suffix",
    async ({ method, suffix, body }) => {
      [provider.create, provider.read, provider.session].forEach((callback) =>
        callback.mockClear(),
      );
      const response = await app({
        ...authenticated,
        resolveSession: async () => ({
          ...user,
          impersonatedBy: "staff-reviewer",
        }),
      }).request(collection + suffix, {
        method,
        ...(body === null
          ? {}
          : {
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            }),
      });
      expect(response.status).toBe(403);
      [provider.create, provider.read, provider.session].forEach((callback) =>
        expect(callback).not.toHaveBeenCalled(),
      );
    },
  );
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

  it("records the organization's NDA once PandaDoc confirms completion", async () => {
    const organizations = onboardingOrganizations();
    provider.read.mockResolvedValueOnce({
      id: "test-document",
      status: "completed",
      details,
      completed_at: recordedNda.signed_at,
      customer_completed: true,
    });
    const response = await app(
      authenticated,
      organizationSummary,
      organizations,
    ).request(`${collection}/test-document`);

    expect(response.status).toBe(200);
    expect(organizations.recordOnboardingNda).toHaveBeenCalledWith(
      user.id,
      organizationId,
      recordedNda,
    );
  });

  it("does not record an NDA that is still awaiting signatures", async () => {
    const organizations = onboardingOrganizations();
    provider.read.mockResolvedValueOnce({
      id: "test-document",
      status: "ready",
      details,
      completed_at: null,
      customer_completed: true,
    });
    await app(authenticated, organizationSummary, organizations).request(
      `${collection}/test-document`,
    );

    expect(organizations.recordOnboardingNda).not.toHaveBeenCalled();
  });
});
