# Enrollment supplies the node name and runtime_base_id metadata.
region = "global"
data_dir = "/var/lib/nomad"
plugin_dir = "/opt/nomad/plugins"
client {
  enabled = true
  # Keep allocation paths traversable without exposing private agent state.
  alloc_dir = "/var/lib/nomad-alloc"
  host_network "loopback" { cidr = "127.0.0.0/8" }
  options = {
    "driver.allowlist" = "raw_exec"
    "user.checked_drivers" = "raw_exec"
    "user.denylist" = "root,nomad"
  }
  max_kill_timeout = "60s"
  artifact {
    http_read_timeout = "10m"
    s3_timeout = "10m"
    http_max_size = "20GiB"
    decompression_size_limit = "40GiB"
    # Python environments contain more files than Nomad's 4096-file default.
    decompression_file_count_limit = 200000
  }
  servers = [
    "nomad-0.rpc.gradiated.com:4647",
    "nomad-1.rpc.gradiated.com:4647",
    "nomad-2.rpc.gradiated.com:4647",
  ]
}
server {
  enabled = false
}
acl {
  enabled = true
}
tls {
  http = true
  rpc = true
  verify_server_hostname = true
  verify_https_client = true
  ca_file = "/etc/nomad/tls/ca.pem"
  cert_file = "/etc/nomad/tls/client.pem"
  key_file = "/etc/nomad/tls/client-key.pem"
}
# Keep the client HTTP API local. The client initiates RPC connections to EKS.
addresses {
  http = "127.0.0.1"
}
advertise {
  http = "127.0.0.1:4646"
}

plugin "raw_exec" { config { enabled = true } }
plugin "nomad-device-nvidia" { config { enabled = true } }
