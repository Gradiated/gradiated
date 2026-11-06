import { z } from "@hono/zod-openapi";
import { ApiProblem, problems } from "../http/problems.js";
import { serviceLog } from "../logging.js";

export const SlackChannelNameSchema = z
  .string()
  .trim()
  .max(80)
  .regex(/^ext-[a-z0-9]+(?:-[a-z0-9]+)*-gradiated$/)
  .describe("A customer channel name such as ext-example-team-gradiated.");

export const SlackInvitationSchema = z
  .object({
    channel_id: z
      .string()
      .describe("The dedicated channel in Gradiated's workspace."),
    channel_name: z.string().describe("The shared customer channel name."),
    email: z
      .email()
      .describe(
        "The recipient email selected by the organization admin for Slack Connect.",
      ),
    status: z
      .enum(["invited", "joined"])
      .describe(
        "Invited remains pending customer acceptance and any workspace approvals.",
      ),
  })
  .openapi("SlackInvitation");

const channelSchema = z.object({
  id: z.string().regex(/^[CG][A-Z0-9]+$/),
  name: z.string().min(1).max(80),
  is_archived: z.boolean().optional(),
  is_private: z.boolean().optional(),
});

const SlackResponseSchema = z
  .object({ ok: z.boolean(), error: z.string().optional() })
  .passthrough();

const EXPECTED_SLACK_ERRORS = new Set([
  "already_in_channel",
  "channel_not_found",
  "name_taken",
]);
const READ_METHODS = new Set(["conversations.info"]);

export const slackChannelName = (company: string) => {
  const slug =
    company
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 66)
      .replace(/-$/g, "") || "customer";

  return `ext-${slug}-gradiated`;
};

export const createSlackConnect = (
  configuration: { token: string; engineerUserIds: string[] },
  request: typeof fetch = fetch,
) => {
  const call = async (method: string, body: Record<string, unknown>) => {
    const warn = (reason: string, status?: number) =>
      serviceLog("warn", "provider_request_failed", {
        dependency: "slack",
        route: method,
        reason,
        ...(status === undefined ? {} : { status }),
      });
    const unavailable = () =>
      new ApiProblem(
        problems.unavailable(
          "Could not confirm the Slack request. Try again shortly; no automatic retry was sent.",
        ),
      );

    const reading = READ_METHODS.has(method);
    const query = reading
      ? "?" +
        new URLSearchParams(
          Object.entries(body).map(([key, value]) => [key, String(value)]),
        )
      : "";
    let response: Response;
    try {
      response = await request(`https://slack.com/api/${method}${query}`, {
        method: reading ? "GET" : "POST",
        headers: {
          Authorization: `Bearer ${configuration.token}`,
          "Content-Type": "application/json; charset=utf-8",
        },
        ...(reading ? {} : { body: JSON.stringify(body) }),
        redirect: "error",
        signal: AbortSignal.timeout(15_000),
      });
    } catch (error) {
      warn(
        error instanceof Error && error.name === "TimeoutError"
          ? "timeout"
          : "network",
      );
      throw unavailable();
    }

    if (!response.ok) {
      warn("http_error", response.status);
      throw unavailable();
    }

    const parsed = SlackResponseSchema.safeParse(
      await response.json().catch(() => undefined),
    );
    if (!parsed.success) {
      warn("invalid_response", response.status);
      throw unavailable();
    }

    const { error } = parsed.data;
    if (!parsed.data.ok && !EXPECTED_SLACK_ERRORS.has(error ?? ""))
      warn(error && /^[a-z0-9_]{1,64}$/.test(error) ? error : "unknown_error");

    return parsed.data;
  };
  const requireSuccess = (response: {
    ok: boolean;
    error?: string | undefined;
  }) => {
    if (response.ok) return;

    if (
      [
        "restricted_action",
        "not_allowed",
        "paid_teams_only",
        "missing_scope",
      ].includes(response.error ?? "")
    )
      throw new ApiProblem(
        problems.unavailable(
          "Slack invitations need attention from Gradiated's workspace admin. You can continue while we sort this out.",
        ),
      );

    throw new ApiProblem(
      problems.unavailable(
        "The Slack invitation could not be confirmed. You can continue and try again later.",
      ),
    );
  };

  return {
    async findChannel(channelId: string) {
      const result = await call("conversations.info", { channel: channelId });
      if (!result.ok && result.error === "channel_not_found") return undefined;

      requireSuccess(result);
      const channel = channelSchema.parse(result.channel);

      return channel.is_archived || channel.is_private ? undefined : channel;
    },

    async createChannel(name: string) {
      const created = await call("conversations.create", {
        name: SlackChannelNameSchema.parse(name),
        is_private: false,
      });
      if (!created.ok && created.error === "name_taken")
        return { status: "name_taken" as const };

      requireSuccess(created);
      const channel = channelSchema.parse(created.channel);
      if (channel.is_private)
        throw new ApiProblem(
          problems.conflict(
            "Slack returned a private channel. Gradiated needs to check it before inviting anyone.",
          ),
        );

      return { status: "created" as const, channel };
    },

    async labelChannel(channelId: string, organizationId: string) {
      await call("conversations.setPurpose", {
        channel: channelId,
        purpose: `Gradiated customer organization: ${organizationId}`,
      }).catch(() => undefined);
    },

    async inviteMembers(channelId: string, email: string) {
      for (const user of configuration.engineerUserIds) {
        const added = await call("conversations.invite", {
          channel: channelId,
          users: user,
        });
        if (added.error !== "already_in_channel") requireSuccess(added);
      }

      const invitation = await call("conversations.inviteShared", {
        channel: channelId,
        emails: [email],
        external_limited: true,
      });
      const joined = invitation.error === "already_in_channel";
      if (!joined) requireSuccess(invitation);
      if (!joined && typeof invitation.invite_id !== "string")
        throw new ApiProblem(
          problems.unavailable(
            "Slack did not confirm an invitation. Check before sending another.",
          ),
        );

      return joined ? ("joined" as const) : ("invited" as const);
    },

    async postNotes(input: {
      channelId: string;
      email: string;
      notes: string;
      requestId: string;
    }) {
      const notes = z.string().trim().min(1).max(3000).parse(input.notes);
      const result = await call("chat.postMessage", {
        channel: input.channelId,
        client_msg_id: z.uuid().parse(input.requestId),
        blocks: [
          {
            type: "section",
            text: {
              type: "plain_text",
              text: `Notes submitted during Gradiated onboarding by ${input.email}`,
            },
          },
          { type: "section", text: { type: "plain_text", text: notes } },
        ],
        unfurl_links: false,
        unfurl_media: false,
      });
      if (!result.ok || typeof result.ts !== "string")
        throw new ApiProblem(
          problems.unavailable("Slack did not confirm the onboarding notes."),
        );

      return { status: "sent" as const };
    },
  };
};

export type SlackConnect = ReturnType<typeof createSlackConnect>;
