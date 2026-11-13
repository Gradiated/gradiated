import { afterEach, describe, expect, it, vi } from "vitest";

import { createSlackConnect, slackChannelName } from "../src/slack/connect.js";
import {
  inviteToSlack,
  SlackInvitationCooldown,
} from "../src/slack/invitations.js";
import {
  memoryIntegrations,
  onboardingOrganizations,
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

const channel = { id: "C123456", name: "ext-example-gradiated" };
const response = (value: unknown) => new Response(JSON.stringify(value));
const configuration = {
  token: "secret-test-token",
  engineerUserIds: ["U123456"],
};
const slackMethod = (url: unknown) =>
  new URL(String(url)).pathname.split("/").at(-1)!;
const methods = (request: { mock: { calls: unknown[][] } }) =>
  request.mock.calls.map(([url]) => slackMethod(url));
const logLines = (log: { mock: { calls: unknown[][] } }) =>
  log.mock.calls.map(([line]) => JSON.parse(String(line)));
const slackApi = (
  replies: Record<string, unknown>,
  fallback: unknown = { ok: true },
) =>
  vi.fn<typeof fetch>(async (url) => {
    const reply = replies[slackMethod(url)] ?? fallback;
    if (reply instanceof Error) throw reply;

    return response(reply);
  });

afterEach(() => vi.restoreAllMocks());

describe("Slack Connect", () => {
  it("reads a stored channel with a GET and ignores archived or missing channels", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response({ ok: true, channel }))
      .mockResolvedValueOnce(
        response({ ok: true, channel: { ...channel, is_archived: true } }),
      )
      .mockResolvedValueOnce(
        response({ ok: false, error: "channel_not_found" }),
      );
    const slack = createSlackConnect(configuration, request);

    expect(await slack.findChannel(channel.id)).toMatchObject(channel);
    expect(await slack.findChannel(channel.id)).toBeUndefined();
    expect(await slack.findChannel(channel.id)).toBeUndefined();
    expect(request.mock.calls[0]?.[1]?.method).toBe("GET");
    expect(
      new URL(String(request.mock.calls[0]?.[0])).searchParams.get("channel"),
    ).toBe(channel.id);
  });

  it("creates a public channel and reports a taken name without logging it", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response({ ok: true, channel }))
      .mockResolvedValueOnce(response({ ok: false, error: "name_taken" }));
    const slack = createSlackConnect(configuration, request);

    expect(await slack.createChannel(channel.name)).toEqual({
      status: "created",
      channel,
    });
    expect(JSON.parse(String(request.mock.calls[0]?.[1]?.body))).toEqual({
      name: channel.name,
      is_private: false,
    });
    expect(await slack.createChannel(channel.name)).toEqual({
      status: "name_taken",
    });
    expect(log).not.toHaveBeenCalled();
  });

  it("treats the channel purpose as a label whose failure does not throw", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const request = vi.fn<typeof fetch>().mockRejectedValue(new Error("down"));

    await expect(
      createSlackConnect(configuration, request).labelChannel(
        channel.id,
        organizationId,
      ),
    ).resolves.toBeUndefined();
    expect(JSON.parse(String(request.mock.calls[0]?.[1]?.body))).toEqual({
      channel: channel.id,
      purpose: `Gradiated customer organization: ${organizationId}`,
    });
  });

  it("adds the engineers and sends a limited Slack Connect invitation", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response({ ok: true }))
      .mockResolvedValueOnce(response({ ok: true, invite_id: "I123456" }));

    expect(
      await createSlackConnect(configuration, request).inviteMembers(
        channel.id,
        user.email,
      ),
    ).toBe("invited");
    expect(methods(request)).toEqual([
      "conversations.invite",
      "conversations.inviteShared",
    ]);
    expect(JSON.parse(String(request.mock.calls[1]?.[1]?.body))).toEqual({
      channel: channel.id,
      emails: [user.email],
      external_limited: true,
    });
  });

  it("reports an existing member as joined", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockImplementation(async () =>
        response({ ok: false, error: "already_in_channel" }),
      );

    expect(
      await createSlackConnect(configuration, request).inviteMembers(
        channel.id,
        user.email,
      ),
    ).toBe("joined");
  });

  it("logs Slack's error code without the response body or token", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response({ ok: true }))
      .mockResolvedValueOnce(
        response({
          ok: false,
          error: "restricted_action",
          detail: "private workspace detail",
        }),
      );
    await expect(
      createSlackConnect(configuration, request).inviteMembers(
        channel.id,
        user.email,
      ),
    ).rejects.toMatchObject({ problem: { status: 503 } });

    const lines = logLines(log);
    expect(lines).toEqual([
      expect.objectContaining({
        level: "warn",
        event: "provider_request_failed",
        dependency: "slack",
        route: "conversations.inviteShared",
        reason: "restricted_action",
      }),
    ]);
    expect(JSON.stringify(lines)).not.toContain("private workspace detail");
    expect(JSON.stringify(lines)).not.toContain(configuration.token);
  });

  it("logs Slack HTTP failures by status", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("upstream body", { status: 502 }));
    await expect(
      createSlackConnect(configuration, request).createChannel(channel.name),
    ).rejects.toMatchObject({ problem: { status: 503 } });

    expect(logLines(log)[0]).toMatchObject({
      dependency: "slack",
      reason: "http_error",
      status: 502,
    });
  });

  it("posts notes as plain text with their author into the given channel", async () => {
    const notes =
      "Please investigate <!channel> and <https://example.com|this link>.";
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(response({ ok: true, ts: "123.456" }));
    await expect(
      createSlackConnect(configuration, request).postNotes({
        channelId: channel.id,
        email: user.email,
        notes,
        requestId: organizationId,
      }),
    ).resolves.toEqual({ status: "sent" });

    expect(JSON.parse(String(request.mock.calls[0]?.[1]?.body))).toMatchObject({
      channel: channel.id,
      client_msg_id: organizationId,
      unfurl_links: false,
      blocks: [
        {
          type: "section",
          text: {
            type: "plain_text",
            text: `Notes submitted during Gradiated onboarding by ${user.email}`,
          },
        },
        { type: "section", text: { type: "plain_text", text: notes } },
      ],
    });
  });

  it("does not report rejected notes as delivered", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(response({ ok: false, error: "not_in_channel" }));

    await expect(
      createSlackConnect(configuration, request).postNotes({
        channelId: channel.id,
        email: user.email,
        notes: "Context",
        requestId: organizationId,
      }),
    ).rejects.toMatchObject({ problem: { status: 503 } });
  });

  it("does not retry an uncertain mutation or expose the token", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const request = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new Error(configuration.token));
    await expect(
      createSlackConnect(configuration, request).createChannel(channel.name),
    ).rejects.not.toHaveProperty("message", configuration.token);
    expect(request).toHaveBeenCalledOnce();
  });

  it("normalizes company names to Slack's 80-character channel limit", () => {
    expect(slackChannelName("Acme, Inc.")).toBe("ext-acme-inc-gradiated");
    expect(slackChannelName("😀")).toBe("ext-customer-gradiated");
    expect(slackChannelName("x".repeat(200))).toHaveLength(80);
  });
});

