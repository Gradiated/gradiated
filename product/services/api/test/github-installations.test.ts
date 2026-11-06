import { describe, expect, it, vi } from "vitest";
import { readGithubAccessToken } from "../src/auth/service.js";
import { createGithubInstallations } from "../src/github/installations.js";
import {
  authenticated,
  createTestApp,
  organizationId,
  organizationSummary,
  user,
} from "./support.js";
import {
  ndaProvider,
  onboardingOrganizations,
  recordedNda,
} from "./onboarding-support.js";

const installation = {
  id: 42,
  app_slug: "gradiated",
  account: { login: "example" },
  suspended_at: null,
  repository_selection: "selected",
  permissions: { contents: "read" },
};
const json = (body: unknown) => new Response(JSON.stringify(body));

describe("GitHub installation verification", () => {
  it("verifies an active app installation and repository access with the user's token", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ installations: [installation] }))
      .mockResolvedValueOnce(
        json({ total_count: 3, repositories: [{ id: 9 }] }),
      );
    expect(
      await createGithubInstallations(request).list("secret-user-token"),
    ).toEqual({
      status: "installed",
      installations: [
        {
          id: 42,
          account: "example",
          repository_selection: "selected",
          repository_count: 3,
        },
      ],
    });
    expect(String(request.mock.calls[1]?.[0])).toContain(
      "/user/installations/42/repositories",
    );
    expect(request.mock.calls[0]?.[1]?.headers).toMatchObject({
      Authorization: "Bearer secret-user-token",
    });
  });

  it.each([
    { ...installation, app_slug: "another-app" },
    { ...installation, suspended_at: "2026-01-01T00:00:00Z" },
    { ...installation, permissions: { metadata: "read" } },
  ])(
    "does not accept a foreign, suspended or underprivileged installation",
    async (candidate) => {
      const request = vi
        .fn<typeof fetch>()
        .mockResolvedValue(json({ installations: [candidate] }));
      expect(await createGithubInstallations(request).list("token")).toEqual({
        status: "not_installed",
        installations: [],
      });
      expect(request).toHaveBeenCalledOnce();
    },
  );

  it("keeps pending installation requests and zero-repository installations blocked", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ installations: [] }));
    expect(
      (await createGithubInstallations(request).list("token")).status,
    ).toBe("not_installed");
    request
      .mockResolvedValueOnce(json({ installations: [installation] }))
      .mockResolvedValueOnce(json({ total_count: 0, repositories: [] }));
    expect(
      (await createGithubInstallations(request).list("token")).status,
    ).toBe("not_installed");
  });

  it("rejects a forged installation ID not in the user's authorized installations", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(json({ installations: [installation] }));
    expect(
      (await createGithubInstallations(request).list("token", 999)).status,
    ).toBe("not_installed");
    expect(request).toHaveBeenCalledOnce();
  });

  it("uses safe errors for expired authorization and provider failures", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response("secret", { status: 401 }))
      .mockRejectedValueOnce(new Error("secret"));
    await expect(
      createGithubInstallations(request).list("secret"),
    ).rejects.toMatchObject({ problem: { status: 403 } });
    await expect(
      createGithubInstallations(request).list("secret"),
    ).rejects.toMatchObject({ problem: { status: 503 } });
  });
});

describe("GitHub access token", () => {
  const headers = new Headers();
  const api = (
    accounts: { id: string; providerId: string }[] | Error,
    token: { accessToken?: string } | Error = { accessToken: "user-token" },
  ) => ({
    listUserAccounts: vi.fn(async () => {
      if (accounts instanceof Error) throw accounts;

      return accounts;
    }),
    getAccessToken: vi.fn(async () => {
      if (token instanceof Error) throw token;

      return token;
    }),
  });

  it("asks for authorization only when no GitHub account is linked", async () => {
    const unlinked = api([{ id: "account-1", providerId: "google" }]);
    expect(await readGithubAccessToken(unlinked, headers)).toBeNull();
    expect(unlinked.getAccessToken).not.toHaveBeenCalled();

    const linked = api([{ id: "account-2", providerId: "github" }]);
    expect(await readGithubAccessToken(linked, headers)).toBe("user-token");
    expect(linked.getAccessToken).toHaveBeenCalledWith({
      headers,
      body: { accountId: "account-2" },
    });
  });

  it.each([
    api(new Error("database unavailable")),
    api(
      [{ id: "account-2", providerId: "github" }],
      new Error("refresh failed"),
    ),
  ])("surfaces account and refresh failures", async (failing) => {
    await expect(readGithubAccessToken(failing, headers)).rejects.toThrow();
  });

  it("rejects an ambiguous pair of linked GitHub accounts", async () => {
    await expect(
      readGithubAccessToken(
        api([
          { id: "account-1", providerId: "github" },
          { id: "account-2", providerId: "github" },
        ]),
        headers,
      ),
    ).rejects.toMatchObject({ problem: { status: 409 } });
  });
});

