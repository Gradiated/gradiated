// Paths must include every tracked file that can enter the Docker build context.
export const catalog = {
  product: {
    context: "product",
    repository: "gradiated/prod/product",
    target: "",
    paths: [
      "product/packages/",
      "product/services/",
      "product/Dockerfile",
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
    repository: "gradiated/prod/gateway",
    target: "",
    paths: ["product/services/gateway/"],
  },
  "nomad-base": {
    context: "product/inference",
    dockerfile: "product/inference/images/nomad-base/Dockerfile",
    repository: "gradiated/prod/inference",
    target: "",
    paths: [
      "product/inference/images/nomad-base/",
      "product/inference/runtime-launcher/CMakeLists.txt",
      "product/inference/runtime-launcher/main.cpp",
      "product/inference/runtime-launcher/supervise.cpp",
      "product/inference/runtime-launcher/supervise.h",
    ],
  },
  "deepseek-v4-1-flash": {
    context: "product/inference/images/deepseek-v4-1-flash",
    repository: "gradiated/prod/inference",
    target: "",
    paths: ["product/inference/images/deepseek-v4-1-flash/"],
  },
  "glm-5-3-flash": {
    context: "product/inference/images/glm-5-3-flash",
    repository: "gradiated/prod/inference",
    target: "",
    paths: ["product/inference/images/glm-5-3-flash/"],
    disabled: "The qualified GLM base image digest is not yet recorded.",
  },
};
