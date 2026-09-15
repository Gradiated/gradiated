server {
  num_schedulers = 1
}

plugin "raw_exec" {
  config {
    enabled = true
  }
}

client {
  # This local test does not use cloud instance metadata.
  options = {
    "fingerprint.denylist" = "env_aws,env_gce,env_azure,env_digitalocean"
  }
  artifact {
    http_read_timeout = "10s"
  }
}