const invitation = {
  userId: user.id,
  organizationId,
  company: "Example",
  email: user.email,
};

describe("Slack invitation ownership", () => {
  it("stores the created channel before labelling it, then invites and activates it", async () => {
    const order: string[] = [];
    const request = vi.fn<typeof fetch>(async (url) => {
      order.push(slackMethod(url));

      return response(
        slackMethod(url) === "conversations.create"
          ? { ok: true, channel }
          : { ok: true, invite_id: "I1" },
      );
    });
    const { service, rows } = memoryIntegrations();
    const record = service.recordSlackChannel.getMockImplementation()!;
    service.recordSlackChannel.mockImplementationOnce(async (...args) => {
      order.push("record");

      return record(...args);
    });

    await expect(
      inviteToSlack(
        createSlackConnect(configuration, request),
        service,
        invitation,
      ),
    ).resolves.toEqual({
      channel_id: channel.id,
      channel_name: channel.name,
      email: user.email,
      status: "invited",
    });
    expect(order).toEqual([
      "conversations.create",
      "record",
      "conversations.setPurpose",
      "conversations.invite",
      "conversations.inviteShared",
    ]);
    expect(rows).toEqual([
      expect.objectContaining({
        externalId: channel.id,
        status: "active",
        settings: expect.objectContaining({ invited_email: user.email }),
      }),
    ]);
  });

  it("keeps the stored channel when setting its purpose fails", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const request = slackApi({
      "conversations.create": { ok: true, channel },
      "conversations.setPurpose": new Error("network down"),
      "conversations.inviteShared": { ok: true, invite_id: "I1" },
    });
    const { service, rows } = memoryIntegrations();

    await expect(
      inviteToSlack(
        createSlackConnect(configuration, request),
        service,
        invitation,
      ),
    ).resolves.toMatchObject({ channel_id: channel.id, status: "invited" });
    expect(rows).toEqual([
      expect.objectContaining({ externalId: channel.id, status: "active" }),
    ]);
  });

  it("re-invites into the stored channel and ignores a requested name, whatever its purpose says", async () => {
    const request = slackApi({
      "conversations.info": {
        ok: true,
        channel: { ...channel, purpose: { value: "Another customer" } },
      },
      "conversations.inviteShared": { ok: true, invite_id: "I1" },
    });
    const { service } = memoryIntegrations([slackRecord()]);

    await expect(
      inviteToSlack(createSlackConnect(configuration, request), service, {
        ...invitation,
        email: "other@example.com",
        channelName: "ext-something-else-gradiated",
      }),
    ).resolves.toMatchObject({
      channel_id: channel.id,
      channel_name: channel.name,
      email: "other@example.com",
    });
    expect(methods(request)).toEqual([
      "conversations.info",
      "conversations.invite",
      "conversations.inviteShared",
    ]);
    expect(service.recordSlackChannel).not.toHaveBeenCalled();
  });

  it("does not adopt a colliding channel even when its purpose names this organization", async () => {
    const request = slackApi({
      "conversations.create": { ok: false, error: "name_taken" },
    });
    const { service } = memoryIntegrations();

    await expect(
      inviteToSlack(
        createSlackConnect(configuration, request),
        service,
        invitation,
      ),
    ).rejects.toMatchObject({
      problem: { status: 409, code: "slack_channel_name_taken" },
    });
    expect(methods(request)).toEqual(["conversations.create"]);
    expect(service.recordSlackChannel).not.toHaveBeenCalled();
  });

  it("replaces a stored channel that Slack archived", async () => {
    const request = slackApi({
      "conversations.info": {
        ok: true,
        channel: { ...channel, is_archived: true },
      },
      "conversations.create": {
        ok: true,
        channel: { id: "C999999", name: channel.name },
      },
      "conversations.inviteShared": { ok: true, invite_id: "I1" },
    });
    const { service, rows } = memoryIntegrations([slackRecord()]);

    await expect(
      inviteToSlack(
        createSlackConnect(configuration, request),
        service,
        invitation,
      ),
    ).resolves.toMatchObject({ channel_id: "C999999" });
    expect(rows.map((row) => [row.externalId, row.status])).toEqual([
      ["C123456", "revoked"],
      ["C999999", "active"],
    ]);
  });

  it("does not invite again during the organization's cooldown", async () => {
    const slack = {
      findChannel: vi.fn(async () => channel),
      inviteMembers: vi.fn(),
    };
    const { service } = memoryIntegrations([slackRecord()]);
    const availableAt = new Date(now.getTime() + 60_000);
    service.claimSlackInvitation.mockResolvedValueOnce({
      claimed: false,
      availableAt,
    } as never);

    await expect(
      inviteToSlack(slack as never, service, invitation),
    ).rejects.toEqual(new SlackInvitationCooldown(availableAt));
    expect(slack.inviteMembers).not.toHaveBeenCalled();
  });

  it("releases the cooldown when Slack rejects the invitation", async () => {
    const slack = {
      findChannel: vi.fn(async () => channel),
      inviteMembers: vi.fn(async () => {
        throw new Error("Slack down");
      }),
    };
    const { service } = memoryIntegrations([
      slackRecord({ status: "pending" }),
    ]);

    await expect(
      inviteToSlack(slack as never, service, invitation),
    ).rejects.toThrow("Slack down");
    expect(service.releaseSlackInvitation).toHaveBeenCalledOnce();
    expect(service.activate).not.toHaveBeenCalled();
  });
});

