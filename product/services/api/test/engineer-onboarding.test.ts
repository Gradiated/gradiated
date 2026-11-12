import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createLoggingEngineerOnboardingNotifier,
  createResendEngineerOnboardingNotifier,
} from "../src/email/engineer-onboarding.js";
import {
  memoryIntegrations,
  ndaProvider,
  onboardingOrganizations,
  recordedNda,
  slackRecord,
} from "./onboarding-support.js";
import {
  authenticated,
  createTestApp,
  now,
  organizationId,
  organizationSummary,
  postJson,
  user,
} from "./support.js";

const path = `/api/v1/organizations/${organizationId}/engineer-onboarding`;
const installation = {
  id: 42,
  account: "example",
  account_type: "Organization" as const,
  manage_url:
    "https://github.com/organizations/example/settings/installations/42",
  repository_selection: "selected" as const,
  repository_count: 3,
  repositories: ["example/trainer", "example/evals", "example/data"],
};
const submission = {
  contact_channel: "slack",
  github_installation_id: 42,
  notes: "  We need help with our retrieval pipeline.  ",
};

afterEach(() => vi.restoreAllMocks());

describe("engineer onboarding notification", () => {
  it("emails the team address with escaped customer content", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(
      async () => new Response(null, { status: 200 }),
    );
    await createResendEngineerOnboardingNotifier({
      from: "Gradiated <auth@example.com>",
      apiKey: "resend-test-key",
      fetch,
    })({
      organizationId,
      organizationName: "<Example>",
      submittedByEmail: user.email,
      contactChannel: "email",
      githubAccounts: ["example"],
      slackChannel: null,
      ndaSignedAt: null,
      notes: "<script>alert(1)</script>",
    });

    const body = JSON.parse(String(fetch.mock.calls[0]?.[1]?.body));
    expect(body.to).toEqual(["team@gradiated.com"]);
    expect(body.subject).toBe("Engineer onboarding submitted: <Example>");
    expect(body.html).not.toContain("<script>");
    expect(body.text).toContain("<script>alert(1)</script>");
    expect(body.text).toContain("Mutual NDA: Not requested");
  });

  it("logs instead of emailing in test mail mode", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    await createLoggingEngineerOnboardingNotifier()({
      organizationId,
      organizationName: "Example",
      submittedByEmail: user.email,
      contactChannel: "email",
      githubAccounts: [],
      slackChannel: null,
      ndaSignedAt: null,
      notes: "Private notes",
    });

    const line = JSON.parse(String(log.mock.calls[0]?.[0]));
    expect(line).toMatchObject({
      level: "warn",
      event: "engineer_onboarding_notification_skipped",
      organization_id: organizationId,
    });
    expect(JSON.stringify(line)).not.toContain("Private notes");
  });
});

const setup = (
  options: {
    role?: "admin" | "member";
    nda?: boolean;
    ndaDocument?: string;
    slackChannel?: boolean;
    token?: string | null;
    installations?: (typeof installation)[];
    testMode?: boolean;
  } = {},
) => {
  const organizations = onboardingOrganizations(
    options.nda === false ? {} : { nda: recordedNda },
    { ...organizationSummary, role: options.role ?? "admin" },
  );
  const { service: integrations, rows } = memoryIntegrations(
    options.slackChannel === false
      ? []
      : [
          slackRecord({
            settings: {
              schema_version: 1,
              channel_name: "ext-example-gradiated",
              invited_email: user.email,
              invited_at: now.toISOString(),
            },
          }),
        ],
  );
  const slack = { postNotes: vi.fn(async () => ({ status: "sent" as const })) };
  const github = {
    list: vi.fn(async () => ({
      status: "installed" as const,
      installations: options.installations ?? [installation],
    })),
  };
  const notify = vi.fn(async () => undefined);
  const app = createTestApp({
    auth: {
      ...authenticated,
      githubAccessToken: async () =>
        options.token === undefined ? "user-token" : options.token,
    },
    ndaDocuments: ndaProvider(options.ndaDocument),
    slackConnect: slack as never,
    githubInstallations: github,
    notifyEngineerOnboarding: notify,
    services: { organizations, integrations },
    ...(options.testMode
      ? {
          authTestMailbox: {
            takeMagicLink: () => null,
            takeOtp: () => null,
            takeInvitation: () => null,
          },
        }
      : {}),
  });

  return { app, organizations, integrations, rows, slack, github, notify };
};

