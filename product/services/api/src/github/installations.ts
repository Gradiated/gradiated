import { z } from "@hono/zod-openapi";
import { ApiProblem, problems } from "../http/problems.js";

const REPOSITORY_SAMPLE = 5;

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
    account_type: z
      .enum(["Organization", "User"])
      .describe(
        "Whether the account is an organization or a personal account.",
      ),
    manage_url: z
      .url()
      .describe(
        "GitHub page where the customer changes the installation's repository access.",
      ),
    repository_selection: z
      .enum(["all", "selected"])
      .describe(
        "Whether the installation covers all or selected repositories.",
      ),
    repository_count: z
      .number()
      .int()
      .nonnegative()
      .describe(
        "Repositories accessible to both this GitHub user and the app installation; zero until the customer selects one.",
      ),
    repositories: z
      .array(z.string())
      .max(REPOSITORY_SAMPLE)
      .describe(
        `Full names of up to ${REPOSITORY_SAMPLE} of those repositories, for display.`,
      ),
  })
  .openapi("GithubInstallation");

export const GithubInstallationsSchema = z
  .object({
    status: z
      .enum(["authorization_required", "not_installed", "installed"])
      .describe(
        "Installed means at least one active Gradiated installation; check repository_count before starting a project.",
      ),
    installations: z.array(GithubInstallationSchema),
  })
  .openapi("GithubInstallations");

const installationSchema = z.object({
  id: z.number().int().positive(),
  app_slug: z.string(),
  account: z
    .object({ login: z.string(), type: z.enum(["Organization", "User"]) })
    .nullable(),
  html_url: z.url(),
  suspended_at: z.string().nullable(),
  repository_selection: z.enum(["all", "selected"]),
  permissions: z.object({ contents: z.string().optional() }),
});

export const createGithubInstallations = (
  appSlug = "gradiated",
  request: typeof fetch = fetch,
) => {
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
            installation.app_slug !== appSlug ||
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
              repositories: z.array(z.object({ full_name: z.string() })),
            })
            .parse(
              await call(
                token,
                `/user/installations/${installation.id}/repositories?per_page=${REPOSITORY_SAMPLE}`,
              ),
            );

          // Zero-repository installations are reported so the customer can
          // be asked to select one; submission still requires a repository.
          installations.push({
            id: installation.id,
            account: installation.account.login,
            account_type: installation.account.type,
            manage_url: installation.html_url,
            repository_selection: installation.repository_selection,
            repository_count: repositories.repositories.length
              ? repositories.total_count
              : 0,
            repositories: repositories.repositories.map(
              (repository) => repository.full_name,
            ),
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
