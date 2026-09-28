target "base" {
  context    = "product/inference"
  dockerfile = "images/nomad-base/Dockerfile"
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

target "verify-deepseek-v4-1-flash" {
  inherits   = ["bundle"]
  dockerfile = "bundles/deepseek-v4-1-flash/Dockerfile"
}

target "verify-kev-9b" {
  inherits   = ["bundle"]
  dockerfile = "bundles/kev-9b/Dockerfile"
}

target "verify-host-tools" {
  inherits   = ["bundle"]
  dockerfile = "bundles/host-tools/Dockerfile"
}
