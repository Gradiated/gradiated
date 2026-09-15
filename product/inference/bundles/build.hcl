target "base" {
  context    = "product/inference"
  dockerfile = "images/nomad-base/Dockerfile"
  platforms  = ["linux/amd64"]
}

target "verify" {
  context    = "product/inference"
  dockerfile = "bundles/deepseek-v4-1-flash/Dockerfile"
  target     = "verify"
  platforms  = ["linux/amd64"]
  contexts = {
    runtime-base = "target:base"
  }
}
