// Paths must include every tracked file that can enter the Docker build context.
export const catalog = {
  "gpu-controller": {
    context: "tools/virtual-kubelet",
    dockerfile: "tools/virtual-kubelet/Dockerfile",
    repository: "gradiated/prod/product",
    target: "",
    paths: [
      "tools/virtual-kubelet/go.mod",
      "tools/virtual-kubelet/go.sum",
      "tools/virtual-kubelet/cmd/",
      "tools/virtual-kubelet/Dockerfile",
    ],
  },
  product: {
    exclude: [
      "product/services/console/",
      "product/services/gateway/",
      "product/services/proxy/",
      "product/services/collector/",
      "product/services/api/generated/",
    ],
    include: [
      "product/services/console/package.json",
      "product/services/gateway/package.json",
    ],
    context: "product",
    repository: "gradiated/prod/product",
    target: "",
    paths: [
      "product/packages/",
      "product/services/",
      "product/Dockerfile",
      "product/inference/images/gpu-base/base-id",
      "product/.dockerignore",
      "product/package.json",
      "product/pnpm-lock.yaml",
      "product/pnpm-workspace.yaml",
      "product/turbo.json",
      "product/tsconfig.base.json",
    ],
  },
  gateway: {
    context: "product/services/gateway",
    dockerfile: "product/services/rust-service.Dockerfile",
    buildContexts: "credentials=product/packages/credentials",
    repository: "gradiated/prod/gateway",
    target: "gateway",
    paths: [
      "product/services/gateway/",
      "product/packages/credentials/",
      "product/services/rust-service.Dockerfile",
    ],
  },
  proxy: {
    context: "product/services/proxy",
    dockerfile: "product/services/rust-service.Dockerfile",
    repository: "gradiated/prod/proxy",
    target: "proxy",
    paths: [
      "product/services/proxy/",
      "product/services/rust-service.Dockerfile",
    ],
  },
  collector: {
    context: "product/services/collector",
    dockerfile: "product/services/rust-service.Dockerfile",
    repository: "gradiated/prod/collector",
    target: "collector",
    paths: [
      "product/services/collector/",
      "product/services/rust-service.Dockerfile",
    ],
  },
  "gpu-base": {
    context: "product/inference",
    dockerfile: "product/inference/images/gpu-base/Dockerfile",
    repository: "gradiated/prod/inference",
    target: "",
    paths: [
      "product/inference/.dockerignore",
      "product/inference/images/gpu-base/Dockerfile",
      "product/inference/images/gpu-base/base-id",
      "product/inference/gpu/host_bundle.py",
      "product/inference/gpu/host_state.py",
      "product/inference/host/",
    ],
  },
};
