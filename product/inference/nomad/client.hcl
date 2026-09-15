# Merge these connection settings into the qualified GPU client configuration.
# Driver configuration, GPU discovery, and runtime user separation are separate.
region = "global"
data_dir = "/var/lib/nomad"
client {
  enabled = true
  max_kill_timeout = "60s"
  artifact {
    http_read_timeout = "10m"
    s3_timeout = "10m"
    set_environment_variables = "AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY,AWS_SESSION_TOKEN,AWS_REGION"
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
