import { z } from "@hono/zod-openapi";
import { ApiProblem, problems } from "../http/problems.js";

export const SlackInvitationSchema = z
  .object({
    channel_id: z
      .string()
      .describe("The dedicated channel in Gradiated's workspace."),
    channel_name: z.string().describe("The shared customer channel name."),
    email: z
      .email()
      .describe("The verified account email invited to Slack Connect."),
    status: z
      .enum(["invited", "joined"])
      .describe(
        "Invited remains pending customer acceptance and any workspace approvals.",
      ),
  })
  .openapi("SlackInvitation");

const channelSchema = z.object({
  id: z.string().regex(/^[CG][A-Z0-9]+$/),
  name: z.string(),
  is_archived: z.boolean().optional(),
  is_private: z.boolean().optional(),
  purpose: z.object({ value: z.string() }).optional(),
});

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
    try {
      const listing = method === "conversations.list";
      const query = listing
        ? "?" +
          new URLSearchParams(
            Object.entries(body).map(([key, value]) => [key, String(value)]),
          )
        : "";
      const response = await request(
        `https://slack.com/api/${method}${query}`,
        {
          method: listing ? "GET" : "POST",
          headers: {
            Authorization: `Bearer ${configuration.token}`,
            "Content-Type": "application/json; charset=utf-8",
          },
          ...(listing ? {} : { body: JSON.stringify(body) }),
          redirect: "error",
          signal: AbortSignal.timeout(15_000),
        },
      );
      if (!response.ok) throw new Error("Slack unavailable");

      return z
        .object({ ok: z.boolean(), error: z.string().optional() })
        .passthrough()
        .parse(await response.json());
    } catch {
      throw new ApiProblem(
        problems.unavailable(
          "Could not confirm the Slack request. Try again shortly; no automatic retry was sent.",
        ),
      );
    }
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
    async invite(input: {
      organizationId: string;
      company: string;
      email: string;
    }) {
      const name = slackChannelName(input.company);
      const purpose = `Gradiated customer organization: ${input.organizationId}`;
      const created = await call("conversations.create", {
        name,
        is_private: false,
      });
      let channel: z.infer<typeof channelSchema>;

      if (created.ok) {
        channel = channelSchema.parse(created.channel);
        if (channel.is_private)
          throw new ApiProblem(
            problems.conflict(
              "Slack returned a private channel. Gradiated needs to check it before inviting anyone.",
            ),
          );
        requireSuccess(
          await call("conversations.setPurpose", {
            channel: channel.id,
            purpose,
          }),
        );
      } else if (created.error === "name_taken") {
        let cursor = "";
        let found: z.infer<typeof channelSchema> | undefined;
        for (let page = 0; page < 50; page++) {
          const listed = await call("conversations.list", {
            types: "public_channel",
            exclude_archived: true,
            limit: 200,
            ...(cursor ? { cursor } : {}),
          });
          requireSuccess(listed);
          const result = z
            .object({
              channels: z.array(channelSchema),
              response_metadata: z
                .object({ next_cursor: z.string().optional() })
                .optional(),
            })
            .parse(listed);
          found = result.channels.find(
            (item) =>
              item.name === name &&
              !item.is_archived &&
              !item.is_private &&
              item.purpose?.value === purpose,
          );
          if (found) break;

          cursor = result.response_metadata?.next_cursor ?? "";
          if (!cursor) break;
        }
        if (!found)
          throw new ApiProblem(
            problems.conflict(
              "That Slack channel name is already in use. Gradiated needs to check it before inviting anyone.",
            ),
          );

        channel = found;
      } else {
        requireSuccess(created);
        throw new Error("Unreachable");
      }

      for (const user of configuration.engineerUserIds) {
        const added = await call("conversations.invite", {
          channel: channel.id,
          users: user,
        });
        if (added.error !== "already_in_channel") requireSuccess(added);
      }

      const invitation = await call("conversations.inviteShared", {
        channel: channel.id,
        emails: [input.email],
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

      return SlackInvitationSchema.parse({
        channel_id: channel.id,
        channel_name: channel.name,
        email: input.email,
        status: joined ? "joined" : "invited",
      });
    },
  };
};

export type SlackConnect = ReturnType<typeof createSlackConnect>;
