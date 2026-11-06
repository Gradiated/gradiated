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
  it("labels onboarding notes with their author and posts user text without interpreting mentions", async () => {
    const notes =
      "Please investigate <!channel> and <https://example.com|this link>.";
    const request = vi
      .fn<typeof fetch>()
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
      .mockResolvedValueOnce(response({ ok: true, ts: "123.456" }));
    await expect(
      createSlackConnect(configuration, request).postNotes({
        organizationId,
        channelName: channel.name,
        email: user.email,
        notes,
        requestId: organizationId,
      }),
    ).resolves.toEqual({ status: "sent" });
    const body = JSON.parse(String(request.mock.calls[1]?.[1]?.body));
    expect(body.channel).toBe(channel.id);
    expect(body.client_msg_id).toBe(organizationId);
    expect(body.blocks).toEqual([
      {
        type: "section",
        text: {
          type: "plain_text",
          text: `Notes submitted during Gradiated onboarding by ${user.email}`,
        },
      },
      { type: "section", text: { type: "plain_text", text: notes } },
    ]);
    expect(body.unfurl_links).toBe(false);
  });

  it("never posts notes to a channel belonging to another customer", async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValueOnce(
      response({
        ok: true,
        channels: [{ ...channel, purpose: { value: "Another customer" } }],
      }),
    );
    await expect(
      createSlackConnect(configuration, request).postNotes({
        organizationId,
        channelName: channel.name,
        email: user.email,
        notes: "Private context",
        requestId: organizationId,
      }),
    ).rejects.toMatchObject({ problem: { status: 403 } });
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("does not report notes as delivered when Slack rejects them", async () => {
    const request = vi
      .fn<typeof fetch>()
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
      .mockResolvedValueOnce(response({ ok: false, error: "missing_scope" }));
    await expect(
      createSlackConnect(configuration, request).postNotes({
        organizationId,
        channelName: channel.name,
        email: user.email,
        notes: "Context",
        requestId: organizationId,
      }),
    ).rejects.toMatchObject({ problem: { status: 503 } });
    expect(request).toHaveBeenCalledTimes(2);
  });
  it("can retry a collision with a different name without sharing the unrelated channel", async () => {
    const replacement = { ...channel, name: "ext-example-team-gradiated" };
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response({ ok: false, error: "name_taken" }))
      .mockResolvedValueOnce(
        response({
          ok: true,
          channels: [{ ...channel, purpose: { value: "Another customer" } }],
        }),
      )
      .mockResolvedValueOnce(response({ ok: true, channel: replacement }))
      .mockResolvedValueOnce(response({ ok: true }))
      .mockResolvedValueOnce(response({ ok: true }))
      .mockResolvedValueOnce(response({ ok: true, invite_id: "I123456" }));
    const provider = createSlackConnect(configuration, request);
    await expect(provider.invite(input)).rejects.toMatchObject({
      problem: { status: 409 },
    });
    expect(request).toHaveBeenCalledTimes(2);

    await expect(
      provider.invite({ ...input, channelName: replacement.name }),
    ).resolves.toMatchObject({ channel_name: replacement.name });
    expect(JSON.parse(String(request.mock.calls[2]?.[1]?.body))).toEqual({
      name: replacement.name,
      is_private: false,
    });
  });

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
    impersonated?: boolean;
  } = {},
) => {
  const slackConnect = {
    postNotes: vi.fn().mockResolvedValue({ status: "sent" }),
    invite: vi.fn().mockResolvedValue({
      channel_id: channel.id,
      channel_name: channel.name,
      email: user.email,
      status: "invited",
    }),
  };
  const ndaDocuments = nda(options.status);
  const app = createTestApp({
    auth: options.impersonated
      ? {
          ...authenticated,
          resolveSession: async () => ({ ...user, impersonatedBy: user.id }),
        }
      : authenticated,
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
  it("posts onboarding notes using authenticated author identity after verifying the NDA", async () => {
    const { app, slackConnect, ndaDocuments } = setup();
    const result = await postJson(
      app,
      `/api/v1/organizations/${organizationId}/slack-messages`,
      {
        nda_document_id: "test-document",
        channel_name: channel.name,
        notes: "  Useful context  ",
        request_id: organizationId,
      },
    );
    expect(result.status).toBe(201);
    expect(slackConnect.postNotes).toHaveBeenCalledWith({
      organizationId,
      email: user.email,
      channelName: channel.name,
      notes: "Useful context",
      requestId: organizationId,
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
    { impersonated: true, expected: 403 },
  ])(
    "blocks onboarding notes without authorization or completed NDA: %j",
    async ({ expected, ...options }) => {
      const { app, slackConnect } = setup(options);
      expect(
        (
          await postJson(
            app,
            `/api/v1/organizations/${organizationId}/slack-messages`,
            {
              nda_document_id: "test-document",
              channel_name: channel.name,
              notes: "Context",
              request_id: organizationId,
            },
          )
        ).status,
      ).toBe(expected);
      expect(slackConnect.postNotes).not.toHaveBeenCalled();
    },
  );

  it.each(["", " ", "a".repeat(3001)])(
    "rejects empty or oversized onboarding notes",
    async (notes) => {
      const { app, slackConnect } = setup();
      expect(
        (
          await postJson(
            app,
            `/api/v1/organizations/${organizationId}/slack-messages`,
            {
              nda_document_id: "test-document",
              channel_name: channel.name,
              notes,
              request_id: organizationId,
            },
          )
        ).status,
      ).toBe(422);
      expect(slackConnect.postNotes).not.toHaveBeenCalled();
    },
  );
  it("passes a proposed replacement channel name to the provider", async () => {
    const { app, slackConnect } = setup();
    const result = await postJson(app, collection, {
      nda_document_id: "test-document",
      channel_name: "ext-example-team-gradiated",
    });
    expect(result.status).toBe(201);
    expect(slackConnect.invite).toHaveBeenCalledWith({
      ...input,
      company: organizationSummary.name,
      channelName: "ext-example-team-gradiated",
    });
  });

  it.each([
    "general",
    "ext-Example-gradiated",
    "ext-example_other-gradiated",
    `ext-${"a".repeat(70)}-gradiated`,
  ])("rejects an invalid replacement channel: %s", async (channel_name) => {
    const { app, slackConnect } = setup();
    expect(
      (
        await postJson(app, collection, {
          nda_document_id: "test-document",
          channel_name,
        })
      ).status,
    ).toBe(422);
    expect(slackConnect.invite).not.toHaveBeenCalled();
  });

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
    { impersonated: true, expected: 403 },
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

  it("invites the chosen Slack email while verifying the NDA with the signed-in signer", async () => {
    const { app, slackConnect, ndaDocuments } = setup();
    expect(
      (
        await postJson(app, collection, {
          nda_document_id: "test-document",
          email: "  Other@Example.com  ",
        })
      ).status,
    ).toBe(201);
    expect(slackConnect.invite).toHaveBeenCalledWith({
      organizationId,
      company: organizationSummary.name,
      email: "other@example.com",
    });
    expect(ndaDocuments.read).toHaveBeenCalledWith(
      { organizationId, userId: user.id, email: user.email },
      "test-document",
    );
  });

  it.each(["", "not-an-email", "a".repeat(201) + "@example.com"])(
    "rejects an invalid Slack recipient: %s",
    async (email) => {
      const { app, slackConnect } = setup();
      expect(
        (
          await postJson(app, collection, {
            nda_document_id: "test-document",
            email,
          })
        ).status,
      ).toBe(422);
      expect(slackConnect.invite).not.toHaveBeenCalled();
    },
  );
});
