import { problemContent } from "@gradiated/contracts";
import type { OrganizationService } from "@gradiated/control";
import { createRoute, type OpenAPIHono, z } from "@hono/zod-openapi";
import {
  GithubInstallationsSchema,
  type GithubInstallations,
} from "../github/installations.js";
import { consoleOnly } from "../http/audience.js";
import { ApiProblem, problems, requireUser } from "../http/problems.js";
import type { PandaDocNda } from "../legal/pandadoc.js";
import type { ApiEnvironment, AuthService } from "../types.js";

const read = createRoute({
  ...consoleOnly,
  method: "get",
  path: "/api/v1/organizations/{organization_id}/github-installations",
  operationId: "getGithubInstallations",
  tags: ["GitHub installations"],
  summary: "Verify the customer's Gradiated GitHub App installation",
  description:
    "Uses the signed-in customer's linked GitHub App user authorization to check active installations, Contents access and accessible repositories. Requires a completed NDA and organization admin membership. Callback IDs and browser state are never proof of installation.",
  request: {
    params: z.object({
      organization_id: z
        .uuid()
        .describe("The authorized Gradiated organization."),
    }),
    query: z.object({
      nda_document_id: z
        .string()
        .regex(/^[a-zA-Z0-9_-]{1,100}$/)
        .describe("The completed NDA bound to this user and organization."),
      installation_id: z.coerce
        .number()
        .int()
        .positive()
        .optional()
        .describe(
          "An installation to recheck; never trusted without GitHub verification.",
        ),
    }),
  },
  responses: {
    200: {
      description: "GitHub-confirmed current installation state.",
      content: { "application/json": { schema: GithubInstallationsSchema } },
    },
    ...Object.fromEntries(
      [401, 403, 409, 422, 503].map((status) => [
        status,
        {
          description:
            "Unauthorized, incomplete, invalid or unavailable verification.",
          content: problemContent,
        },
      ]),
    ),
  },
});

export const registerGithubInstallationRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  organizations: Pick<OrganizationService, "listForUser">,
  auth: AuthService,
  provider?: GithubInstallations,
  nda?: PandaDocNda,
) => {
  app.openapi(read, async (context) => {
    context.header("Cache-Control", "no-store");
    const user = await requireUser(context);
    if ("impersonatedBy" in user && user.impersonatedBy)
      throw new ApiProblem(
        problems.forbidden(
          "Leave impersonation before connecting a GitHub identity.",
        ),
      );
    const { organization_id } = context.req.valid("param");
    const memberships = await organizations.listForUser(user.id);
    if (
      !user.emailVerified ||
      !memberships.some(
        (item) =>
          item.id === organization_id &&
          item.status === "active" &&
          item.role === "admin",
      )
    )
      throw new ApiProblem(
        problems.forbidden(
          "A verified organization admin must connect GitHub.",
        ),
      );

    if (!provider || !nda || !auth.githubAccessToken)
      throw new ApiProblem(
        problems.unavailable(
          "GitHub installation verification has not been configured yet.",
        ),
      );

    const query = context.req.valid("query");
    const document = await nda.read(
      { userId: user.id, email: user.email, organizationId: organization_id },
      query.nda_document_id,
    );
    if (document.status !== "completed")
      throw new ApiProblem(
        problems.conflict("Complete your mutual NDA before connecting GitHub."),
      );

    const token = await auth.githubAccessToken(context.req.raw.headers);
    if (!token)
      return context.json(
        { status: "authorization_required" as const, installations: [] },
        200,
      );

    return context.json(await provider.list(token, query.installation_id), 200);
  });
};
