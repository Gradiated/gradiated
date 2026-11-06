import { z } from "@hono/zod-openapi";
import { ApiProblem, problems } from "../http/problems.js";

export const GithubInstallationSchema = z
  .object({
    id: z
      .number()
      .int()
      .positive()
      .describe("The verified Gradiated GitHub App installation ID."),
    account: z
      .string()
      .describe("The GitHub account where the customer installed Gradiated."),
    repository_selection: z
      .enum(["all", "selected"])
      .describe(
        "Whether the installation covers all or selected repositories.",
      ),
    repository_count: z
      .number()
      .int()
      .positive()
      .describe(
        "Repositories accessible to both this GitHub user and the app installation.",
      ),
  })
  .openapi("GithubInstallation");

export const GithubInstallationsSchema = z
  .object({
    status: z
      .enum(["authorization_required", "not_installed", "installed"])
      .describe(
        "Installed requires an active Gradiated installation and accessible repositories.",
      ),
    installations: z.array(GithubInstallationSchema),
  })
  .openapi("GithubInstallations");

const installationSchema = z.object({
  id: z.number().int().positive(),
  app_slug: z.string(),
  account: z.object({ login: z.string() }).nullable(),
  suspended_at: z.string().nullable(),
  repository_selection: z.enum(["all", "selected"]),
  permissions: z.object({ contents: z.string().optional() }),
});

export const createGithubInstallations = (request: typeof fetch = fetch) => {
  const call = async (token: string, path: string) => {
    try {
      const response = await request(`https://api.github.com${path}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        redirect: "error",
        signal: AbortSignal.timeout(15_000),
      });
      if (response.status === 401)
        throw new ApiProblem(
          problems.forbidden(
            "Reconnect your GitHub account to check the installation.",
          ),
        );

      if (!response.ok) throw new Error("GitHub unavailable");

      return await response.json();
    } catch (error) {
      if (error instanceof ApiProblem) throw error;

      throw new ApiProblem(
        problems.unavailable(
          "Could not verify the GitHub installation. Try checking again shortly.",
        ),
      );
    }
  };

  return {
    async list(token: string, selectedId?: number) {
      const installations: z.infer<typeof GithubInstallationSchema>[] = [];
      for (let page = 1; page <= 10; page++) {
        const result = z
          .object({ installations: z.array(installationSchema) })
          .parse(
            await call(token, `/user/installations?per_page=100&page=${page}`),
          );
        for (const installation of result.installations) {
          if (
            installation.app_slug !== "gradiated" ||
            installation.suspended_at !== null ||
            !installation.account ||
            !["read", "write"].includes(
              installation.permissions.contents ?? "",
            ) ||
            (selectedId !== undefined && installation.id !== selectedId)
          )
            continue;

          const repositories = z
            .object({
              total_count: z.number().int().nonnegative(),
              repositories: z.array(
                z.object({ id: z.number().int().positive() }),
              ),
            })
            .parse(
              await call(
                token,
                `/user/installations/${installation.id}/repositories?per_page=1`,
              ),
            );
          if (!repositories.total_count || !repositories.repositories.length)
            continue;

          installations.push({
            id: installation.id,
            account: installation.account.login,
            repository_selection: installation.repository_selection,
            repository_count: repositories.total_count,
          });
        }
        if (result.installations.length < 100)
          return GithubInstallationsSchema.parse({
            status: installations.length ? "installed" : "not_installed",
            installations,
          });
      }

      throw new ApiProblem(
        problems.unavailable(
          "Too many GitHub installations to verify. Contact Gradiated for help.",
        ),
      );
    },
  };
};

export type GithubInstallations = ReturnType<typeof createGithubInstallations>;
