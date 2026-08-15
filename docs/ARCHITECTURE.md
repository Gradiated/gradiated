# Architecture

The current architecture is defined by this document, the [canonical data model](DATA_MODEL.md), and the [Kimi K3 provider launch plan](KIMI_K3_PROVIDER_LAUNCH_PLAN.md).

## Runtime boundary

| Area | Choice | Authority |
| --- | --- | --- |
| browser product | Vite/React/shadcn | generated control API client |
| control plane | TypeScript/Node, Hono, Zod, Drizzle, Better Auth | PostgreSQL |
| inference hot path | Rust | Valkey serving state and Git-pinned deployment manifest |
| model runtime | SGLang, one deployment per exact model | immutable release configuration |
| AWS platform | EKS, RDS, ECR, Secrets Manager and edge | Terraform/Argo CD |
| GPU platform | selected external Kubernetes provider, initially one 8x B300 node | provider plus Argo workload |

Direct customer keys and OpenRouter call the same Rust Chat Completions API. Requests name an exact hosted model. There is no general gateway, third-party provider routing, fallback, branded alias or generalized fleet service.

Every Gradiated HTTP API is authored with described Zod schemas and route metadata. OpenAPI 3.1, documentation, TypeScript clients and Rust fixtures are generated from that source.

Only introduce a routing layer or broader serving platform after at least two real hosted models create a measured shared-routing requirement that cannot be represented by the finite exact-model catalog.

Older architecture manuals and blueprints were removed. A new service map will be authored before implementation expands beyond the reviewed model and launch plan.
