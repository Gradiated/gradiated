// GitHub Apps that replace repository deploy keys. Each app is split by trust
// boundary and installed on exactly the repositories listed here.

export const owner = "Gradiated";
export const homepage = "https://gradiated.com";

export const apps = [
  {
    key: "release",
    name: "Gradiated Release",
    description: "Commits production release state to main. Bypasses the main ruleset.",
    permissions: { contents: "write" },
    repositories: ["gradiated"],
    store: {
      github: {
        repository: "gradiated",
        environment: "production",
        secret: "RELEASE_APP_PRIVATE_KEY",
        variable: "RELEASE_APP_CLIENT_ID",
      },
    },
  },
  {
    key: "ci",
    name: "Gradiated CI",
    description: "Pushes generated screenshots to pull request branches. No ruleset bypass.",
    permissions: { contents: "write" },
    repositories: ["gradiated"],
    store: {
      github: {
        repository: "gradiated",
        secret: "CI_APP_PRIVATE_KEY",
        variable: "CI_APP_CLIENT_ID",
      },
    },
  },
  {
    key: "docs",
    name: "Gradiated Docs",
    description: "Opens and updates the daily developer docs pull request. No ruleset bypass.",
    permissions: { contents: "write", pull_requests: "write" },
    repositories: ["gradiated"],
    store: {
      github: {
        repository: "gradiated",
        secret: "DOCS_APP_PRIVATE_KEY",
        variable: "DOCS_APP_CLIENT_ID",
      },
    },
  },
  {
    key: "autotrain-reader",
    name: "Gradiated Autotrain Reader",
    description: "Reads the private autotrain library for runtime builds.",
    permissions: { contents: "read" },
    repositories: ["autotrain"],
    store: {
      github: {
        repository: "gradiated",
        secret: "AUTOTRAIN_APP_PRIVATE_KEY",
        variable: "AUTOTRAIN_APP_CLIENT_ID",
      },
    },
  },
  {
    key: "argocd",
    name: "Gradiated Argo CD",
    description: "Lets production Argo CD read the GitOps repository.",
    permissions: { contents: "read" },
    repositories: ["gradiated"],
    store: {
      // Argo CD repository credential fields, read by an ExternalSecret.
      aws: {
        secretId: "gradiated/prod/gitops/argocd-github-app",
        repositoryUrl: "https://github.com/Gradiated/gradiated.git",
      },
    },
  },
];

export function manifest(app, redirectUrl) {
  return {
    name: app.name,
    description: app.description,
    url: homepage,
    redirect_url: redirectUrl,
    public: false,
    hook_attributes: { url: homepage, active: false },
    default_permissions: { metadata: "read", ...app.permissions },
    default_events: [],
  };
}

export function argoRepositoryCredential(app, { id, installationId, pem }) {
  return {
    type: "git",
    url: app.store.aws.repositoryUrl,
    githubAppID: String(id),
    githubAppInstallationID: String(installationId),
    githubAppPrivateKey: pem,
  };
}