const url = `/api/v1/organizations/${organizationId}/github-installations?`;
const setup = (
  role: "admin" | "member" = "admin",
  ndaStatus = "recorded",
  token: string | null = "token",
) => {
  const list = vi.fn().mockResolvedValue({
    status: "installed",
    installations: [{ id: 42, account: "example", repository_count: 1 }],
  });
  const githubAccessToken = vi.fn().mockResolvedValue(token);
  const nda = ndaProvider(ndaStatus === "recorded" ? "completed" : ndaStatus);
  const app = createTestApp({
    auth: { ...authenticated, githubAccessToken },
    githubInstallations: { list },
    ndaDocuments: nda,
    services: {
      organizations: onboardingOrganizations(
        ndaStatus === "recorded" ? { nda: recordedNda } : {},
        { ...organizationSummary, role },
      ),
    },
  });
  return { app, list, githubAccessToken, read: nda.read };
};

describe("GitHub installation route", () => {
  it("does not connect a GitHub identity from an impersonated session", async () => {
    const githubAccessToken = vi.fn();
    const app = createTestApp({
      auth: {
        ...authenticated,
        githubAccessToken,
        resolveSession: async () => ({ ...user, impersonatedBy: "staff-user" }),
      },
    });
    expect((await app.request(url)).status).toBe(403);
    expect(githubAccessToken).not.toHaveBeenCalled();
  });
  it("uses the organization's recorded NDA", async () => {
    const { app, list, read } = setup();
    expect((await app.request(url + "&installation_id=42")).status).toBe(200);
    expect(read).not.toHaveBeenCalled();
    expect(list).toHaveBeenCalledWith("token", 42);
  });

  it("binds an unrecorded NDA to the signed-in organization admin", async () => {
    const { app, read } = setup("admin", "completed");
    expect(
      (await app.request(url + "&nda_document_id=test-document")).status,
    ).toBe(200);
    expect(read).toHaveBeenCalledWith(
      { userId: user.id, email: user.email, organizationId },
      "test-document",
    );
  });

  it("requires GitHub authorization without exposing a token to the browser", async () => {
    const { app, list } = setup("admin", "recorded", null);
    const result = await app.request(url);
    expect(await result.json()).toEqual({
      status: "authorization_required",
      installations: [],
    });
    expect(list).not.toHaveBeenCalled();
  });

  it.each([
    { role: "member" as const, nda: "recorded", status: 403 },
    { role: "admin" as const, nda: "ready", status: 409 },
  ])("does not call GitHub before admin and NDA checks pass", async (input) => {
    const { app, list, githubAccessToken } = setup(input.role, input.nda);
    expect((await app.request(url)).status).toBe(input.status);
    expect(list).not.toHaveBeenCalled();
    expect(githubAccessToken).not.toHaveBeenCalled();
  });

  it("reports a token lookup failure as unavailable instead of asking to reconnect", async () => {
    const { app, githubAccessToken, list } = setup();
    githubAccessToken.mockRejectedValueOnce(new Error("refresh failed"));
    expect((await app.request(url)).status).toBe(503);
    expect(list).not.toHaveBeenCalled();
  });

  it("fails closed when GitHub verification is not configured", async () => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        organizations: { listForUser: async () => [organizationSummary] },
      },
    });
    expect((await app.request(url)).status).toBe(503);
  });
});
