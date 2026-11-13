# Production deployment

## Release contract

`Product tests` is the pre-merge quality gate. It builds changed container images
and the production console, scans the image archives with Trivy, and retains
verified artifacts for 30 days. A CRITICAL vulnerability with an available fix
blocks the PR; HIGH findings are reported. The existing GPU base image policy
remains report-only. `.trivyignore` still requires a justification and expiry for
each accepted risk. Scanner and policy changes invalidate prior verification.

A push to `main` starts `Application deployment` immediately. It does not wait
for another test run, rebuild containers, compile the console, or run vulnerability
scans. It promotes the artifacts that passed PR CI. Image archives are bound to
their exact build inputs, verification inputs and archive checksum. Console
artifacts additionally bind their public build configuration and every output
file. Only successful runs of the product CI workflow in this repository qualify;
fork artifacts cannot be promoted. If the merged inputs differ from those tested,
or the required artifact expired, deployment stops and requires a retested PR.
It never silently rebuilds an unverified image. An unchanged already-published
image can be retained without downloading or copying its archive again.

Manual runs accept an explicit 40-character source commit from `main`. Release
metadata records the originating `deploymentRunId`, so recovery inspects that
run even when the dispatch ref and selected source differ. Sources
older than the recorded release are skipped; ancestry is checked again before
writing release state. Rollbacks use a new revert commit on `main`, preserving
release ordering and making the rollback pass CI.

Manual application deployment dispatches explicitly publish the console, allowing
public build configuration changes without forcing backend rollouts. Run Product
tests on main with the new configuration first to produce the matching verified
console artifact; deployment continues to download that artifact without building.

## Deployment order

1. Resolve the source and compare its actual component inputs with the recorded
   release. Resolve unchanged image digests and promote changed, CI-verified OCI
   archives to ECR in parallel with downloading/staging the verified console.
   Kubernetes uses immutable digests, not mutable deployment tags.
2. Upload hashed console assets to private S3 without changing live `index.html`.
   Backend-only releases skip console staging and publication.
3. Commit the source revision, image digests and actual console revision to
   `main` with the Gradiated Release app. Generated commits carry `[skip ci]`.
4. For backend changes, wait for Argo CD to apply the release, fully promote API,
   gateway and proxy canaries, make worker/collector Deployments available, and
   pass the checks that require real production (including inference probes and
   training readiness). Keep an explicit gateway image override where configured.
5. Publish console `index.html`, invalidate CloudFront, and verify live root,
   SPA fallback, static branding and API readiness. A frontend-only change skips
   backend rollout waiting only when the previous backend deployment succeeded;
   an uncertain or failed prior deployment falls back to checking backend health.

Vercel owns the website and its previews; these application release steps concern
the customer console and backend services. Build preparation and CI reuse do not
permit competing production publications: the production concurrency group and
stale-source checks remain in force.

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
It does not bypass pre-merge CI, database migration or the final production readiness checks.
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
  only their listed repositories. `gradctl github-apps create` creates them
  through the manifest flow, verifies each installation's repository scope, and
  writes each private key straight to its secret store:
  - Gradiated Release (contents write, `main` bypass): release commits.
  - Gradiated CI (contents write, no bypass): screenshot commits on PR branches.
  - Gradiated Docs (contents and pull requests write, no bypass): the daily
    developer docs pull request from `.github/workflows/docs-refresh.yml`.
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
  `.github/workflows/security.yml`). It also requires one approving review,
  from the `gradiated-review` app or a person with write access who is not the
  author. `.github/workflows/ai-review-gate.yml` still posts an informational
  `AI review passed` status, which is no longer required. The same workflow reviews each PR
  as the `gradiated-review` GitHub App (app id 5394141). It approves when a
  bot review passed (Codex without P0/P1 findings, or a successful Graphite
  AI Reviews check), every Codex P0/P1 was followed by a clean Codex review of
  a newer commit, and every review thread is resolved. Otherwise it leaves a
  comment review listing what is outstanding, and asks Codex to review pushed
  fixes. Comment `@gradiated-review` (or `/review`) on a PR, with write
  access, to make it review again. GitHub cannot send review requests to apps.
  The rule is documented at the top of the workflow. The app's
  private key is the `AI_REVIEW_APP_PRIVATE_KEY` secret of the
  `ai-review-gate` environment, which admits only `main`, so PR code cannot
  read it. Once the ruleset requires one approving review, this approval is
  the required review; ordinary PRs need no human approval. Organization owners,
  repository administrators and the Gradiated Release app are bypass actors.
  Administrators bypass only as the Change Management Policy allows, when
  both AI reviewers are unavailable or for an emergency, and record each
  bypass in a PR comment. For everyone else a red or pending required check
  blocks the merge. The separate `main integrity` ruleset has no bypass actors and
  retains deletion and force-push protections. The repository has no deploy
  keys; each automated writer or reader is a GitHub App above.

