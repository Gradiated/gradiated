variable "name" { type = string }
variable "checksum" { type = string }
variable "launcher" { type = string }
variable "bundle" { type = string }

job "artifact-test" {
  name = var.name
  type = "batch"

  group "test" {
    restart {
      attempts = 0
    }
    reschedule {
      attempts  = 0
      unlimited = false
    }

    task "download-runtime" {
      driver = "raw_exec"
      lifecycle {
        hook = "prestart"
        sidecar = false
      }
      env {
        TEST_BUNDLE = var.bundle
      }
      config {
        command = "/bin/bash"
        args = [
          "/opt/gradiated/bin/fetch-runtime",
          "s3::https://test-bucket.s3.us-east-1.amazonaws.com/bundles/sha256/${var.checksum}.tar.gz",
          var.checksum, "${NOMAD_ALLOC_DIR}/runtime",
        ]
      }
    }
    task "runtime" {
      driver = "raw_exec"
      config {
        command = var.launcher
        args    = ["${NOMAD_ALLOC_DIR}/runtime", "--", "literal $(false)"]
      }
    }
  }
}
