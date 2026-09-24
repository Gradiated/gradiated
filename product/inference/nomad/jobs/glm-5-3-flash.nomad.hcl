# Serving job: runtime and reporting are mandatory tasks in the same allocation.
variable "base_id" { type = string }
variable "cpu_mhz" { type = number }
variable "memory_mb" { type = number }
variable "runtime_disk_mb" { type = number }

variable "deployment_id" { type = string }
variable "runtime_revision" { type = string }
variable "status_url" { type = string }

job "glm-5-3-flash" {
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
      port "inference" {
        static = 8888
      }
      port "desmond" {
        static       = 9090
        host_network = "loopback"
      }
      port "runtime" {
        static       = 8000
        host_network = "loopback"
      }
    }
    # Starts with the allocation and is restarted by Nomad independently of vLLM.
    # A separate Unix user keeps the reporting credential out of the runtime.
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
        DESMOND_DEPLOYMENT_ID      = var.deployment_id
        DESMOND_RELEASE            = var.runtime_revision
        DESMOND_MODEL              = "z-ai/glm-5.3-flash"
        DESMOND_MODEL_REVISION     = "84c6a6aa9497188e15a635ba793b0f95a79b1033"
        DESMOND_RUNTIME_HOST       = "127.0.0.1"
        DESMOND_RUNTIME_PORT       = "8000"
        DESMOND_CONTROL_HOST       = "127.0.0.1"
        DESMOND_CONTROL_PORT       = "9090"
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
        check {
          name     = "runtime-and-reporting-ready"
          type     = "http"
          path     = "/health/ready"
          interval = "10s"
          timeout  = "2s"
          # Do not restart a healthy runtime during an ingest outage.
          # Nomad still restarts Desmond when its process exits.
        }
      }
    }
    task "inference-proxy" {
      driver       = "raw_exec"
      user         = "desmond"
      kill_signal  = "SIGQUIT"
      kill_timeout = "60s"
      config {
        command = "/usr/bin/setpriv"
        args = [
          "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs",
          "/usr/sbin/nginx", "-c", "/etc/gradiated/runtime-proxy.conf",
          "-g", "daemon off;",
        ]
      }
      resources {
        cpu    = 250
        memory = 128
      }
    }
    task "vllm" {
      driver         = "raw_exec"
      user           = "runtime"
      shutdown_delay = "10s"
      kill_signal    = "SIGTERM"
      kill_timeout   = "60s"
      config {
        # The agent can switch users; the model must retain none of its capabilities.
        command = "/usr/bin/setpriv"
        args = [
          "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs",
          "/bin/bash", "/opt/gradiated/bin/start-glm",
        ]
      }
      env {
        HOME           = "/home/runtime"
        XDG_CACHE_HOME = "/home/runtime/.cache"
        RUNTIME_HOST   = "127.0.0.1"
        RUNTIME_PORT   = "8000"
        HF_HOME        = "/workspace/gradiated/model-cache"
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
        name     = "glm-5-3-flash-runtime"
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
