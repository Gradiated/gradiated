import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it } from "vitest";

import type { InvitationMessage } from "../src/email/invitation.js";
import {
  authenticated,
  createTestApp,
  expectProblem,
  failWith,
  organizationId,
  organizationSummary,
  postJson,
  user,
  validationProblem,
} from "./support.js";

const memberId = "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b8f";
const invitationId = "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b90";
const token = "a".repeat(43);
const joinedAt = new Date("2026-10-01T12:00:00.000Z");
const invitation = {
  id: invitationId,
  organizationId,
  email: "morgan@acme.com",
  role: "member" as const,
  invitedByEmail: user.email,
  expiresAt: new Date("2026-10-08T12:00:00.000Z"),
  createdAt: joinedAt,
};
const base = `/api/v1/organizations/${organizationId}`;

const request = (
  app: ReturnType<typeof createTestApp>,
  method: string,
  path: string,
  body?: unknown,
) =>
  app.request(path, {
    method,
    ...(body === undefined
      ? {}
      : {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
  });

describe("member routes", () => {
  it("lists members by email", async () => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        members: {
          listMembers: async () => [
            { userId: user.id, email: user.email, role: "admin", joinedAt },
          ],
        },
      },
    });

    const response = await app.request(`${base}/members`);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      data: [
        {
          user_id: user.id,
          email: user.email,
          role: "admin",
          joined_at: joinedAt.toISOString(),
        },
      ],
      next_cursor: null,
    });
  });

  it("changes a role and removes a member", async () => {
    const calls: unknown[] = [];
    const app = createTestApp({
      auth: authenticated,
      services: {
        members: {
          updateMember: async (...args) => {
            calls.push(["update", ...args]);
            return {
              userId: memberId,
              email: "sam@acme.com",
              role: "admin",
              joinedAt,
            };
          },
          removeMember: async (...args) => {
            calls.push(["remove", ...args]);
          },
        },
      },
    });

    const updated = await request(app, "PATCH", `${base}/members/${memberId}`, {
      role: "admin",
    });
    const removed = await request(app, "DELETE", `${base}/members/${memberId}`);

    expect(updated.status).toBe(200);
    await expect(updated.json()).resolves.toMatchObject({ role: "admin" });
    expect(removed.status).toBe(204);
    expect(calls).toEqual([
      ["update", user.id, organizationId, memberId, { role: "admin" }],
      ["remove", user.id, organizationId, memberId],
    ]);
  });

  it.each([{ role: "owner" }, { role: "billing" }, {}])(
    "rejects the role update %j",
    async (body) => {
      const response = await request(
        createTestApp({ auth: authenticated }),
        "PATCH",
        `${base}/members/${memberId}`,
        body,
      );

      await expectProblem(response, validationProblem);
    },
  );

  it("maps a refused self-change to 403", async () => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        members: {
          removeMember: failWith(
            new ControlServiceError("forbidden", "Not yourself."),
          ),
        },
      },
    });

    const response = await request(
      app,
      "DELETE",
      `${base}/members/${memberId}`,
    );

    await expectProblem(response, {
      status: 403,
      code: "forbidden",
      type: "forbidden",
    });
  });
});

