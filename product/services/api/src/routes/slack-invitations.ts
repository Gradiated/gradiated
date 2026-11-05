import { problemContent } from "@gradiated/contracts";
import type { OrganizationService } from "@gradiated/control";
import { createRoute, type OpenAPIHono, z } from "@hono/zod-openapi";
import { consoleOnly } from "../http/audience.js";
import { ApiProblem, problems, requireUser } from "../http/problems.js";
import type { PandaDocNda } from "../legal/pandadoc.js";
import { SlackInvitationSchema, type SlackConnect } from "../slack/connect.js";
import type { ApiEnvironment } from "../types.js";

const create = createRoute({
  ...consoleOnly,
  method: "post",
  path: "/api/v1/organizations/{organization_id}/slack-invitations",
  operationId: "createSlackInvitation",
  tags: ["Slack invitations"],
  summary:
    "Invite the customer's chosen email to a dedicated Slack Connect channel",
  description:
    "Requires an active verified organization admin and completed NDA. Creates or reuses the public customer channel, adds Gradiated engineers, and emails a Slack Connect invitation to the chosen recipient. The Slack email may differ from the NDA signer. Customer acceptance and workspace approval may still be required.",
  request: {
    params: z.object({
      organization_id: z.uuid().describe("The customer organization."),
    }),
    body: {
      required: true,
      content: {
        "application/json": {
          schema: z.strictObject({
            email: z
              .string()
              .trim()
              .toLowerCase()
              .email()
              .max(200)
              .optional()
              .describe(
                "The Slack invitation recipient; defaults to the signed-in account email, independently of the NDA signer.",
              ),
            nda_document_id: z
              .string()
              .regex(/^[a-zA-Z0-9_-]{1,100}$/)
              .describe(
                "The completed NDA for this organization and signed-in user.",
              ),
          }),
        },
      },
    },
  },
  responses: {
    201: {
      description: "Slack confirmed the invitation or existing membership.",
      content: { "application/json": { schema: SlackInvitationSchema } },
    },
    ...Object.fromEntries(
      [401, 403, 409, 422, 503].map((status) => [
        status,
        {
          description:
            "The request is unauthorized, incomplete, invalid, or unavailable.",
          content: problemContent,
        },
      ]),
    ),
  },
});

export const registerSlackInvitationRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  organizations: Pick<OrganizationService, "listForUser">,
  provider?: SlackConnect,
  nda?: PandaDocNda,
) => {
  app.openapi(create, async (context) => {
    context.header("Cache-Control", "no-store");
    const user = await requireUser(context);
    const { organization_id } = context.req.valid("param");
    const memberships = await organizations.listForUser(user.id);
    const organization = memberships.find(
      (item) =>
        item.id === organization_id &&
        item.status === "active" &&
        item.role === "admin",
    );
    if (!user.emailVerified || !organization)
      throw new ApiProblem(
        problems.forbidden(
          "A verified organization admin must request the Slack invitation.",
        ),
      );

    if (!provider || !nda)
      throw new ApiProblem(
        problems.unavailable(
          "Automatic Slack invitations have not been configured yet. You can continue with setup.",
        ),
      );

    const document = await nda.read(
      { userId: user.id, email: user.email, organizationId: organization_id },
      context.req.valid("json").nda_document_id,
    );
    if (document.status !== "completed")
      throw new ApiProblem(
        problems.conflict(
          "Complete your mutual NDA before requesting the Slack invitation.",
        ),
      );

    return context.json(
      await provider.invite({
        organizationId: organization_id,
        company: organization.name,
        email: context.req.valid("json").email ?? user.email,
      }),
      201,
    );
  });
};
