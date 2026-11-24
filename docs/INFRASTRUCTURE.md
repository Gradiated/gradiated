# Infrastructure

Gradiated's production infrastructure lives in the private
[Gradiated/infrastructure](https://github.com/Gradiated/infrastructure)
repository, not in this monorepo.

## What lives in `Gradiated/infrastructure`

- **Terraform & Terragrunt** (`environments/prod/us-east-1/terraform/`,
  `modules/`, `bootstrap/`) — AWS networking, EKS, RDS, ClickHouse, Temporal,
  Tailscale, Argo CD bootstrap, monitoring, secrets, and account bootstrap
  roots.
- **Kubernetes & Argo CD GitOps manifests**
  (`environments/prod/us-east-1/kubernetes/`) — Cluster platform Applications,
  application Deployments/Rollouts, GPU inference host inventory and model
  pools, and operational workloads.
- **Infrastructure container images** (`images/`) — Custom `falco` and
  `temporal-ui` images.
- **Infrastructure CI & operations** (`.github/workflows/`) — Terraform
  plan/apply, Kubernetes manifest & observability checks, pinned GPU image
  verification, weekly EKS node patching, weekly Prowler SOC 2 scans, and AWS
  control inventory.

## How this repository interacts with `Gradiated/infrastructure`

Product code, services, inference runtimes, and image builds stay in this
repository. When changes merge to `main`:

- **Application deployment** (`.github/workflows/application-deployment.yml`)
  and **Image promotion** (`.github/workflows/build-images.yml`) read and
  commit updated immutable image digests and release metadata in
  `Gradiated/infrastructure` using the `Gradiated Release` GitHub App
  (`RELEASE_STATE_REPO=infrastructure`).
- **Model deployment** (`.github/workflows/model-deployment.yml`) publishes
  verified runtime bundles to S3 and commits updated host-bundle pins to
  `Gradiated/infrastructure`.
- Argo CD reconciles production workloads directly from
  `Gradiated/infrastructure` `main`.

For infrastructure changes, Terraform plans/applies, or Kubernetes manifest
edits, work directly in `Gradiated/infrastructure`.
