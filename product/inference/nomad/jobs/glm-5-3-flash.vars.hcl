replicas        = 1
cpu_mhz         = 32000
memory_mb       = 400000
runtime_disk_mb = 350000
status_url      = "https://api.gradiated.com/v1/deployment-status"

lora_enabled             = true
lora_base_model_revision = "a5b45eb41df6402735dedc900be14a42e8d5e538"
lora_disk_cache_bytes    = 274877906944
lora_download_hosts      = "gradiated-prod-model-artifacts-873716897517.s3.us-east-1.amazonaws.com"
gradiated_api_base_url   = "https://api.gradiated.com"
