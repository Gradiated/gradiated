target "base" {
  context    = "product/inference"
  dockerfile = "images/gpu-base/Dockerfile"
  platforms  = ["linux/amd64"]
}

target "bundle" {
  context   = "product/inference"
  target    = "verify"
  platforms = ["linux/amd64"]
  contexts = {
    runtime-base = "target:base"
  }
}

target "verify-decider-27b" {
  inherits   = ["bundle"]
  dockerfile = "bundles/decider-27b/Dockerfile"
}

target "verify-linden-1-sglang" {
  inherits   = ["bundle"]
  dockerfile = "bundles/linden-1-sglang/Dockerfile"
}

target "verify-kev-9b" {
  inherits   = ["bundle"]
  dockerfile = "bundles/kev-9b/Dockerfile"
}

target "verify-training" {
  inherits   = ["bundle"]
  context    = "product"
  dockerfile = "inference/training/Dockerfile"
}

target "verify-host" {
  inherits   = ["bundle"]
  context    = "."
  dockerfile = "product/inference/bundles/host/Dockerfile"
}

target "verify-glm-5-3-flash-sglang" {
  inherits = ["bundle"]
  dockerfile = "bundles/glm-5-3-flash-sglang/Dockerfile"
}

target "verify-kimi-k31-pro" {
  inherits = ["bundle"]
  dockerfile = "bundles/kimi-k31-pro/Dockerfile"
}

target "verify-deepseek-v4-1-flash-sglang" {
  inherits = ["bundle"]
  dockerfile = "bundles/deepseek-v4-1-flash-sglang/Dockerfile"
}