describe("engineer onboarding state", () => {
  it("returns the persisted onboarding state for resuming", async () => {
    const { app, rows } = setup();
    rows.push({
      ...slackRecord(),
      id: "0198ae80-0000-7000-9000-000000000042",
      provider: "github",
      externalId: "42",
      settings: {
        schema_version: 1,
        account_login: "example",
        repository_selection: "all",
      },
    });
    const response = await app.request(path);

    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(await response.json()).toEqual({
      nda: {
        document_id: recordedNda.document_id,
        signed_at: recordedNda.signed_at,
      },
      slack: {
        channel_id: "C123456",
        channel_name: "ext-example-gradiated",
        status: "active",
        invited_email: user.email,
        invited_at: now.toISOString(),
      },
      github_installations: [
        { id: 42, account: "example", repository_selection: "all" },
      ],
      contact_channel: null,
      submitted_at: null,
    });
  });

  it("starts empty", async () => {
    const { app } = setup({ nda: false, slackChannel: false });

    expect(await (await app.request(path)).json()).toEqual({
      nda: null,
      slack: null,
      github_installations: [],
      contact_channel: null,
      submitted_at: null,
    });
  });

  it.each([
    { auth: authenticated, role: "member" as const },
    {
      auth: {
        ...authenticated,
        resolveSession: async () => ({ ...user, impersonatedBy: user.id }),
      },
      role: "admin" as const,
    },
  ])("requires a verified admin outside impersonation", async (input) => {
    const { organizations, integrations } = setup({ role: input.role });
    const app = createTestApp({
      auth: input.auth,
      services: { organizations, integrations },
    });

    expect((await app.request(path)).status).toBe(403);
    expect(organizations.getOnboarding).not.toHaveBeenCalled();
  });
});

