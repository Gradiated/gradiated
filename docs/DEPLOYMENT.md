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
2. Push the images to ECR.
3. Upload hashed console assets to the private S3 bucket. Do not upload the live
   `index.html` file.
4. Commit the source revision, image digests and console revision directly to
   `main`, using the repository-specific release deploy key. The source has
   already passed `Product tests`; the generated commit carries `[skip ci]`
   to avoid starting another build and deployment cycle.
5. Wait for Argo CD to apply the release and for the API and worker Deployments
   to become available.
   An explicit Argo gateway image override is preserved and checked for readiness.
6. Upload `index.html` with revalidation headers.
7. Invalidate the console CloudFront distribution.
8. Compare the live root and SPA fallback with the built entry point. Check API
   readiness.

The release job uses `DEPLOY_RELEASE_SSH_KEY` for its checkout and push. This
write deploy key bypasses the PR and status-check rules for `main`; a separate
ruleset still forbids branch deletion and force pushes. GitHub applies deploy-key
bypass to repository deploy keys as a class, so existing write deploy keys share
that exception. Ordinary user and app pushes retain their PR and CI requirements.
The release helper stages only the generated manifest paths, rejects pre-staged
changes, rechecks release ancestry before each push, and retries fast-forward
races by rebasing onto the latest `main`. Conflicts or stale sources stop the
release. No release PR or workflow approval is required.

The proxy manifest carries an all-zero placeholder digest until the first release
after its merge records a real one. Until then its pods cannot pull an image; the
proxy has no public route, so no customer traffic depends on it.

## Console cache behavior

Hashed assets use a one-year immutable cache lifetime. Deployments do not delete
old hashed assets because open browser tabs can still request them. The live
`index.html` uses revalidation headers and changes only after the backend is
healthy. S3 versioning keeps previous entry points for recovery.

## Required GitHub configuration

- Repository variable `AWS_ACCOUNT_ID` must contain the production AWS account
  ID.
- The `production` environment must permit the deployment workflow.
- Repository secret `DEPLOY_RELEASE_SSH_KEY` contains the private SSH key for
  the repository write deploy key used by the release job. Keep the key outside
  version control; the job needs only read access through `GITHUB_TOKEN`.
- The `main` ruleset requires one gate per workflow: `Product tests passed`,
  `Kubernetes passed`, `Nomad deployment passed`, `Terraform passed`,
  `Model deployment passed`, `Wizard publish passed`, `Agent quality passed`,
  `Dependency age passed` and `Research lab passed`. Ordinary PRs satisfy these
  checks and resolved review threads. Deploy keys bypass this ruleset; the
  separate `main integrity` ruleset retains deletion and force-push protections.

Every workflow runs on every pull request. Its `changes` job
(`.github/actions/relevant`) compares the pull request's files with the
workflow's own `push.paths` and skips the other jobs when nothing relevant
changed; the `passed` gate treats skipped jobs as passing. A new job must be
listed in its workflow's `passed.needs`; the `changes` job fails otherwise.

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
