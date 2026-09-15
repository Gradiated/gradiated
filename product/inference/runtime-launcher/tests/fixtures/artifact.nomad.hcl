variable "name" { type = string }
variable "checksum" { type = string }
variable "launcher" { type = string }

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

    task "runtime" {
      driver = "raw_exec"
      artifact {
        source      = "https://localhost:19443/bundle.tar.gz"
        destination = "local/runtime"
        options {
          checksum = "sha256:${var.checksum}"
          archive  = "tar.gz"
        }
      }
      config {
        command = var.launcher
        args    = ["${NOMAD_TASK_DIR}/runtime", "--", "literal $(false)"]
      }
    }
  }
}
