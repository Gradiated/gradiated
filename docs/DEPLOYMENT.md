# Production deployment

## Release contract

`Product tests` is the production quality gate. A successful run for `main`
starts `Application deployment`. A manual run can deploy an explicit 40-character
source commit from `main`. Sources older than the recorded production release are
skipped before building; ancestry is checked again before writing release state.
Rollbacks use a new revert commit on `main`, so delayed workflows cannot undo a
newer deployment.

The deployment has one source revision and these parallel build outputs:

- one product image for the API, worker, and migration commands;
- one gateway image;
- one proxy image;
- one collector image;
- one static console build.

The workflow tags ECR images with `git-<source-sha>`. ECR tag immutability makes
the build idempotent. Kubernetes uses only resolved `sha256` image digests.

## Deployment order

1. Build the product image, gateway image, proxy image, collector image, and
   console in parallel.
2. Push the images to ECR, then scan each pushed digest with Trivy. A CRITICAL
   vulnerability with a fix available fails the build and stops the release;
   HIGH findings are reported in the job summary. Reports are kept as 90-day
   workflow artifacts. Accepted risks go in `.trivyignore`, each with a
   justification comment and an expiry date. The scan policy and Trivy version
   come from the workflow revision, not the source commit. GPU base images are
   scanned in report-only mode.
3. Upload hashed console assets to the private S3 bucket. Do not upload the live
   `index.html` file.
4. Commit the source revision, image digests and console revision directly to
   `main`, using a token from the Gradiated Release GitHub App. The source has
   already passed `Product tests`; the generated commit carries `[skip ci]`
   to avoid starting another build and deployment cycle.
5. Wait for Argo CD to apply the release, fully promote the API, gateway and proxy
   Rollouts, and make the remaining worker/collector Deployments available.
   An explicit Argo gateway image override is preserved and checked for readiness.
6. Upload `index.html` with revalidation headers.
7. Invalidate the console CloudFront distribution.
8. Compare the live root and SPA fallback with the built entry point. Check API
   readiness.

The release job mints a short-lived token from the Gradiated Release GitHub App
(`RELEASE_APP_CLIENT_ID` variable, `RELEASE_APP_PRIVATE_KEY` secret in the
`production` environment) for its checkout and push. The app is a `main`
ruleset bypass actor, so it can skip the PR and status-check
rules; a separate ruleset still forbids branch deletion and force pushes.
Ordinary user and app pushes retain their PR and CI requirements.
The release helper stages only the generated manifest paths, rejects pre-staged
changes, rechecks release ancestry before each push, and retries fast-forward
races by rebasing onto the latest `main`. Conflicts or stale sources stop the
release. No release PR or workflow approval is required.

## Application canaries and rollback

One shared Argo Rollouts installation manages API, gateway and proxy in
`gradiated` and GPU models in `gpu-inference`. Its controller runs with three
replicas in `gpu-inference` and watches the cluster. Worker, Temporal worker and
collector remain Deployments. GPU model Rollouts retain their SDK qualification.
Host bundles are managed by the GPU host controller, independently of these
application Rollouts.

Shared analysis templates are owned by the API application and sync at wave
`-10`, before its Rollout. Gateway and proxy sync independently: parent
Application waves do not guarantee that shared templates already exist. For a
clean bootstrap or the first upgrade from older Application file filters, apply
the committed `rollout-analysis.yaml` before introducing the Rollouts. An
already-running sync can retain the old filter until it completes. Introduce
future template names in a separate release and confirm they exist before
shipping Rollouts that reference them. Missing templates prevent progression;
controllers retry automatically once the templates exist.

Each application Rollout references its existing Deployment as its pod template.
The initial takeover starts a full healthy replica set before scaling the old
Deployment down (`workloadRef.scaleDown: onsuccess`); do not delete the template.
Argo ignores the template's replica count so self-healing cannot restart it.
After migration, image changes still go into the Deployment template, while
KEDA scales the Rollout. Rollouts skip canary steps on initial creation: the
first takeover is a readiness-gated migration, not a canary regression test.

For later image changes, the Rollout uses 10%, 25%, 50% and 100% replica steps with
zero allowed unavailable replicas and one surge pod. Each intermediate step
runs seven candidate-only readiness requests over 90 seconds. Background
analysis begins after the first replica step is ready, waits 30 seconds for
initial scrapes, then checks every 15 seconds for fresh scrapes from every ready
candidate pod and server errors. All three services are scraped every 5 seconds.
Missing or stale candidate targets or replica-count telemetry fail the check.
The configured `failureLimit: 1` aborts on the second failed measurement, nominally
at 45 seconds for a persistently failing candidate, before the first 90-second
soak ends. Background analysis continues across subsequent steps. Repeated
provider errors also fail analysis instead of qualifying a release.
A 90-second window with at least three 5xx responses and a server-error ratio
above 2% fails a measurement. Gateway analysis additionally checks failed
terminal generations, including errors after streaming response headers.
The 100% step waits for pod readiness and completes promotion without a fourth
timed soak. The three soaks add about four and a half minutes, plus scheduling, startup and
check overhead; the services progress independently. The progress deadline aborts
an update that cannot make progress for 20 minutes.