const collection = `/api/v1/organizations/${organizationId}/slack-invitations`;
const setup = (
  options: {
    role?: "admin" | "member";
    configured?: boolean;
    impersonated?: boolean;
  } = {},
) => {
  const organizations = onboardingOrganizations(
    {},
    { ...organizationSummary, role: options.role ?? "admin" },
  );
  const slackConnect = {
    findChannel: vi.fn(async () => channel),
    createChannel: vi.fn(async () => ({
      status: "created" as const,
      channel,
    })),
    labelChannel: vi.fn(async () => undefined),
    inviteMembers: vi.fn(async () => "invited" as const),
    postNotes: vi.fn(),
  };
  const { service: integrations } = memoryIntegrations();
  const app = createTestApp({
    auth: options.impersonated
      ? {
          ...authenticated,
          resolveSession: async () => ({ ...user, impersonatedBy: user.id }),
        }
      : authenticated,
    slackConnect:
      options.configured === false ? undefined : (slackConnect as never),
    services: { organizations, integrations },
  });

  return { app, slackConnect, organizations, integrations };
};

describe("Slack invitation route", () => {
  it("derives the company and email from the session without an NDA", async () => {
    const { app, slackConnect } = setup();
    const result = await postJson(app, collection, {});

    expect(result.status).toBe(201);
    expect(await result.json()).toEqual({
      channel_id: channel.id,
      channel_name: channel.name,
      email: user.email,
      status: "invited",
    });
    expect(slackConnect.createChannel).toHaveBeenCalledWith(
      slackChannelName(organizationSummary.name),
    );
    expect(slackConnect.inviteMembers).toHaveBeenCalledWith(
      channel.id,
      user.email,
    );
  });

  it("invites a chosen Slack email and passes a proposed channel name", async () => {
    const { app, slackConnect } = setup();

    expect(
      (
        await postJson(app, collection, {
          email: "  Other@Example.com  ",
          channel_name: "ext-example-team-gradiated",
        })
      ).status,
    ).toBe(201);
    expect(slackConnect.createChannel).toHaveBeenCalledWith(
      "ext-example-team-gradiated",
    );
    expect(slackConnect.inviteMembers).toHaveBeenCalledWith(
      channel.id,
      "other@example.com",
    );
  });

  it.each([
    { options: { role: "member" as const }, status: 403, code: "forbidden" },
    { options: { impersonated: true }, status: 403, code: "forbidden" },
    { options: { configured: false }, status: 503, code: "unavailable" },
  ])(
    "does not send without authorization or setup: $code",
    async ({ options, status, code }) => {
      const { app, slackConnect } = setup(options);
      const result = await postJson(app, collection, {});

      expect(result.status).toBe(status);
      expect((await result.json()).code).toBe(code);
      expect(slackConnect.inviteMembers).not.toHaveBeenCalled();
    },
  );

  it("returns a stable code for a taken channel name", async () => {
    const { app, slackConnect } = setup();
    slackConnect.createChannel.mockResolvedValueOnce({
      status: "name_taken",
    } as never);
    const result = await postJson(app, collection, {});

    expect(result.status).toBe(409);
    expect((await result.json()).code).toBe("slack_channel_name_taken");
  });

  it("returns Retry-After during the invitation cooldown", async () => {
    const { app, integrations } = setup();
    integrations.claimSlackInvitation.mockResolvedValueOnce({
      claimed: false,
      availableAt: new Date(Date.now() + 90_000),
    } as never);
    const result = await postJson(app, collection, {});

    expect(result.status).toBe(429);
    expect((await result.json()).code).toBe("slack_invitation_cooldown");
    expect(Number(result.headers.get("Retry-After"))).toBeGreaterThan(80);
  });

  it.each([
    { channel_name: "general" },
    { channel_name: "ext-Example-gradiated" },
    { channel_name: `ext-${"a".repeat(70)}-gradiated` },
    { email: "not-an-email" },
    { email: "a".repeat(201) + "@example.com" },
  ])("rejects invalid input: %j", async (body) => {
    const { app, slackConnect } = setup();

    expect((await postJson(app, collection, body)).status).toBe(422);
    expect(slackConnect.inviteMembers).not.toHaveBeenCalled();
  });
});
