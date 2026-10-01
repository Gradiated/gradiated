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
4. Open a release PR recording the source revision, image digests and console
   revision. Required checks must pass before auto-merge applies it to `main`.
5. Wait for Argo CD to apply the release and for the API and worker Deployments
   to become available.
   An explicit Argo gateway image override is preserved and checked for readiness.
6. Upload `index.html` with revalidation headers.
7. Invalidate the console CloudFront distribution.
8. Compare the live root and SPA fallback with the built entry point. Check API
   readiness.

The release PR uses the repository `GITHUB_TOKEN`. Its branch push and PR
creation do not trigger checks automatically, so the deployment explicitly
dispatches every required workflow on that branch. The relevance helper finds
the open PR and retains normal path filtering. A release still open after the
one-hour merge timeout is closed to prevent a late deployment. The workflow updates `kustomization.yaml`,
`release-metadata.yaml` and the image digest in each workload manifest that runs a
released image.

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
- Workflow permissions must allow the repository `GITHUB_TOKEN` to write
  contents.
- Organization policy and repository settings must allow GitHub Actions to
  create pull requests. Enable repository auto-merge. The release job gets
  contents, pull-request and workflow-dispatch write permissions; other jobs
  retain their existing permissions. It does not approve reviews.
- The `main` ruleset requires one gate per workflow: `Product tests passed`,
  `Kubernetes passed`, `Nomad deployment passed`, `Terraform passed`,
  `Model deployment passed`, `Wizard publish passed`, `Agent quality passed`,
  `Dependency age passed` and `Research lab passed`. Release PRs satisfy these
  checks and resolved review threads without a branch-rules bypass.

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
