# Image builds and deployment sequences

`build-images.yml` is a reusable workflow. Callers select catalog image names
and a source commit. The workflow builds independent images in parallel and
returns their exact digests. It does not deploy workloads.

| Caller | Sequence | Current stopping point |
| --- | --- | --- |
| `application-deployment.yml` | Successful Product tests, required images and console build, release record, application rollout and checks | Existing application deployment |
| `nomad-deployment.yml` | Rust and server configuration tests, relay image, GitOps digest record | Record only; Nomad is outside Argo sync |
| `model-deployment.yml` | Launch checks, model image publication | Publication only; GPU qualification and serving rollout are pending |

The application requires `product` and `gateway`. Nomad requires `nomad-relay`.
The model workflow currently publishes DeepSeek. GLM is listed in the catalog
but cannot build until its qualified base image digest is recorded. A disabled
image fails explicitly if requested. A model failure does not block application
or Nomad publication. Before adding model rollouts, give each model a separate
release run so one model does not block another.

## Change detection

Triggers limit each caller to related paths. The reusable workflow hashes the
tracked build inputs at the selected commit, including file modes and build
settings. The resulting ECR tag is immutable. If the tag already exists, the
workflow resolves its digest instead of rebuilding. A new caller commit can
therefore reuse unchanged images. The first run builds images that have no
matching input tag. AWS errors other than a missing image fail the lookup.

The catalog must cover every Docker COPY input. Application Docker context
excludes `services/nomad-relay`, which has its own image. Model and relay images
use distinct tag prefixes in the existing `gradiated/prod/inference` repository.
Build results record both the requested source revision and the input tag.
Use a distinct artifact prefix for each call within a workflow run.

All current base images are external inputs. If we introduce a shared base that
we build, add an explicit base-build dependency and pass its immutable digest
to dependent builds. Do not infer ordering from matrix position.

The relay recorder retries concurrent Git pushes and skips a source superseded
by newer relay inputs. It updates only the relay manifest. No model serving job
or route changes on publication. Workflow credentials use the existing production
OIDC role and environment. No local AWS session is required for publication.

## Checks

```sh
node --test tools/images/*.test.mjs
node --test tools/deployment/update-release.test.mjs
actionlint .github/workflows/build-images.yml .github/workflows/application-deployment.yml .github/workflows/nomad-deployment.yml .github/workflows/model-deployment.yml .github/workflows/tests.yml
```

The first merge must verify ECR publication and the GitOps commit in GitHub.
Local tests cannot prove that the production role and branch rules permit them.