Every required workflow runs on every pull request. Its `changes` job
(`.github/actions/relevant`) compares the pull request's files with the
workflow's own `push.paths` and skips the other jobs when nothing relevant
changed; the `passed` gate treats skipped jobs as passing. A new job must be
listed in its workflow's `passed.needs`; the `changes` job fails otherwise.

Product tests select jobs through `.github/actions/product-changes/plan.py`.
The normal checks target five minutes; expensive Rust, browser, image, native
runtime and GPU tests target ten minutes and have explicit path scopes. These
are performance targets; generous failure timeouts only stop runaway jobs. CI workflow,
shared selector and toolchain changes intentionally validate all affected scopes.

TypeScript checks are split into bounded parallel groups, with independent Rust
jobs. Formatting is a separate fast check, including website-only and product
Markdown changes. The pnpm lockfile selector compares each importer's transitive
snapshot/integrity closure; a console-only dependency update does not automatically
select inference or GPU checks. The production console still builds for every
lockfile change because its immutable artifact includes the complete lockfile.
Unknown lockfile shapes, missing bases, root
workspace dependency changes and global lockfile settings conservatively run full
validation. Workspace dependencies and explicit cross-language fixtures still
propagate changes to their consumers.

A successful product CI run can prove identical selected checks on a later push.
The reuse key includes the material merged tree, tool/test definitions and selected
scope, so changed merge inputs or changed coverage cannot borrow an unrelated
result. Formatting remains independent; image candidates require a scan proof
no older than 24 hours when reusing a build in CI. Required aggregate gates always
report, even for an unchanged round. Restored compilation caches are an optimization,
not evidence that tests passed. PR jobs restore Rust targets without uploading
them; only successful main checks populate those compilation caches.

The workflow prints per-shard wall/CPU/RSS measurements. Change Depot machine size
only after comparing an identified CPU or memory bottleneck on the same workload;
network/cache transfer and production soak waits do not benefit from more CPUs.

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

Website builds run in the Product tests PR gate. Website-only main-branch
changes do not trigger Product tests and its downstream application deployment;
Vercel owns website hosting and PR preview links. Console Storybook uses a
separate `storybook` Vercel project in the Gradiated team, rooted at
`product/services/console`, with its build
configuration in `vercel.json` and PR links provided by Vercel's Git integration.
Preview builds run independently of GitHub Actions. Configure Standard machines
and on-demand concurrency with one active build per branch for parallel PRs.
Neither website nor Storybook CI captures or commits screenshots. Local capture
scripts remain available under `tools/browser/`. Storybook production is served
at `https://storybook.gradiated.com` by Vercel. The `public-ingress` module owns
its CNAME, pointing to `49acbae7731b47db.vercel-dns-016.com`; the Vercel project
must have this domain assigned to Production. The Vercel deployment URL and PR
preview links remain available; project deployment protection controls access.

Before observability reconciliation, populate the externally managed
`gradiated/prod/platform/alertmanager-notifications` secret with a
`webhook-url` key and a `webhook-token` key. Alert definitions and dashboards
deploy without embedded receiver credentials. Notification delivery requires
that secret version.

Terraform creates `gradiated-prod-deployment`. The role trusts only this
repository's immutable GitHub OIDC subject in the `production` environment.

### Storybook domain migration

The AWS retirement uses two ordered, reviewed Terraform releases:

1. Apply the preparation release first: remove the old AAAA alias, set only the
   Storybook bucket's `force_destroy` to true, and remove obsolete deployment
   permissions. Wait for the production apply to succeed. The old domain keeps
   serving through its A alias. The saved bucket setting allows the AWS provider
   to delete all versions and delete markers during the cutover release.
2. Confirm Vercel's `storybook` project has `storybook.gradiated.com` assigned to
   Production, recommends `49acbae7731b47db.vercel-dns-016.com`, and has a ready
   production deployment. Then apply the cutover release. The moved Route 53
   resource preserves Terraform ownership while changing the A alias to a CNAME.
   The AAAA alias must already be absent because Route 53 rejects a CNAME alongside either address record.
   Terraform also removes the Storybook bucket and all its versions, CloudFront
   distribution, origin access control and outputs. The console and shared
   certificate/WAF remain in AWS.
3. Verify the Terraform apply succeeded, Vercel reports valid configuration,
   HTTPS works, and the expected production stories are present. CloudFront
   retirement can take time; cached DNS may briefly serve the old distribution.

Do not merge the cutover release until preparation has been applied. Production
changes run through CI from main. There is no manual bucket purge or state edit.
The old Storybook GitHub Actions workflow is already removed; Vercel owns builds.
AWS assets are reproducible build output; reverting after deletion cannot recover
the old bucket contents or distribution identity. Roll back hosting by restoring
AWS infrastructure and rebuilding assets, or correct the Vercel domain/deployment.

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
