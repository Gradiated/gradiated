server {
  num_schedulers = 1
}

plugin "raw_exec" {
  config {
    enabled = true
  }
}

client {
  artifact {
    http_read_timeout = "10s"
  }
}
