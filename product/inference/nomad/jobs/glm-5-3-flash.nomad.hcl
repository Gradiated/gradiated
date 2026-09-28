variable "bundle_url" { type = string }
variable "bundle_sha256" { type = string }
variable "base_id" { type = string }
variable "replicas" { type = number }
variable "cpu_mhz" { type = number }
variable "memory_mb" { type = number }
variable "runtime_disk_mb" { type = number }
variable "status_url" { type = string }

locals {
  model_id       = "z-ai/glm-5.3-flash"
  model_revision = "84c6a6aa9497188e15a635ba793b0f95a79b1033"
  release = {
    schema_version     = 1
    runtime_revision   = "glm-${substr(var.bundle_sha256, 0, 12)}"
    model_path         = "zai-org/GLM-5.3-Flash"
    model_revision     = local.model_revision
    tokenizer_path     = "zai-org/GLM-5.3-Flash"
    tokenizer_revision = local.model_revision
  }
}

job "glm-5-3-flash" {
  type        = "service"
  region      = "global"
  datacenters = ["dc1"]

  meta {
    gradiated_model_id = local.model_id
    gradiated_release  = jsonencode(local.release)
  }

  constraint {
    attribute = "${meta.runtime_base_id}"
    value     = var.base_id
  }

  constraint {
    attribute = "${meta.serving_ingress}"
    value     = "host-proxy"
  }

  group "replicas" {
    count = var.replicas

    ephemeral_disk {
      size = var.runtime_disk_mb
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
      interval = "1h"
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
        host_network = "loopback"
      }
      port "warmup" {
        host_network = "loopback"
      }
      port "desmond" {
        host_network = "loopback"
      }
    }

    task "download-runtime" {
      driver       = "raw_exec"
      user         = "downloader"
      kill_timeout = "30s"

      lifecycle {
        hook    = "prestart"
        sidecar = false
      }

      config {
        command = "/usr/bin/setpriv"
        args = [
          "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs",
          "/bin/bash", "/opt/gradiated/bin/fetch-runtime",
          var.bundle_url, var.bundle_sha256, "${NOMAD_ALLOC_DIR}/runtime",
        ]
      }

      resources {
        cpu    = 1000
        memory = 1024
      }
    }

    task "desmond" {
      driver         = "raw_exec"
      user           = "desmond"
      kill_signal    = "SIGTERM"
      kill_timeout   = "10s"
      shutdown_delay = "5s"

      lifecycle {
        hook    = "prestart"
        sidecar = true
      }

      config {
        command = "/usr/bin/setpriv"
        args = [
          "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs",
          "/bin/bash", "/opt/gradiated/bin/start-desmond",
        ]
      }

      env {
        DESMOND_DEPLOYMENT_ID      = "${NOMAD_ALLOC_ID}"
        DESMOND_RELEASE            = local.release.runtime_revision
        DESMOND_MODEL              = local.model_id
        DESMOND_MODEL_REVISION     = local.model_revision
        DESMOND_RUNTIME_HOST       = "127.0.0.1"
        DESMOND_RUNTIME_PORT       = "${NOMAD_PORT_warmup}"
        DESMOND_CONTROL_HOST       = "127.0.0.1"
        DESMOND_CONTROL_PORT       = "${NOMAD_PORT_desmond}"
        DESMOND_STATUS_URL         = var.status_url
        DESMOND_CONTROL_TOKEN_FILE = "/etc/gradiated/runtime-access.token"
        DESMOND_STATUS_TOKEN_FILE  = "/etc/gradiated/deployment-status.token"
      }

      resources {
        cpu    = 250
        memory = 256
      }

      service {
        name     = "glm-5-3-flash-reporting"
        provider = "nomad"
        address  = "127.0.0.1"
        port     = "desmond"
        # Not restarted on failure, so an ingest outage cannot restart a healthy runtime.
        check {
          name     = "runtime-and-reporting-ready"
          type     = "http"
          path     = "/health/ready"
          interval = "10s"
          timeout  = "2s"
        }
      }
    }

    task "vllm" {
      driver         = "raw_exec"
      user           = "runtime"
      shutdown_delay = "10s"
      kill_signal    = "SIGTERM"
      kill_timeout   = "60s"

      config {
        command = "/usr/bin/setpriv"
        args = [
          "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs",
          "/opt/gradiated/bin/runtime-launch", "${NOMAD_ALLOC_DIR}/runtime",
        ]
      }

      env {
        HOME           = "/home/runtime"
        XDG_CACHE_HOME = "/home/runtime/.cache"
        HF_HOME        = "/workspace/gradiated/model-cache"
        RUNTIME_PORT   = "${NOMAD_PORT_runtime}"
        WARMUP_PORT    = "${NOMAD_PORT_warmup}"
      }

      resources {
        cpu    = var.cpu_mhz
        memory = var.memory_mb
        device "nvidia/gpu" {
          count = 2
          constraint {
            attribute = "${device.model}"
            operator  = "regexp"
            value     = "(^| )B300( |$)"
          }
        }
      }

      service {
        name     = "gradiated-runtime"
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
            grace = "60m"
          }
        }
      }
    }
  }
}