The public Services continue selecting ready stable and candidate pods. These
weights control replica proportions, not exact ALB or per-request traffic
percentages. Keeping existing Service selectors avoids a load-balancer target
switch during migration. Candidate Services are internal and select only the
latest revision. Existing readiness gates, topology placement and graceful
stream draining remain in force.

Failed analysis restores the stable revision's replica count and stops automatic
promotion. Recovery can require stable pods to start: this configuration does
not keep a full stable fleet warm throughout the rollout. An abort does not
rewrite Git or undo migrations. Inspect the failure, then ship a fix or a new
revert commit. A new image/pod template starts a fresh canary automatically;
retrying the same unchanged candidate is an explicit operator action.
Backward-compatible database migrations are required throughout this window.

CI checks all three Rollouts' observed Deployment generations, stable revisions,
phases and ready replica counts together on every poll. A stale `Healthy` status
or an abort cannot publish the console. The existing training checks and fleet-wide public inference checks
still run after application promotion. Readiness plus observed error metrics do
not prove correctness under low traffic; this migration does not add an
authenticated SDK test for each application revision or precise traffic routing.

## Urgent hotfix promotion in Argo CD

Build and record the hotfix through the normal release workflow. Once Argo has
observed its candidate, open `https://argocd.gradiated.com`, choose the `api`,
`gateway` or `proxy` Application, select its **Rollout** resource, and choose
**promote-full** from the resource actions. Confirm the candidate image and
revision before promotion; the zero-replica Deployment is only the template.

`promote-full` explicitly skips the remaining canary steps, readiness analysis
Jobs and metric analysis. It preserves pod readiness, zero-unavailable capacity
constraints and graceful termination, so it cannot make an unready image serve.
It does not skip building, database migration or the final CI release checks.
Promotion applies to the current candidate, not a permanent fast mode for future
releases. After full promotion, rollout analysis stops; normal service alerting
continues. Do not expect the skipped analysis to automatically abort the hotfix.

Use **pause** to hold a running rollout, **resume** to release a pause, **abort**
to return an active rollout to stable, and **retry** to re-run an aborted
candidate. If the hotfix candidate is already aborted, inspect the failure and
retry it before full promotion. A fully promoted release requires a new image
update/revert rather than an abort of an active rollout.

All verified `@gradiated.com` Google users have application write access,
including these actions, behind the existing domain gate. Application writers
are trusted production operators: the default project permits applications to
deploy privileged Kubernetes resources. No per-user role assignment or
Kubernetes plugin is needed for the browser path. The public
Google gate requires a browser session; do not bypass it for CLI convenience.
For an existing authenticated Kubernetes operator session, the equivalent is:

```sh
kubectl argo rollouts get rollout gateway -n gradiated
kubectl argo rollouts promote gateway -n gradiated --full
kubectl argo rollouts abort gateway -n gradiated
```

## Console cache behavior

Product analytics uses the console's `CONSOLE_POSTHOG_KEY` build variable and
the API's `POSTHOG_KEY`/`POSTHOG_HOST` fields in its existing Secrets Manager
secret. Both must point to the same environment-specific project. See
[product analytics](PRODUCT_ANALYTICS.md) for rollout and notification setup.

Hashed assets use a one-year immutable cache lifetime. Deployments do not delete
old hashed assets because open browser tabs can still request them. The live
`index.html` uses revalidation headers and changes only after the backend is
healthy. S3 versioning keeps previous entry points for recovery.

## Required GitHub configuration

- Repository variable `AWS_ACCOUNT_ID` must contain the production AWS account
  ID.
- The `production` environment must permit the deployment workflow.
- The GitHub Apps in `tools/github-apps/apps.mjs` exist and are installed on
  only their listed repositories. `mise run github-apps:create` creates them
  through the manifest flow, verifies each installation's repository scope, and
  writes each private key straight to its secret store:
  - Gradiated Release (contents write, `main` bypass): release commits.
  - Gradiated CI (contents write, no bypass): screenshot commits on PR branches.
  - Gradiated Autotrain Reader (contents read on `autotrain`): runtime builds.
  - Gradiated Argo CD (contents read): the
    `gradiated/prod/gitops/argocd-github-app` repository credential.
  To rotate a key, generate a new one on the app's settings page, pipe it into
  the same secret (`gh secret set` or `aws secretsmanager put-secret-value`),
  then delete the old key. Never keep keys in version control.
