# Image builds and deployment sequences

`build-images.yml` is a reusable workflow. Callers select catalog image names
and a source commit. The workflow builds independent images in parallel and
returns their exact digests. It does not deploy workloads.

| Caller | Sequence | Current stopping point |
| --- | --- | --- |
| `application-deployment.yml` | Successful Product tests, required images and console build, release record, application rollout and checks | Existing application deployment |
| `model-deployment.yml` | Launch checks, GPU base image, verified runtime bundle and release record | Artifact publication; GPU qualification and serving rollout remain pending |

The application requires `product`, `gateway`, `proxy` and `collector`. The collector builds separately. When an explicit rollback source predates the collector catalog entry, the collector uses the deployment workflow revision while the other images use the requested source. The gateway, the proxy and the collector build from the shared `product/services/rust-service.Dockerfile`, which pins its builder and distroless runtime images by digest; each service selects its final stage with `target`. The GPU controller is a separate pinned image.
The model workflow publishes the GPU base and verified model/training bundles.
See `tools/models/README.md` for build order and the separate Kubernetes rollout
and SDK qualification steps. Runtime publication does not deploy a model.

## Change detection

Triggers limit each caller to related paths. The reusable workflow hashes the
tracked build inputs at the selected commit, including file modes and build
settings. The resulting ECR tag is immutable. If the tag already exists, the
workflow resolves its digest instead of rebuilding. A new caller commit can
therefore reuse unchanged images. The first run builds images that have no
matching input tag. AWS errors other than a missing image fail the lookup.

The catalog must cover every Docker COPY input. Model images
use distinct tag prefixes in the existing `gradiated/prod/inference` repository.
Build results record both the requested source revision and the input tag.
Use a distinct artifact prefix for each call within a workflow run.

The runtime bundle depends on the shared GPU base image. The model workflow
builds the base first and passes its immutable digest to the bundle build.
Do not infer ordering from matrix position.

No model serving job or route changes on publication. Workflow credentials use the existing production
OIDC role and environment. No local AWS session is required for publication.

## Checks

```sh
node --test tools/images/*.test.mjs
node --test tools/deployment/update-release.test.mjs
actionlint .github/workflows/build-images.yml .github/workflows/application-deployment.yml .github/workflows/model-deployment.yml .github/workflows/tests.yml
```

The first merge must verify ECR publication and the GitOps commit in GitHub.
Local tests cannot prove that the production role and branch rules permit them.

## Large model images

DeepSeek uses `COPY --link` so the launch script can be added without extracting
the large vLLM base filesystem. Keep this image free of `RUN` steps unless the
runner disk budget is revisited. Publication still transfers base layers to ECR.
Model builds remove unused hosted-runner SDKs and require 25 GiB free before build.
They skip GitHub Actions cache import/export; immutable ECR tags still provide reuse.
The first successful hosted publication is the acceptance check for the disk fix.
