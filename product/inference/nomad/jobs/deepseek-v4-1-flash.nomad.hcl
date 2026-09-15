# Candidate job. Validate GPU device support and worker cleanup before submission.
variable "bundle_url" { type = string }
variable "bundle_sha256" { type = string }
variable "base_id" { type = string }
variable "cpu_mhz" { type = number }
variable "memory_mb" { type = number }
variable "runtime_disk_mb" { type = number }

job "deepseek-v4-1-flash" {
  type        = "service"
  region      = "global"
  datacenters = ["dc1"]

  constraint {
    attribute = "${meta.runtime_base_id}"
    value     = var.base_id
  }

  group "replicas" {
    count = 1
    ephemeral_disk {
      size = var.runtime_disk_mb
    }
    constraint {
      operator = "distinct_hosts"
      value    = "true"
    }
    # No spare capacity: require an operator decision after host loss.
    disconnect {
      replace   = false
      reconcile = "keep_original"
    }
    reschedule {
      attempts  = 0
      unlimited = false
    }
    restart {
      attempts = 2
      interval = "2h"
      delay    = "15s"
      mode     = "fail"
    }
    update {
      max_parallel      = 1
      canary            = 0
      min_healthy_time  = "30s"
      healthy_deadline  = "70m"
      progress_deadline = "90m"
      auto_revert       = false
    }
    network {
      mode = "host"
      port "runtime" {
        static       = 8000
        host_network = "loopback"
      }
    }
    task "vllm" {
      driver         = "raw_exec"
      shutdown_delay = "10s"
      kill_signal    = "SIGTERM"
      kill_timeout   = "60s"
      artifact {
        source      = var.bundle_url
        destination = "local/runtime"
        options {
          checksum = "sha256:${var.bundle_sha256}"
          archive  = "tar.gz"
        }
      }
      config {
        command = "/opt/gradiated/bin/runtime-launch"
        args = [
          "${NOMAD_TASK_DIR}/runtime",
        ]
      }
      env {
        RUNTIME_HOST = "127.0.0.1"
        RUNTIME_PORT = "8000"
        HF_HOME      = "/workspace/gradiated/model-cache"
      }
      resources {
        cpu    = var.cpu_mhz
        memory = var.memory_mb
        device "nvidia/gpu" {
          count = 4
          constraint {
            attribute = "${device.model}"
            operator  = "regexp"
            value     = "(^| )B300( |$)"
          }
        }
      }
      service {
        name     = "deepseek-v4-1-flash-runtime"
        provider = "nomad"
        address  = "127.0.0.1"
        port     = "runtime"
        check {
          name     = "runtime-health"
          type     = "http"
          path     = "/health"
          interval = "10s"
          timeout  = "2s"
          check_restart {
            limit = 3
            grace = "65m"
          }
        }
      }
    }
  }
}