- The `main` ruleset requires one gate per workflow: `Product tests passed`,
  `Kubernetes passed`, `Terraform passed`,
  `Model deployment passed`, `Wizard publish passed`, `Agent quality passed`,
  `Dependency age passed`, `Research lab passed`,
  `GPU controller and manifests passed` and `Security scans passed`
  (Gitleaks secret scanning, scan-policy checks and report-only Semgrep; see
  `.github/workflows/security.yml`). It also requires the `AI review passed`
  status, which `.github/workflows/ai-review-gate.yml` sets once Codex and
  Graphite have both reviewed a commit of the PR. Ordinary PRs satisfy these
  checks and resolved review threads; no approval is required. The Gradiated
  Release app is the only bypass actor. Organization admins, users and deploy
  keys cannot bypass it, so a red or pending required check blocks the merge;
  an emergency override means editing the ruleset, which GitHub records in its
  history. The separate `main integrity` ruleset has no bypass actors and
  retains deletion and force-push protections. The repository has no deploy
  keys; each automated writer or reader is a GitHub App above.

Every required workflow runs on every pull request. Its `changes` job
(`.github/actions/relevant`) compares the pull request's files with the
workflow's own `push.paths` and skips the other jobs when nothing relevant
changed; the `passed` gate treats skipped jobs as passing. A new job must be
listed in its workflow's `passed.needs`; the `changes` job fails otherwise.

Product tests further select individual jobs through
`.github/actions/product-changes/plan.py`. Workspace unit checks include changed
packages and their dependents; cross-service and Cargo fixture dependencies
have explicit path scopes. Native runtime, storage, gateway, proxy, product
browser, website, and tooling checks each have their own scopes. Root manifests,
lockfiles, toolchain settings, and changes to the test workflow run all checks.
Leaf package manifests select that workspace and its dependents; deleting a
workspace manifest runs all checks because the current graph cannot identify its
former consumers. Changes to the shared relevance action revalidate every caller.
Manual dispatch also runs every check. Pushes compare the full before/after
commit range; PRs include both current and previous names of renamed files.
Documentation and screenshot-only changes skip product checks.

Product Rust build caches include the source commit in their save keys and restore
the latest cache with matching lockfiles first. This lets successful source changes
refresh compiled artifacts instead of repeatedly restoring an immutable old build.
GPU enrollment, GPU base bootstrap, and Tailscale assets copied into the product
image also trigger Product tests and application release, with tooling checks.

Kubernetes selects its database, observability, Tailscale, Temporal UI/browser,
Argo authentication, and Loki subchecks from `.github/actions/relevant/kubernetes.json`.
GPU controller builds, configuration generation, and operator-schema validation
use `.github/actions/relevant/gpu.json`. The relevance action resolves changed
paths once and returns these selections alongside the workflow-level result.
These callers fetch full Git history for push before/after comparisons; PR
lookups include previous rename paths and failures fail the required gate.
Manual dispatch, new-branch pushes without a base, workflow changes, shared-action
changes, and toolchain changes run every subcheck. Keep scopes in sync with the
files each validator reads, including shared helpers and cross-file fixtures.

Website builds run in the Product tests PR gate and the separate informative
Website screenshots workflow. Website-only main-branch changes do not trigger
Product tests and its downstream application deployment; Vercel owns website
hosting. The screenshot workflow follows the console Storybook pattern: artifacts
for all PRs, committed PNGs and before/after comments for same-repository PRs,
and no pixel-diff failures.

Before observability reconciliation, populate the externally managed
`gradiated/prod/platform/alertmanager-notifications` secret with a
`webhook-url` key and a `webhook-token` key. Alert definitions and dashboards
deploy without embedded receiver credentials. Notification delivery requires
that secret version.

Terraform creates `gradiated-prod-deployment`. The role trusts only this
repository's immutable GitHub OIDC subject in the `production` environment.

## First deployment

The first Terraform apply after this workflow is merged creates the deployment
role and its EKS read-only access entry. The deployment workflow retries role
assumption while that apply runs. If the role is not ready within 15 minutes,
rerun the failed production deployment. Existing ECR images and staged console
assets are reused.

## Failure behavior

- A build or release-commit failure leaves the live console unchanged.
- An Argo timeout leaves the live console unchanged.
- A console publication failure leaves the new compatible backend with the old
  console. A rerun completes the cutover.
- A release rerun does not create a second commit when release state already
  matches the source revision and image digests.