describe("engineer onboarding submission", () => {
  it("records the submission, posts notes and notifies Gradiated exactly once", async () => {
    const { app, slack, notify, github, organizations, integrations } = setup();
    const first = await postJson(app, `${path}/submission`, submission);

    expect(first.status).toBe(201);
    const state = await first.json();
    expect(state).toMatchObject({
      contact_channel: "slack",
      submitted_at: now.toISOString(),
      github_installations: [
        { id: 42, account: "example", repository_selection: "selected" },
      ],
    });
    expect(github.list).toHaveBeenCalledWith("user-token", 42);
    expect(integrations.recordGithubInstallation).toHaveBeenCalledWith(
      user.id,
      organizationId,
      { id: 42, account_login: "example", repository_selection: "selected" },
    );
    expect(organizations.submitOnboarding).toHaveBeenCalledWith(
      user.id,
      organizationId,
      "slack",
    );
    expect(slack.postNotes).toHaveBeenCalledWith({
      channelId: "C123456",
      email: user.email,
      notes: "We need help with our retrieval pipeline.",
      requestId: organizationId,
    });
    expect(notify).toHaveBeenCalledWith({
      organizationId,
      organizationName: organizationSummary.name,
      submittedByEmail: user.email,
      contactChannel: "slack",
      githubAccounts: ["example"],
      slackChannel: "ext-example-gradiated",
      ndaSignedAt: recordedNda.signed_at,
      notes: "We need help with our retrieval pipeline.",
    });

    const repeated = await postJson(app, `${path}/submission`, {
      ...submission,
      contact_channel: "email",
      notes: "Different notes",
    });
    expect(repeated.status).toBe(200);
    expect(await repeated.json()).toEqual(state);
    expect(slack.postNotes).toHaveBeenCalledOnce();
    expect(notify).toHaveBeenCalledOnce();
    expect(github.list).toHaveBeenCalledOnce();
  });

  it("emails notes without posting to Slack when email is the contact channel", async () => {
    const { app, slack, notify } = setup({ slackChannel: false });
    const response = await postJson(app, `${path}/submission`, {
      ...submission,
      contact_channel: "email",
    });

    expect(response.status).toBe(201);
    expect(slack.postNotes).not.toHaveBeenCalled();
    expect(notify).toHaveBeenCalledWith(
      expect.objectContaining({
        contactChannel: "email",
        slackChannel: null,
        notes: "We need help with our retrieval pipeline.",
      }),
    );
  });

  it("skips the Slack post for empty notes", async () => {
    const { app, slack, notify } = setup();

    expect(
      (
        await postJson(app, `${path}/submission`, {
          ...submission,
          notes: "   ",
        })
      ).status,
    ).toBe(201);
    expect(slack.postNotes).not.toHaveBeenCalled();
    expect(notify).toHaveBeenCalledWith(
      expect.objectContaining({ notes: null }),
    );
  });

  it("keeps the submission when only the Slack post fails", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const { app, slack, organizations } = setup();
    slack.postNotes.mockRejectedValueOnce(new Error("Slack down"));

    expect((await postJson(app, `${path}/submission`, submission)).status).toBe(
      201,
    );
    expect(organizations.submitOnboarding).toHaveBeenCalledOnce();
    expect(
      log.mock.calls
        .map(([line]) => JSON.parse(String(line)))
        .filter((line) => line.event === "engineer_onboarding_delivery_failed")
        .map((line) => line.dependency),
    ).toEqual(["slack"]);
  });

  it("records nothing when the team email fails, so a retry delivers it", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const other = { ...installation, id: 43, account: "other" };
    const { app, slack, notify, organizations } = setup({
      installations: [installation, other],
    });
    notify.mockRejectedValueOnce(new Error("Resend down"));

    const failed = await postJson(app, `${path}/submission`, submission);
    expect(failed.status).toBe(503);
    expect(organizations.submitOnboarding).not.toHaveBeenCalled();
    expect(organizations.releaseOnboardingSubmission).toHaveBeenCalledOnce();
    expect(slack.postNotes).not.toHaveBeenCalled();

    // The retry picks another account; only that one is announced.
    const retried = await postJson(app, `${path}/submission`, {
      ...submission,
      github_installation_id: 43,
    });
    expect(retried.status).toBe(201);
    expect(notify).toHaveBeenCalledTimes(2);
    expect(notify).toHaveBeenLastCalledWith(
      expect.objectContaining({ githubAccounts: ["other"] }),
    );
    expect(organizations.submitOnboarding).toHaveBeenCalledOnce();
    expect(slack.postNotes).toHaveBeenCalledOnce();
  });

  it("lets only one overlapping submission notify the team", async () => {
    const { app, notify, organizations } = setup();
    let finish = () => {};
    notify.mockImplementationOnce(
      () =>
        new Promise<undefined>(
          (resolve) => (finish = () => resolve(undefined)),
        ),
    );

    const first = postJson(app, `${path}/submission`, submission);
    await vi.waitFor(() => expect(notify).toHaveBeenCalledOnce());
    const second = await postJson(app, `${path}/submission`, submission);
    expect(second.status).toBe(409);
    expect(await second.json()).toMatchObject({
      code: "submission_in_progress",
    });

    finish();
    expect((await first).status).toBe(201);
    expect(notify).toHaveBeenCalledOnce();
    expect(organizations.submitOnboarding).toHaveBeenCalledOnce();

    const repeated = await postJson(app, `${path}/submission`, submission);
    expect(repeated.status).toBe(200);
    expect(notify).toHaveBeenCalledOnce();
  });

  it("starts the project without an NDA when none was requested", async () => {
    const { app, notify } = setup({ nda: false });
    const response = await postJson(app, `${path}/submission`, submission);

    expect(response.status).toBe(201);
    expect((await response.json()).nda).toBeNull();
    expect(notify).toHaveBeenCalledWith(
      expect.objectContaining({ ndaSignedAt: null }),
    );
  });

  it("records a requested NDA that PandaDoc completed", async () => {
    const { app, organizations } = setup({ nda: false });
    const response = await postJson(app, `${path}/submission`, {
      ...submission,
      nda_document_id: "test-document",
    });

    expect(response.status).toBe(201);
    expect(organizations.recordOnboardingNda).toHaveBeenCalledOnce();
  });

  it("does not start the project before a requested NDA is completed", async () => {
    const { app, organizations, notify } = setup({
      nda: false,
      ndaDocument: "ready",
    });
    const response = await postJson(app, `${path}/submission`, {
      ...submission,
      nda_document_id: "test-document",
    });

    expect(response.status).toBe(409);
    expect((await response.json()).code).toBe("nda_required");
    expect(organizations.submitOnboarding).not.toHaveBeenCalled();
    expect(notify).not.toHaveBeenCalled();
  });

  it.each([
    { options: { token: null }, code: "github_authorization_required" },
    { options: { installations: [] }, code: "github_installation_unverified" },
    {
      options: {
        installations: [
          { ...installation, repository_count: 0, repositories: [] },
        ],
      },
      code: "github_repositories_required",
    },
    { options: { slackChannel: false }, code: "slack_channel_required" },
  ])(
    "does not submit before every step is verified: $code",
    async ({ options, code }) => {
      const { app, organizations, notify, slack } = setup(options);
      const response = await postJson(app, `${path}/submission`, submission);

      expect(response.status).toBe(409);
      expect((await response.json()).code).toBe(code);
      expect(organizations.submitOnboarding).not.toHaveBeenCalled();
      expect(notify).not.toHaveBeenCalled();
      expect(slack.postNotes).not.toHaveBeenCalled();
    },
  );

  it("requires an organization admin", async () => {
    const { app, organizations } = setup({ role: "member" });

    expect((await postJson(app, `${path}/submission`, submission)).status).toBe(
      403,
    );
    expect(organizations.submitOnboarding).not.toHaveBeenCalled();
  });

  it.each([
    { ...submission, contact_channel: "phone" },
    { ...submission, github_installation_id: 0 },
    { ...submission, notes: "a".repeat(3001) },
    { ...submission, extra: true },
  ])("rejects an invalid submission", async (body) => {
    const { app } = setup();

    expect((await postJson(app, `${path}/submission`, body)).status).toBe(422);
  });
});

describe("local onboarding reset", () => {
  const reset = (app: ReturnType<typeof setup>["app"]) =>
    app.request(`${path}/submission`, { method: "DELETE" });

  it("does not exist outside local test mode", async () => {
    const { app, organizations } = setup();

    expect((await reset(app)).status).toBe(404);
    expect(organizations.resetOnboardingSubmission).not.toHaveBeenCalled();
  });

  it("lets an admin walk the journey again in test mode", async () => {
    const { app, organizations } = setup({ testMode: true });
    await postJson(app, `${path}/submission`, submission);

    expect((await reset(app)).status).toBe(204);
    expect((await (await app.request(path)).json()).submitted_at).toBeNull();
    expect(organizations.resetOnboardingSubmission).toHaveBeenCalledOnce();
  });

  it("requires an organization admin", async () => {
    const { app, organizations } = setup({ testMode: true, role: "member" });

    expect((await reset(app)).status).toBe(403);
    expect(organizations.resetOnboardingSubmission).not.toHaveBeenCalled();
  });
});
