# One authenticated ingress per host. The gateway addresses a replica as
# /alloc/<allocation id>/ and this proxy forwards to that allocation's loopback
# runtime port, so runtimes are never published and ports can be dynamic. Model
# jobs register their runtime as the shared service "gradiated-runtime".
job "host-proxy" {
  type = "system"
  node_pool = "all"

  # Hosts enrolled before the proxy run their own ingress on the same port; this
  # constraint goes once they are migrated.
  constraint {
    attribute = "${meta.serving_ingress}"
    value     = "host-proxy"
  }

  group "proxy" {
    restart {
      attempts = 3
      interval = "1m"
      delay    = "5s"
      mode     = "delay"
    }

    network {
      port "inference" {
        static = 8888
      }
    }

    service {
      name     = "host-proxy"
      provider = "nomad"
      port     = "inference"
      task     = "nginx"
      check {
        type     = "http"
        path     = "/healthz"
        interval = "10s"
        timeout  = "2s"
        check_restart {
          limit = 3
          grace = "15s"
        }
      }
    }

    task "nginx" {
      driver         = "raw_exec"
      user           = "desmond"
      kill_signal    = "SIGQUIT"
      kill_timeout   = "60s"
      shutdown_delay = "11m"

      config {
        command = "/usr/bin/setpriv"
        args = [
          "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs",
          "/usr/sbin/nginx", "-c", "${NOMAD_TASK_DIR}/nginx.conf",
          "-g", "daemon off;",
        ]
      }

      template {
        destination   = "local/nginx.conf"
        change_mode   = "signal"
        change_signal = "SIGHUP"
        data          = <<-EOF
          {{- $allocation := env "NOMAD_ALLOC_ID" }}
          {{- $registered := false }}
          {{- range nomadService "host-proxy" }}{{ if eq .AllocID $allocation }}{{ $registered = true }}{{ end }}{{ end }}
          worker_processes 1;
          worker_rlimit_nofile 8192;
          pid {{ env "NOMAD_TASK_DIR" }}/nginx.pid;
          error_log stderr warn;
          events { worker_connections 2048; }
          http {
              access_log off;
              client_max_body_size 32M;
              client_body_temp_path {{ env "NOMAD_TASK_DIR" }}/body;
              proxy_temp_path {{ env "NOMAD_TASK_DIR" }}/proxy;
              fastcgi_temp_path {{ env "NOMAD_TASK_DIR" }}/fastcgi;
              uwsgi_temp_path {{ env "NOMAD_TASK_DIR" }}/uwsgi;
              scgi_temp_path {{ env "NOMAD_TASK_DIR" }}/scgi;
              map_hash_bucket_size 512;
              map $uri $health_check {
                  default 0;
                  /healthz 1;
              }
              map $uri $withdrawn_readiness {
                  default 0;
          {{- if not $registered }}
                  ~^/alloc/[0-9a-f-]+/health$ 1;
          {{- end }}
              }
              map $http_authorization $authorized {
                  default 0;
                  include /etc/gradiated/runtime-proxy-auth.conf;
              }
              server {
                  listen {{ env "NOMAD_PORT_inference" }};
                  if ($health_check) { return 200 "ok\n"; }
                  if ($authorized = 0) { return 401; }
                  if ($withdrawn_readiness) { return 503; }
                  proxy_http_version 1.1;
                  proxy_set_header Connection "";
                  proxy_set_header Authorization "";
                  proxy_buffering off;
                  proxy_request_buffering off;
                  proxy_read_timeout 330s;
                  proxy_send_timeout 330s;
          {{- range nomadService "gradiated-runtime" }}{{ if eq .Node (env "node.unique.id") }}
                  location /alloc/{{ .AllocID }}/ {
                      proxy_pass http://{{ .Address }}:{{ .Port }}/;
                  }
          {{- end }}{{ end }}
                  # The gateway treats an unknown allocation like any failed replica.
                  location / { return 404 "unknown allocation\n"; }
              }
          }
        EOF
      }

      resources {
        cpu    = 250
        memory = 128
      }
    }
  }
}