describe("invitation routes", () => {
  it("normalizes addresses, emails each invitation and returns them", async () => {
    const received: unknown[] = [];
    const sent: InvitationMessage[] = [];
    const app = createTestApp({
      auth: authenticated,
      consoleUrl: "https://console.example.com",
      sendInvitation: async (message) => {
        sent.push(message);
      },
      services: {
        members: {
          createInvitations: async (_userId, _organizationId, input) => {
            received.push(input);
            return [
              { invitation, organizationName: "Acme", token: "secret-token" },
            ];
          },
        },
      },
    });

    const response = await postJson(app, `${base}/invitations`, {
      emails: [" Morgan@Acme.com "],
      role: "member",
    });

    expect(response.status).toBe(201);
    expect(received).toEqual([{ emails: ["morgan@acme.com"], role: "member" }]);
    expect(sent).toEqual([
      {
        email: "morgan@acme.com",
        invitedByEmail: user.email,
        organizationName: "Acme",
        role: "member",
        url: "https://console.example.com/invitations/accept?token=secret-token",
      },
    ]);
    await expect(response.json()).resolves.toMatchObject({
      data: [{ id: invitationId, email: "morgan@acme.com", role: "member" }],
    });
  });

  it.each([
    { emails: [], role: "member" },
    { emails: ["not-an-email"], role: "member" },
    {
      emails: Array.from({ length: 21 }, (_, i) => `p${i}@acme.com`),
      role: "member",
    },
    { emails: ["a@acme.com"], role: "owner" },
  ])("rejects the invitation request %#", async (body) => {
    const response = await postJson(
      createTestApp({ auth: authenticated }),
      `${base}/invitations`,
      body,
    );

    await expectProblem(response, validationProblem);
  });

  it("reports failed deliveries after saving every invitation", async () => {
    const attempted: string[] = [];
    const app = createTestApp({
      auth: authenticated,
      sendInvitation: async ({ email }) => {
        attempted.push(email);
        if (email === "morgan@acme.com") throw new Error("Resend is down");
      },
      services: {
        members: {
          createInvitations: async () => [
            { invitation, organizationName: "Acme", token: "one" },
            {
              invitation: { ...invitation, email: "casey@acme.com" },
              organizationName: "Acme",
              token: "two",
            },
          ],
        },
      },
    });

    const response = await postJson(app, `${base}/invitations`, {
      emails: ["morgan@acme.com", "casey@acme.com"],
      role: "member",
    });

    expect(attempted).toEqual(["morgan@acme.com", "casey@acme.com"]);
    await expectProblem(response, {
      status: 503,
      code: "unavailable",
      type: "unavailable",
    });
  });

  it("maps invitations for existing members to 409", async () => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        members: {
          createInvitations: failWith(
            new ControlServiceError("conflict", "Already a member."),
          ),
        },
      },
    });

    const response = await postJson(app, `${base}/invitations`, {
      emails: ["sam@acme.com"],
      role: "member",
    });

    await expectProblem(response, {
      status: 409,
      code: "conflict",
      type: "conflict",
    });
  });

  it("resends and revokes", async () => {
    const sent: InvitationMessage[] = [];
    const app = createTestApp({
      auth: authenticated,
      sendInvitation: async (message) => {
        sent.push(message);
      },
      services: {
        members: {
          resendInvitation: async () => ({
            invitation,
            organizationName: "Acme",
            token: "fresh",
          }),
          revokeInvitation: async () => undefined,
        },
      },
    });

    const resent = await request(
      app,
      "POST",
      `${base}/invitations/${invitationId}/resend`,
    );
    const revoked = await request(
      app,
      "DELETE",
      `${base}/invitations/${invitationId}`,
    );

    expect(resent.status).toBe(200);
    expect(sent.map((message) => message.url)).toEqual([
      expect.stringContaining("token=fresh"),
    ]);
    expect(revoked.status).toBe(204);
  });

  it("reports a failed resend as unavailable", async () => {
    const app = createTestApp({
      auth: authenticated,
      sendInvitation: async () => {
        throw new Error("Resend is down");
      },
      services: {
        members: {
          resendInvitation: async () => ({
            invitation,
            organizationName: "Acme",
            token: "fresh",
          }),
        },
      },
    });

    const response = await request(
      app,
      "POST",
      `${base}/invitations/${invitationId}/resend`,
    );

    await expectProblem(response, {
      status: 503,
      code: "unavailable",
      type: "unavailable",
    });
  });

  it("previews a token without a session", async () => {
    const app = createTestApp({
      services: {
        members: { previewInvitation: async () => ({ status: "invalid" }) },
      },
    });

    const response = await postJson(app, "/api/v1/invitations/preview", {
      token,
    });

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ status: "invalid" });
  });

  it("accepts for the signed-in user and returns the joined organization", async () => {
    const accepted: unknown[] = [];
    const app = createTestApp({
      auth: authenticated,
      services: {
        members: {
          acceptInvitation: async (acceptor, value) => {
            accepted.push([acceptor.email, value]);
            return { organizationId };
          },
        },
        organizations: {
          listForUser: async () => [{ ...organizationSummary, role: "member" }],
        },
      },
    });

    const response = await postJson(app, "/api/v1/invitations/accept", {
      token,
    });

    expect(response.status).toBe(200);
    expect(accepted).toEqual([[user.email, token]]);
    await expect(response.json()).resolves.toMatchObject({
      id: organizationId,
      role: "member",
    });
  });

  it("rejects malformed tokens", async () => {
    const response = await postJson(
      createTestApp({ auth: authenticated }),
      "/api/v1/invitations/accept",
      { token: "short" },
    );

    await expectProblem(response, validationProblem);
  });
});
