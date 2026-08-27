# Production deployment

## Release contract

`Product tests` is the production quality gate. A successful run for `main`
starts `Production deployment`. A manual run can deploy an explicit 40-character
source commit.

The deployment has one source revision and three parallel build outputs:

- one product image for the API, worker, and migration commands;
- one gateway image;
- one static console build.

The workflow tags ECR images with `git-<source-sha>`. ECR tag immutability makes
the build idempotent. Kubernetes uses only resolved `sha256` image digests.

## Deployment order

1. Build the product image, gateway image, and console in parallel.
2. Push the images to ECR.
3. Upload hashed console assets to the private S3 bucket. Do not upload the live
   `index.html` file.
4. Create one automated release commit on `main`. This commit records the source
   revision, both image digests, and the console revision.
5. Wait for Argo CD to apply the release and for the API and worker Deployments
   to become available.
6. Upload `index.html` with revalidation headers.
7. Invalidate the console CloudFront distribution.
8. Compare the live root and SPA fallback with the built entry point. Check API
   readiness.

The release commit uses the repository `GITHUB_TOKEN`. GitHub does not start a
new push workflow for that commit. The workflow updates only
`kustomization.yaml` and `release-metadata.yaml`.

The gateway image is built and recorded now. The production gateway Deployment
must remain disabled until the binary implements its documented inference HTTP
surface and the selected SGLang runtime is qualified. When the gateway manifest
uses the existing ECR repository name, Kustomize will apply the recorded digest.

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
- Branch rules must allow `github-actions[bot]` to push the two generated release
  files, or provide an equivalent narrowly scoped ruleset bypass.

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
