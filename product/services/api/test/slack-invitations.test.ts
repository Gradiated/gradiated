import { describe, expect, it, vi } from "vitest";
import { createSlackConnect, slackChannelName } from "../src/slack/connect.js";
import {
  authenticated,
  createTestApp,
  organizationId,
  organizationSummary,
  postJson,
  user,
} from "./support.js";
import type { PandaDocNda } from "../src/legal/pandadoc.js";

const channel = { id: "C123456", name: "ext-example-gradiated" };
const input = { organizationId, company: "Example", email: user.email };
const response = (value: unknown) => new Response(JSON.stringify(value));
const configuration = {
  token: "secret-test-token",
  engineerUserIds: ["U123456"],
};
const ready = () =>
  vi
    .fn<typeof fetch>()
    .mockResolvedValueOnce(response({ ok: true, channel }))
    .mockResolvedValueOnce(response({ ok: true }))
    .mockResolvedValueOnce(response({ ok: true }))
    .mockResolvedValueOnce(response({ ok: true, invite_id: "I123456" }));

describe("Slack Connect", () => {
  it("creates a public organization-bound channel, adds the engineer, and invites the verified email", async () => {
    const request = ready();
    expect(
      await createSlackConnect(configuration, request).invite(input),
    ).toMatchObject({
      channel_name: channel.name,
      email: user.email,
      status: "invited",
    });
    expect(
      request.mock.calls.map(([url]) => String(url).split("/").at(-1)),
    ).toEqual([
      "conversations.create",
      "conversations.setPurpose",
      "conversations.invite",
      "conversations.inviteShared",
    ]);
    expect(JSON.parse(String(request.mock.calls[0]?.[1]?.body))).toEqual({
      name: channel.name,
      is_private: false,
    });
    expect(JSON.parse(String(request.mock.calls[1]?.[1]?.body))).toEqual({
      channel: channel.id,
      purpose: `Gradiated customer organization: ${organizationId}`,
    });
    expect(JSON.parse(String(request.mock.calls[3]?.[1]?.body))).toEqual({
      channel: channel.id,
      emails: [user.email],
      external_limited: true,
    });
  });

  it("reuses only the channel marked for this organization on retry", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response({ ok: false, error: "name_taken" }))
      .mockResolvedValueOnce(
        response({
          ok: true,
          channels: [
            {
              ...channel,
              purpose: {
                value: `Gradiated customer organization: ${organizationId}`,
              },
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        response({ ok: false, error: "already_in_channel" }),
      )
      .mockResolvedValueOnce(response({ ok: true, invite_id: "I123456" }));
    await expect(
      createSlackConnect(configuration, request).invite(input),
    ).resolves.toMatchObject({ status: "invited" });
    expect(request.mock.calls[1]?.[1]?.method).toBe("GET");
    expect(
      new URL(String(request.mock.calls[1]?.[0])).searchParams.get("types"),
    ).toBe("public_channel");
  });

  it("does not reuse a private channel even if it carries the organization marker", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response({ ok: false, error: "name_taken" }))
      .mockResolvedValueOnce(
        response({
          ok: true,
          channels: [
            {
              ...channel,
              is_private: true,
              purpose: {
                value: `Gradiated customer organization: ${organizationId}`,
              },
            },
          ],
        }),
      );

    await expect(
      createSlackConnect(configuration, request).invite(input),
    ).rejects.toMatchObject({ problem: { status: 409 } });
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("does not invite anyone to a colliding channel belonging to another customer", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response({ ok: false, error: "name_taken" }))
      .mockResolvedValueOnce(
        response({
          ok: true,
          channels: [{ ...channel, purpose: { value: "Another customer" } }],
        }),
      );
    await expect(
      createSlackConnect(configuration, request).invite(input),
    ).rejects.toMatchObject({ problem: { status: 409 } });
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("does not report a restricted or failed invitation as sent", async () => {
    const request = ready();
    request
      .mockReset()
      .mockResolvedValueOnce(response({ ok: true, channel }))
      .mockResolvedValueOnce(response({ ok: true }))
      .mockResolvedValueOnce(response({ ok: true }))
      .mockResolvedValueOnce(
        response({ ok: false, error: "restricted_action" }),
      );
    await expect(
      createSlackConnect(configuration, request).invite(input),
    ).rejects.toMatchObject({ problem: { status: 503 } });
  });

  it("does not retry an uncertain mutation or expose Slack response bodies", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new Error(configuration.token));
    await expect(
      createSlackConnect(configuration, request).invite(input),
    ).rejects.not.toHaveProperty("message", configuration.token);
    expect(request).toHaveBeenCalledOnce();
  });

  it("normalizes company names to Slack's 80-character channel limit", () => {
    expect(slackChannelName("Acme, Inc.")).toBe("ext-acme-inc-gradiated");
    expect(slackChannelName("😀")).toBe("ext-customer-gradiated");
    expect(slackChannelName("x".repeat(200))).toHaveLength(80);
  });
});

const collection = `/api/v1/organizations/${organizationId}/slack-invitations`;
const nda = (status = "completed") =>
  ({ read: vi.fn().mockResolvedValue({ status }) }) as unknown as PandaDocNda;
const setup = (
  options: {
    role?: "admin" | "member";
    status?: string;
    configured?: boolean;
  } = {},
) => {
  const slackConnect = {
    invite: vi.fn().mockResolvedValue({
      channel_id: channel.id,
      channel_name: channel.name,
      email: user.email,
      status: "invited",
    }),
  };
  const ndaDocuments = nda(options.status);
  const app = createTestApp({
    auth: authenticated,
    slackConnect: options.configured === false ? undefined : slackConnect,
    ndaDocuments,
    services: {
      organizations: {
        listForUser: async () => [
          { ...organizationSummary, role: options.role ?? "admin" },
        ],
      },
    },
  });
  return { app, slackConnect, ndaDocuments };
};

describe("Slack invitation route", () => {
  it("derives the company and email from authenticated membership, after verifying the NDA", async () => {
    const { app, slackConnect, ndaDocuments } = setup();
    const result = await postJson(app, collection, {
      nda_document_id: "test-document",
    });
    expect(result.status).toBe(201);
    expect(slackConnect.invite).toHaveBeenCalledWith({
      organizationId,
      company: organizationSummary.name,
      email: user.email,
    });
    expect(ndaDocuments.read).toHaveBeenCalledWith(
      { organizationId, userId: user.id, email: user.email },
      "test-document",
    );
  });

  it.each([
    { role: "member" as const, expected: 403 },
    { status: "ready", expected: 409 },
    { configured: false, expected: 503 },
  ])(
    "does not send when authorization or setup is incomplete: %j",
    async ({ expected, ...options }) => {
      const { app, slackConnect } = setup(options);
      expect(
        (await postJson(app, collection, { nda_document_id: "test-document" }))
          .status,
      ).toBe(expected);
      expect(slackConnect.invite).not.toHaveBeenCalled();
    },
  );

  it("rejects arbitrary recipient emails", async () => {
    const { app, slackConnect } = setup();
    expect(
      (
        await postJson(app, collection, {
          nda_document_id: "test-document",
          email: "other@example.com",
        })
      ).status,
    ).toBe(422);
    expect(slackConnect.invite).not.toHaveBeenCalled();
  });
});
