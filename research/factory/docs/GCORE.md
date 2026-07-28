# Gcore GPU bare-metal provider

Gcore is registered in [`data/providers.json`](../data/providers.json) for
user-managed GPU bare-metal clusters. The provider adapter is intentionally
read-only: it discovers regions, flavor capacity and prices, images, existing
user-managed clusters, and a one-server quota probe. It never creates or
deletes a cluster.

## Credentials

Keep values outside the repository. The configured host-only environment file
uses these names:

```text
GCORE_API_KEY
GCORE_PROJECT_ID
GCORE_REGION_ID              # optional; blank discovers all GPU bare-metal regions
GCORE_SSH_KEY_NAME            # used later by a campaign-owned create workflow
GCORE_SSH_USERNAME            # image-specific; auto discovery is supported
GCORE_SSH_PRIVATE_KEY_PATH    # local path only; never commit the key
```

For an interactive shell on the server:

```bash
set -a
source /root/.config/gradiated/gcore.env
set +a
```

## Find availability and prices

Run this from the repository root:

```bash
research/factory/tools/grad-profile providers --provider gcore
```

The command refreshes this page when the embedded snapshot is more than 24
hours old. It prints the same inventory as JSON for scripts, while the tables
below remain the human-readable record. Use the cached page without making an
API request with:

```bash
research/factory/tools/grad-profile providers --provider gcore --offline
```

Capacity and prices are vendor-reported and can change between refreshes;
capacity is not a reservation guarantee. A flavor with capacity may still
fail a later allocation, so a campaign should re-check limits immediately
before provisioning and record the selected region, flavor, image, rate, and
budget.

## Provisioning boundary

Provisioning and cleanup remain campaign-owned. Before creating anything,
select a region with a non-disabled flavor and capacity, check the quota result
below, confirm the spend cap, then create a user-managed cluster with the
project's SSH key. The exact SSH login username comes from the selected image;
the configured `auto` value is not itself a Gcore API username.

Gcore API operations used by the inventory are:

- GPU regions with bare-metal support
- GPU bare-metal flavors with `include_capacity=true&include_prices=true`
- GPU bare-metal images
- existing clusters filtered by `managed_by=user`
- `check_limits` for one server using an external IPv4 interface

The first host must still pass `grad-profile probe`; Nsight Systems and Nsight
Compute counter access is unverified until it is measured on that host.

<!-- gcore-inventory-meta: {"project_id":"1222266","provider":"gcore","refresh_interval_hours":24,"regions":[{"clusters":[],"country":"US","errors":[],"flavors":[{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8468","disk":"2x960gb NVMe, 4x7.68TB NVMe RI SSD | 8xNvidia L40s ","gpu":"NVIDIA L40S-8GPU (48GB)","network":"2x25G","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"l40s","nic_eth":"2x25","nic_ib":null},"name":"bm3-infrastructure-ai-large-l40s-48-8","price":{"currency_code":"EUR","price_per_hour":10.368,"price_per_month":7464.96,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":false}}],"has_baremetal":true,"id":14,"images":[{"architecture":null,"created_at":"2026-07-14T15:02:18Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"0889711f-d04b-4c7a-9ac0-339e42677e3d","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-24T02:30:08Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:28Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"08962020-43a5-4b1f-ad08-d9d66b18d0ec","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-02-06T14:58:52Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T14:45:04Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"bd86b39c-9c00-417c-9ea3-fe9516845333","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:13Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:51:15Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"d5411cae-839f-4063-9e8c-60fb5444f59e","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:07Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:31Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"4ad39413-5c30-42c0-a5c3-a5f3b737d308","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-02-06T14:54:40Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T12:58:40Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"3283be52-2649-49b6-b197-a67c9f5bca59","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:29:54Z","visibility":"public"}],"name":"Manassas","quota_check":{"baremetal_gpu_l40s_count_limit":0,"baremetal_gpu_l40s_count_requested":1,"baremetal_gpu_l40s_count_usage":0}},{"clusters":[],"country":"SG","errors":[],"flavors":[],"has_baremetal":true,"id":18,"images":[],"name":"Singapore"},{"clusters":[],"country":"LU","errors":[],"flavors":[{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8468","disk":"2x960gb NVMe, 4x7.68TB NVMe RI SSD | 8xNvidia L40s ","gpu":"NVIDIA L40S-8GPU (48GB)","network":"2x25G","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"l40s","nic_eth":"2x25","nic_ib":null},"name":"bm3-infrastructure-ai-large-l40s-48-8","price":{"currency_code":"EUR","price_per_hour":10.368,"price_per_month":7464.96,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":false}}],"has_baremetal":true,"id":76,"images":[{"architecture":null,"created_at":"2026-07-14T14:07:31Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"543c6823-fea1-4824-a98e-49668cccf081","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-17T09:59:59Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:24Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"e2229957-d3f7-4a0c-98a4-f22918e356bd","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-06-10T07:01:14Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:51:26Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"0dad8e81-3d47-4ed4-87e2-6c90b2bc7789","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:21Z","visibility":"public"},{"architecture":null,"created_at":"2025-03-05T09:26:37Z","cuda_toolkit_version":null,"disk_format":"qcow2","gpu_driver":null,"gpu_driver_type":null,"gpu_driver_version":null,"hw_firmware_type":null,"id":"2108dd06-bdcd-4e7f-8e69-d863c0043bf1","metadata":{},"min_disk":0,"min_ram":0,"name":"ubuntu-22.04-x64-nvidia-a100/h100-eni","os_distro":"nvidia-a100/h100-ubuntu","os_type":"linux","os_version":"22.04-eni","size":4403363840,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2025-03-05T13:11:56Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:23:08Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"ce420622-e38a-4312-8fcd-ed08cf366a2f","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:11Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:32Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"f5e00f74-fc35-42dc-9c3c-ad61b117e8c6","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-06-10T07:01:14Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T12:58:40Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"9e9276b4-cbca-4816-af12-eb85c02eef9f","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:29:55Z","visibility":"public"},{"architecture":null,"created_at":"2024-11-07T11:13:16Z","cuda_toolkit_version":null,"disk_format":"qcow2","gpu_driver":null,"gpu_driver_type":null,"gpu_driver_version":null,"hw_firmware_type":null,"id":"363ba07b-2ea7-4964-b018-0a3a16ef2b31","metadata":{},"min_disk":0,"min_ram":0,"name":"ubuntu-22.04-x64-nvidia-a100/h100-550-12.4-eni","os_distro":"nvidia-a100/h100-ubuntu","os_type":"linux","os_version":"22.04-550-12.4-eni","size":11708902912,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-06-10T07:01:14Z","visibility":"public"}],"name":"Luxembourg-2","quota_check":{"baremetal_gpu_l40s_count_limit":0,"baremetal_gpu_l40s_count_requested":1,"baremetal_gpu_l40s_count_usage":0}},{"clusters":[],"country":"KR","errors":[],"flavors":[{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8480+","disk":"8 x 3.84 TB NVMe","gpu":"NVIDIA H100-8GPU (80GB)","network":"3.2 Tbit/s Infiniband","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h100","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-1xlarge-h100-80-8","price":{"currency_code":"EUR","price_per_hour":21.816,"price_per_month":15707.52,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":false}},{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8480+","disk":"8x3.84 TB NVMe","gpu":"NVIDIA H100-8GPU (80GB)","network":"2x100Gbit/s Ethernet","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h100","nic_eth":"2x100","nic_ib":null},"name":"bm3-ai-1xlarge-noib-h100-80-8","price":{"currency_code":"EUR","price_per_hour":21.816,"price_per_month":15707.52,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":false}},{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8480+","disk":"8 x 3.84 TB NVMe","gpu":"NVIDIA H100-8GPU (80GB)","network":"3.2 Tbit/s Infiniband","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h100","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-spot-large-h100-80-8","price":{"currency_code":"EUR","price_per_hour":15.708,"price_per_month":11309.76,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":false}}],"has_baremetal":true,"id":140,"images":[{"architecture":null,"created_at":"2026-07-15T10:39:58Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"db3d95f1-4054-4a49-8980-faf42cf40e27","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:36Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:32Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"0b94446b-b70f-4f09-9846-8fe47f2ccfcc","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-02-06T15:17:34Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-15T08:23:47Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"271895e8-e3d2-4ada-938d-2cfb31e4d753","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:23Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T14:07:17Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"bb292cce-64a9-40f3-bd6b-74c8fb02404c","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:14Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:42Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"4635704c-fbc3-4296-b9e5-cab690bd5f7b","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-02-06T15:16:55Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T12:58:46Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"f280d224-dd11-42e0-b575-c1aa26bfe7a3","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:00Z","visibility":"public"},{"architecture":null,"created_at":"2024-11-05T20:39:36Z","cuda_toolkit_version":null,"disk_format":"qcow2","gpu_driver":null,"gpu_driver_type":null,"gpu_driver_version":null,"hw_firmware_type":null,"id":"8a48f667-3172-4605-bd8d-9c24ea70ea9c","metadata":{},"min_disk":0,"min_ram":0,"name":"ubuntu-22.04-x64-nvidia-a100/h100-550-12.4-eni","os_distro":"nvidia-a100/h100-ubuntu","os_type":"linux","os_version":"22.04-550-12.4-eni","size":11708902912,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2025-03-05T13:22:25Z","visibility":"public"},{"architecture":null,"created_at":"2024-11-05T20:39:45Z","cuda_toolkit_version":null,"disk_format":"qcow2","gpu_driver":null,"gpu_driver_type":null,"gpu_driver_version":null,"hw_firmware_type":null,"id":"76e677f5-85f6-4ec0-9133-65332cf9f7c3","metadata":{},"min_disk":0,"min_ram":0,"name":"ubuntu-20.04-x64-nvidia-a100/h100-550-11.8-eni","os_distro":"nvidia-a100/h100-ubuntu","os_type":"linux","os_version":"20.04-550-11.8-eni","size":10167386112,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2025-03-05T13:22:08Z","visibility":"public"}],"name":"Incheon","quota_check":{"baremetal_gpu_h100_count_limit":0,"baremetal_gpu_h100_count_requested":1,"baremetal_gpu_h100_count_usage":0}},{"clusters":[],"country":"LU","errors":[],"flavors":[{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8480+","disk":"8 x 3.84 TB NVMe","gpu":"NVIDIA H100-8GPU (80GB)","network":"3.2 Tbit/s Infiniband","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h100","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-1xlarge-h100-80-8","price":{"currency_code":"EUR","price_per_hour":21.816,"price_per_month":15707.52,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":false}},{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2xIntel Xeon 8468 ","disk":"8x3.84 TB NVMe","gpu":"NVIDIA A100-8GPU (80GB)","network":"2x100Gbit/s Ethernet","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"a100","nic_eth":"4x100","nic_ib":null},"name":"bm3-ai-1xlarge-noib-a100-80-8","price":{"currency_code":"EUR","price_per_hour":12.096,"price_per_month":8709.12,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":false}}],"has_baremetal":true,"id":148,"images":[{"architecture":null,"created_at":"2026-07-14T14:07:32Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"308366a7-bf7b-4959-904a-7ca05bf159ab","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-22T23:30:06Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:29Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"5a66e528-0a80-43c4-94ff-2697c5755371","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-14T13:30:06Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:51:25Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"0b670615-ff8b-4882-b6a8-8ef16e210836","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:21Z","visibility":"public"},{"architecture":null,"created_at":"2025-03-05T08:52:58Z","cuda_toolkit_version":null,"disk_format":"qcow2","gpu_driver":null,"gpu_driver_type":null,"gpu_driver_version":null,"hw_firmware_type":null,"id":"0e2600fe-df82-40bf-97f1-0b4b1f8bc9e0","metadata":{},"min_disk":0,"min_ram":0,"name":"ubuntu-22.04-x64-nvidia-a100/h100-eni","os_distro":"nvidia-a100/h100-ubuntu","os_type":"linux","os_version":"22.04-eni","size":4403363840,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2025-03-05T13:21:04Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:23:06Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"0335144b-f06b-487a-bdc6-26c0d31cae0c","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:09Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:44Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"55c480e8-2787-4b63-ae2f-0573c38bcebc","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-14T13:30:06Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T12:58:44Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"b4b51f68-6a93-410a-a6de-622d0c875fb8","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:29:59Z","visibility":"public"},{"architecture":null,"created_at":"2024-11-07T10:09:02Z","cuda_toolkit_version":null,"disk_format":"qcow2","gpu_driver":null,"gpu_driver_type":null,"gpu_driver_version":null,"hw_firmware_type":null,"id":"4f16fa4b-aaba-4ad2-9507-0b192a7067f2","metadata":{},"min_disk":0,"min_ram":0,"name":"ubuntu-22.04-x64-nvidia-a100/h100-550-12.4-eni","os_distro":"nvidia-a100/h100-ubuntu","os_type":"linux","os_version":"22.04-550-12.4-eni","size":11708902912,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2025-03-05T13:20:59Z","visibility":"public"},{"architecture":null,"created_at":"2024-11-07T10:09:23Z","cuda_toolkit_version":null,"disk_format":"qcow2","gpu_driver":null,"gpu_driver_type":null,"gpu_driver_version":null,"hw_firmware_type":null,"id":"af84a6b0-abbb-4ba9-af73-6c06e460afe3","metadata":{},"min_disk":0,"min_ram":0,"name":"ubuntu-20.04-x64-nvidia-a100/h100-550-12.4-eni","os_distro":"nvidia-a100/h100-ubuntu","os_type":"linux","os_version":"20.04-550-12.4-eni","size":10607394816,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2025-03-05T13:20:55Z","visibility":"public"},{"architecture":null,"created_at":"2024-11-07T10:09:10Z","cuda_toolkit_version":null,"disk_format":"qcow2","gpu_driver":null,"gpu_driver_type":null,"gpu_driver_version":null,"hw_firmware_type":null,"id":"a8fc379e-3963-4e28-a4ef-43948c713fc2","metadata":{},"min_disk":0,"min_ram":0,"name":"ubuntu-20.04-x64-nvidia-a100/h100-550-11.8-eni","os_distro":"nvidia-a100/h100-ubuntu","os_type":"linux","os_version":"20.04-550-11.8-eni","size":10167386112,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2025-03-05T13:20:52Z","visibility":"public"}],"name":"Luxembourg-3","quota_check":{"baremetal_gpu_h100_count_limit":0,"baremetal_gpu_h100_count_requested":1,"baremetal_gpu_h100_count_usage":0}},{"clusters":[],"country":"FI","errors":[],"flavors":[{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8480+","disk":"8 x 3.84 TB NVMe","gpu":"NVIDIA H100-8GPU (80GB)","network":"3.2 Tbit/s Infiniband","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h100","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-1xlarge-h100-80-8","price":{"currency_code":"EUR","price_per_hour":21.816,"price_per_month":15707.52,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":false}},{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8480+","disk":"8 x 3.84 TB NVMe","gpu":"NVIDIA H100-8GPU (80GB)","network":"8 x 400G Infiniband","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h100","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-spot-1xlarge-h100-80-8","price":{"currency_code":"EUR","price_per_hour":15.708,"price_per_month":11309.76,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":false}}],"has_baremetal":true,"id":152,"images":[{"architecture":null,"created_at":"2025-02-24T09:53:37Z","cuda_toolkit_version":null,"disk_format":"qcow2","gpu_driver":null,"gpu_driver_type":null,"gpu_driver_version":null,"hw_firmware_type":null,"id":"e660ec88-3f0b-45b9-a52e-e05b4c2a1270","metadata":{},"min_disk":0,"min_ram":0,"name":"ubuntu-22.04-x64-nvidia-a100/h100-570-12.8-eni","os_distro":"nvidia-a100/h100-ubuntu","os_type":"linux","os_version":"22.04-570-12.8-eni","size":14521467392,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-14T13:30:12Z","visibility":"public"},{"architecture":null,"created_at":"2024-11-08T09:50:24Z","cuda_toolkit_version":null,"disk_format":"qcow2","gpu_driver":null,"gpu_driver_type":null,"gpu_driver_version":null,"hw_firmware_type":null,"id":"65d43105-0af1-4550-b527-28f012c61b63","metadata":{},"min_disk":0,"min_ram":0,"name":"ubuntu-22.04-x64-nvidia-a100/h100-550-12.4-eni","os_distro":"nvidia-a100/h100-ubuntu","os_type":"linux","os_version":"22.04-550-12.4-eni","size":11708902912,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-06-23T10:00:10Z","visibility":"public"}],"name":"Helsinki","quota_check":{"baremetal_gpu_h100_count_limit":0,"baremetal_gpu_h100_count_requested":1,"baremetal_gpu_h100_count_usage":0}},{"clusters":[],"country":"PT","errors":[],"flavors":[{"architecture":"x86_64","capacity":1,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8480+","disk":"2 x 1.92 TB NVMe, 6 x 3.84 TB NVMe ","gpu":"NVIDIA H100-8GPU (80GB)","network":"3.2 Tbit/s Infiniband, 2x25Gbit/s Ethernet","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h100","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-ndp-1xlarge-h100-80-8","price":{"currency_code":"EUR","price_per_hour":21.816,"price_per_month":15707.52,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":true}},{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8480+","disk":"2 x 1.92 TB NVMe, 6 x 3.84 TB NVMe ","gpu":"NVIDIA H100-8GPU (80GB)","network":"3.2 Tbit/s Infiniband, 2x25Gbit/s Ethernet","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h100","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-ndp-spot-1xlarge-h100-80-8","price":{"currency_code":"EUR","price_per_hour":15.708,"price_per_month":11309.76,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":true}}],"has_baremetal":true,"id":164,"images":[{"architecture":null,"created_at":"2026-07-14T14:07:34Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"18c97ca3-f832-47e1-992c-7ef88a3e5bd1","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-27T13:00:07Z","visibility":"public"},{"architecture":null,"created_at":"2025-07-11T13:26:57Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"575.57.08","hw_firmware_type":null,"id":"a0e6e6f2-1d23-4841-81cc-fc0038f1ccb9","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-575.57.08-open-12.9.1-v1.12","os_distro":"nvidia-a100/h100-ubuntu","os_type":"linux","os_version":"24.04-575-12.9-eni","size":26843545600,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-24T12:30:08Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:27Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"a808badc-360c-4b67-b5e9-f4e140e1fcc2","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-02-06T14:30:08Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:51:39Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"5dc001b6-f5f3-4f92-8f40-c95d25d64316","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:21Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:23:08Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"aaae0495-840d-4894-8b23-f0b40f22c64a","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-27T15:00:07Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:33Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"51132ab1-a258-4c1c-9856-0e616dedae82","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-24T12:30:08Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T12:58:46Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"2ac06fb2-1338-42c2-870c-7f7ede673ebc","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:29:58Z","visibility":"public"}],"name":"Sines-2","quota_check":{"baremetal_gpu_h100_count_limit":0,"baremetal_gpu_h100_count_requested":1,"baremetal_gpu_h100_count_usage":0}},{"clusters":[],"country":"PT","errors":[],"flavors":[{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8480+","disk":"2 x 1.92 TB NVMe, 6 x 3.84 TB NVMe ","gpu":"NVIDIA H100-8GPU (80GB)","network":"3.2 Tbit/s Infiniband, 2x100Gbit/s Ethernet","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h100","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-ndp2-1xlarge-h100-80-8","price":{"currency_code":"EUR","price_per_hour":21.816,"price_per_month":15707.52,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":false}},{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8480+","disk":"2 x 1.92 TB NVMe, 6 x 3.84 TB NVMe ","gpu":"NVIDIA H100-8GPU (80GB)","network":"3.2 Tbit/s Infiniband, 2x100Gbit/s Ethernet","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h100","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-ndp2-spot-1xlarge-h100-80-8","price":{"currency_code":"EUR","price_per_hour":15.708,"price_per_month":11309.76,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":false}}],"has_baremetal":true,"id":176,"images":[{"architecture":null,"created_at":"2026-07-14T14:07:35Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"f43671d5-a5df-447d-bfc8-41a8a9bbb504","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-21T06:30:08Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:29Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"65ffe2a2-2647-41bf-8581-a6e536a593c5","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-02-06T14:30:43Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:51:36Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"0369cfbb-90f9-4274-acce-74f812860362","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-16T15:30:08Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:23:11Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"c9734863-4a0d-4780-9d92-88a261f06731","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:10Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:32Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"46176f32-fb01-4c84-8f5e-003b990d5caf","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-14T13:30:07Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T12:58:48Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"f7f8c864-1d38-4ea4-b103-c60c93dbfc74","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:29:56Z","visibility":"public"}],"name":"Sines-3","quota_check":{"baremetal_gpu_h100_count_limit":0,"baremetal_gpu_h100_count_requested":1,"baremetal_gpu_h100_count_usage":0}},{"clusters":[],"country":"GB","errors":[],"flavors":[{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8558","disk":"2 x 960 GB NVMe, 6 x 3.84 TB NVMe ","gpu":"NVIDIA H200-8GPU (141GB)","network":"3.2 Tbit/s Infiniband, 2x200Gbit/s Ethernet","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h200","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-1xlarge-h200-141-8","price":{"currency_code":"EUR","price_per_hour":26.184,"price_per_month":18852.48,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":true}},{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8558","disk":"2 x 960 GB NVMe, 6 x 3.84 TB NVMe ","gpu":"NVIDIA H200-8GPU (141GB)","network":"3.2 Tbit/s Infiniband, 2x200Gbit/s Ethernet","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h200","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-spot-1xlarge-h200-141-8","price":{"currency_code":"EUR","price_per_hour":21.816,"price_per_month":15707.52,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":true}}],"has_baremetal":true,"id":184,"images":[{"architecture":null,"created_at":"2026-07-14T14:07:31Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"54588858-c92a-4964-b735-e8b85d86aa21","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:31Z","visibility":"public"},{"architecture":null,"created_at":"2025-07-21T09:47:44Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"575.57.08","hw_firmware_type":null,"id":"18126da2-261a-4e56-a059-82e71477bada","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-575.57.08-open-12.9.1-v1.12","os_distro":"nvidia-a100/h100-ubuntu","os_type":"linux","os_version":"24.04-575-12.9-eni","size":26843545600,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2025-07-21T10:11:02Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:28Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"cd3911c3-d129-4f0d-86e9-4a3796b1d789","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-02-06T14:27:41Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:51:37Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"d9983b19-f49e-4e89-901a-87e85ad805e2","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:19Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:23:08Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"fbfe1836-9dd4-401f-a56b-306d5b26a711","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:08Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:37Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"4f9e4dfd-d37a-4332-9320-b64fc985bf11","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-02-06T14:28:06Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T12:58:44Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"039e45d6-5a75-4024-b305-393a9d55ac95","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:29:57Z","visibility":"public"}],"name":"Chester","quota_check":{"baremetal_gpu_h200_count_limit":0,"baremetal_gpu_h200_count_requested":1,"baremetal_gpu_h200_count_usage":0}},{"clusters":[],"country":"GB","errors":[],"flavors":[{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8462Y+","disk":"2 x 960 GB NVMe, 6 x 3.84 TB NVMe","gpu":"NVIDIA H100-8GPU (80GB)","network":"3.2 Tbit/s Infiniband, 2x25Gbit/s Ethernet","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h100","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-ndlo-1xlarge-h100-80-8","price":{"currency_code":"EUR","price_per_hour":21.816,"price_per_month":15707.52,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":true}},{"architecture":"x86_64","capacity":0,"disabled":false,"hardware_description":{"cpu":"2x Intel Xeon 8462Y+","disk":" 2x960 GB NVMe, 6x3.84 TB NVMe","gpu":"NVIDIA H100-8GPU (80GB)","network":"3.2 Tbit/s Infiniband, 2x25Gbit/s Ethernet","ram":"2TB RAM"},"hardware_properties":{"gpu_count":8,"gpu_manufacturer":"nvidia","gpu_model":"h100","nic_eth":"2x100","nic_ib":"8x400"},"name":"bm3-ai-ndlo-spot-1xlarge-h100-80-8","price":{"currency_code":"EUR","price_per_hour":15.708,"price_per_month":11309.76,"price_status":"show"},"reserved_capacity":0,"supported_features":{"security_groups":true}}],"has_baremetal":true,"id":196,"images":[{"architecture":null,"created_at":"2026-07-14T14:07:31Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"0ec31f5f-f216-4b32-8971-4d850365fc80","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-17T10:00:05Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:27Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"4074c759-6ee0-4d54-9637-63d6c7a72766","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-19T23:00:07Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:51:34Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"79338bc6-b99a-438e-ae33-8e6db9e38db6","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"24.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:23Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T13:23:11Z","cuda_toolkit_version":"13.0.2","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"580.173.02","hw_firmware_type":null,"id":"2a9a6691-f759-448f-ae16-c1a04074f90b","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-580-13.0-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:30:12Z","visibility":"public"},{"architecture":null,"created_at":"2026-02-06T14:04:47Z","cuda_toolkit_version":"12.9.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"87809d38-df93-44ea-b5a7-4e7cb56c6b9a","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.9-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-02T12:00:03Z","visibility":"public"},{"architecture":null,"created_at":"2026-07-14T14:47:53Z","cuda_toolkit_version":"12.8.1","disk_format":"raw","gpu_driver":"nvidia","gpu_driver_type":"open","gpu_driver_version":"570.211.01","hw_firmware_type":null,"id":"3ba1526c-8265-4e17-b0f8-d482d9a45eaf","metadata":{},"min_disk":0,"min_ram":0,"name":"gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38","os_distro":"Ubuntu","os_type":"linux","os_version":"22.04-570-12.8-eni","size":32212254720,"ssh_key":null,"status":"active","tags":[],"task_id":null,"updated_at":"2026-07-15T12:29:59Z","visibility":"public"}],"name":"London-2","quota_check":{"baremetal_gpu_h100_count_limit":0,"baremetal_gpu_h100_count_requested":1,"baremetal_gpu_h100_count_usage":0}}],"retrieved_at_utc":"2026-07-28T10:00:28Z","schema_version":1} -->
<!-- gcore-inventory-start -->
# Gcore GPU bare-metal inventory

Last refreshed: **2026-07-28T10:00:28Z** (automatic refresh window: 24 hours)

Project: `1222266`. Values below are vendor-reported catalog, capacity, pricing, and quota data; they are not a reservation guarantee.

## Manassas (region `14`)

### GPU flavors

| Flavor | Capacity | Disabled | Currency | Hourly | Monthly | Hardware |
| --- | ---: | :---: | :---: | ---: | ---: | --- |
| bm3-infrastructure-ai-large-l40s-48-8 | 0 | no | EUR | 10.368 | 7464.96 | NVIDIA L40S-8GPU (48GB) |

### Quota check (one-server read-only probe)

```json
{
  "baremetal_gpu_l40s_count_limit": 0,
  "baremetal_gpu_l40s_count_requested": 1,
  "baremetal_gpu_l40s_count_usage": 0
}
```

### Images

| ID | Name | Status | GPU driver |
| --- | --- | --- | --- |
| 0889711f-d04b-4c7a-9ac0-339e42677e3d | gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 08962020-43a5-4b1f-ad08-d9d66b18d0ec | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| bd86b39c-9c00-417c-9ea3-fe9516845333 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |
| d5411cae-839f-4063-9e8c-60fb5444f59e | gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 4ad39413-5c30-42c0-a5c3-a5f3b737d308 | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| 3283be52-2649-49b6-b197-a67c9f5bca59 | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |

### Existing user-managed clusters

No existing user-managed clusters returned.

## Singapore (region `18`)

### GPU flavors

| Flavor | Capacity | Disabled | Currency | Hourly | Monthly | Hardware |
| --- | ---: | :---: | :---: | ---: | ---: | --- |
| — | — | — | — | — | No flavor data returned |

### Images

No image data returned.

### Existing user-managed clusters

No existing user-managed clusters returned.

## Luxembourg-2 (region `76`)

### GPU flavors

| Flavor | Capacity | Disabled | Currency | Hourly | Monthly | Hardware |
| --- | ---: | :---: | :---: | ---: | ---: | --- |
| bm3-infrastructure-ai-large-l40s-48-8 | 0 | no | EUR | 10.368 | 7464.96 | NVIDIA L40S-8GPU (48GB) |

### Quota check (one-server read-only probe)

```json
{
  "baremetal_gpu_l40s_count_limit": 0,
  "baremetal_gpu_l40s_count_requested": 1,
  "baremetal_gpu_l40s_count_usage": 0
}
```

### Images

| ID | Name | Status | GPU driver |
| --- | --- | --- | --- |
| 543c6823-fea1-4824-a98e-49668cccf081 | gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| e2229957-d3f7-4a0c-98a4-f22918e356bd | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| 0dad8e81-3d47-4ed4-87e2-6c90b2bc7789 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |
| 2108dd06-bdcd-4e7f-8e69-d863c0043bf1 | ubuntu-22.04-x64-nvidia-a100/h100-eni | active | — |
| ce420622-e38a-4312-8fcd-ed08cf366a2f | gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| f5e00f74-fc35-42dc-9c3c-ad61b117e8c6 | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| 9e9276b4-cbca-4816-af12-eb85c02eef9f | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |
| 363ba07b-2ea7-4964-b018-0a3a16ef2b31 | ubuntu-22.04-x64-nvidia-a100/h100-550-12.4-eni | active | — |

### Existing user-managed clusters

No existing user-managed clusters returned.

## Incheon (region `140`)

### GPU flavors

| Flavor | Capacity | Disabled | Currency | Hourly | Monthly | Hardware |
| --- | ---: | :---: | :---: | ---: | ---: | --- |
| bm3-ai-1xlarge-h100-80-8 | 0 | no | EUR | 21.816 | 15707.52 | NVIDIA H100-8GPU (80GB) |
| bm3-ai-1xlarge-noib-h100-80-8 | 0 | no | EUR | 21.816 | 15707.52 | NVIDIA H100-8GPU (80GB) |
| bm3-ai-spot-large-h100-80-8 | 0 | no | EUR | 15.708 | 11309.76 | NVIDIA H100-8GPU (80GB) |

### Quota check (one-server read-only probe)

```json
{
  "baremetal_gpu_h100_count_limit": 0,
  "baremetal_gpu_h100_count_requested": 1,
  "baremetal_gpu_h100_count_usage": 0
}
```

### Images

| ID | Name | Status | GPU driver |
| --- | --- | --- | --- |
| db3d95f1-4054-4a49-8980-faf42cf40e27 | gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 0b94446b-b70f-4f09-9846-8fe47f2ccfcc | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| 271895e8-e3d2-4ada-938d-2cfb31e4d753 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |
| bb292cce-64a9-40f3-bd6b-74c8fb02404c | gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 4635704c-fbc3-4296-b9e5-cab690bd5f7b | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| f280d224-dd11-42e0-b575-c1aa26bfe7a3 | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |
| 8a48f667-3172-4605-bd8d-9c24ea70ea9c | ubuntu-22.04-x64-nvidia-a100/h100-550-12.4-eni | active | — |
| 76e677f5-85f6-4ec0-9133-65332cf9f7c3 | ubuntu-20.04-x64-nvidia-a100/h100-550-11.8-eni | active | — |

### Existing user-managed clusters

No existing user-managed clusters returned.

## Luxembourg-3 (region `148`)

### GPU flavors

| Flavor | Capacity | Disabled | Currency | Hourly | Monthly | Hardware |
| --- | ---: | :---: | :---: | ---: | ---: | --- |
| bm3-ai-1xlarge-h100-80-8 | 0 | no | EUR | 21.816 | 15707.52 | NVIDIA H100-8GPU (80GB) |
| bm3-ai-1xlarge-noib-a100-80-8 | 0 | no | EUR | 12.096 | 8709.12 | NVIDIA A100-8GPU (80GB) |

### Quota check (one-server read-only probe)

```json
{
  "baremetal_gpu_h100_count_limit": 0,
  "baremetal_gpu_h100_count_requested": 1,
  "baremetal_gpu_h100_count_usage": 0
}
```

### Images

| ID | Name | Status | GPU driver |
| --- | --- | --- | --- |
| 308366a7-bf7b-4959-904a-7ca05bf159ab | gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 5a66e528-0a80-43c4-94ff-2697c5755371 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| 0b670615-ff8b-4882-b6a8-8ef16e210836 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |
| 0e2600fe-df82-40bf-97f1-0b4b1f8bc9e0 | ubuntu-22.04-x64-nvidia-a100/h100-eni | active | — |
| 0335144b-f06b-487a-bdc6-26c0d31cae0c | gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 55c480e8-2787-4b63-ae2f-0573c38bcebc | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| b4b51f68-6a93-410a-a6de-622d0c875fb8 | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |
| 4f16fa4b-aaba-4ad2-9507-0b192a7067f2 | ubuntu-22.04-x64-nvidia-a100/h100-550-12.4-eni | active | — |
| af84a6b0-abbb-4ba9-af73-6c06e460afe3 | ubuntu-20.04-x64-nvidia-a100/h100-550-12.4-eni | active | — |
| a8fc379e-3963-4e28-a4ef-43948c713fc2 | ubuntu-20.04-x64-nvidia-a100/h100-550-11.8-eni | active | — |

### Existing user-managed clusters

No existing user-managed clusters returned.

## Helsinki (region `152`)

### GPU flavors

| Flavor | Capacity | Disabled | Currency | Hourly | Monthly | Hardware |
| --- | ---: | :---: | :---: | ---: | ---: | --- |
| bm3-ai-1xlarge-h100-80-8 | 0 | no | EUR | 21.816 | 15707.52 | NVIDIA H100-8GPU (80GB) |
| bm3-ai-spot-1xlarge-h100-80-8 | 0 | no | EUR | 15.708 | 11309.76 | NVIDIA H100-8GPU (80GB) |

### Quota check (one-server read-only probe)

```json
{
  "baremetal_gpu_h100_count_limit": 0,
  "baremetal_gpu_h100_count_requested": 1,
  "baremetal_gpu_h100_count_usage": 0
}
```

### Images

| ID | Name | Status | GPU driver |
| --- | --- | --- | --- |
| e660ec88-3f0b-45b9-a52e-e05b4c2a1270 | ubuntu-22.04-x64-nvidia-a100/h100-570-12.8-eni | active | — |
| 65d43105-0af1-4550-b527-28f012c61b63 | ubuntu-22.04-x64-nvidia-a100/h100-550-12.4-eni | active | — |

### Existing user-managed clusters

No existing user-managed clusters returned.

## Sines-2 (region `164`)

### GPU flavors

| Flavor | Capacity | Disabled | Currency | Hourly | Monthly | Hardware |
| --- | ---: | :---: | :---: | ---: | ---: | --- |
| bm3-ai-ndp-1xlarge-h100-80-8 | 1 | no | EUR | 21.816 | 15707.52 | NVIDIA H100-8GPU (80GB) |
| bm3-ai-ndp-spot-1xlarge-h100-80-8 | 0 | no | EUR | 15.708 | 11309.76 | NVIDIA H100-8GPU (80GB) |

### Quota check (one-server read-only probe)

```json
{
  "baremetal_gpu_h100_count_limit": 0,
  "baremetal_gpu_h100_count_requested": 1,
  "baremetal_gpu_h100_count_usage": 0
}
```

### Images

| ID | Name | Status | GPU driver |
| --- | --- | --- | --- |
| 18c97ca3-f832-47e1-992c-7ef88a3e5bd1 | gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| a0e6e6f2-1d23-4841-81cc-fc0038f1ccb9 | gcloud-ai-gpu-ubuntu-24.04-575.57.08-open-12.9.1-v1.12 | active | nvidia |
| a808badc-360c-4b67-b5e9-f4e140e1fcc2 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| 5dc001b6-f5f3-4f92-8f40-c95d25d64316 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |
| aaae0495-840d-4894-8b23-f0b40f22c64a | gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 51132ab1-a258-4c1c-9856-0e616dedae82 | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| 2ac06fb2-1338-42c2-870c-7f7ede673ebc | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |

### Existing user-managed clusters

No existing user-managed clusters returned.

## Sines-3 (region `176`)

### GPU flavors

| Flavor | Capacity | Disabled | Currency | Hourly | Monthly | Hardware |
| --- | ---: | :---: | :---: | ---: | ---: | --- |
| bm3-ai-ndp2-1xlarge-h100-80-8 | 0 | no | EUR | 21.816 | 15707.52 | NVIDIA H100-8GPU (80GB) |
| bm3-ai-ndp2-spot-1xlarge-h100-80-8 | 0 | no | EUR | 15.708 | 11309.76 | NVIDIA H100-8GPU (80GB) |

### Quota check (one-server read-only probe)

```json
{
  "baremetal_gpu_h100_count_limit": 0,
  "baremetal_gpu_h100_count_requested": 1,
  "baremetal_gpu_h100_count_usage": 0
}
```

### Images

| ID | Name | Status | GPU driver |
| --- | --- | --- | --- |
| f43671d5-a5df-447d-bfc8-41a8a9bbb504 | gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 65ffe2a2-2647-41bf-8581-a6e536a593c5 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| 0369cfbb-90f9-4274-acce-74f812860362 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |
| c9734863-4a0d-4780-9d92-88a261f06731 | gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 46176f32-fb01-4c84-8f5e-003b990d5caf | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| f7f8c864-1d38-4ea4-b103-c60c93dbfc74 | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |

### Existing user-managed clusters

No existing user-managed clusters returned.

## Chester (region `184`)

### GPU flavors

| Flavor | Capacity | Disabled | Currency | Hourly | Monthly | Hardware |
| --- | ---: | :---: | :---: | ---: | ---: | --- |
| bm3-ai-1xlarge-h200-141-8 | 0 | no | EUR | 26.184 | 18852.48 | NVIDIA H200-8GPU (141GB) |
| bm3-ai-spot-1xlarge-h200-141-8 | 0 | no | EUR | 21.816 | 15707.52 | NVIDIA H200-8GPU (141GB) |

### Quota check (one-server read-only probe)

```json
{
  "baremetal_gpu_h200_count_limit": 0,
  "baremetal_gpu_h200_count_requested": 1,
  "baremetal_gpu_h200_count_usage": 0
}
```

### Images

| ID | Name | Status | GPU driver |
| --- | --- | --- | --- |
| 54588858-c92a-4964-b735-e8b85d86aa21 | gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 18126da2-261a-4e56-a059-82e71477bada | gcloud-ai-gpu-ubuntu-24.04-575.57.08-open-12.9.1-v1.12 | active | nvidia |
| cd3911c3-d129-4f0d-86e9-4a3796b1d789 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| d9983b19-f49e-4e89-901a-87e85ad805e2 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |
| fbfe1836-9dd4-401f-a56b-306d5b26a711 | gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 4f9e4dfd-d37a-4332-9320-b64fc985bf11 | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| 039e45d6-5a75-4024-b305-393a9d55ac95 | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |

### Existing user-managed clusters

No existing user-managed clusters returned.

## London-2 (region `196`)

### GPU flavors

| Flavor | Capacity | Disabled | Currency | Hourly | Monthly | Hardware |
| --- | ---: | :---: | :---: | ---: | ---: | --- |
| bm3-ai-ndlo-1xlarge-h100-80-8 | 0 | no | EUR | 21.816 | 15707.52 | NVIDIA H100-8GPU (80GB) |
| bm3-ai-ndlo-spot-1xlarge-h100-80-8 | 0 | no | EUR | 15.708 | 11309.76 | NVIDIA H100-8GPU (80GB) |

### Quota check (one-server read-only probe)

```json
{
  "baremetal_gpu_h100_count_limit": 0,
  "baremetal_gpu_h100_count_requested": 1,
  "baremetal_gpu_h100_count_usage": 0
}
```

### Images

| ID | Name | Status | GPU driver |
| --- | --- | --- | --- |
| 0ec31f5f-f216-4b32-8971-4d850365fc80 | gcloud-ai-gpu-ubuntu-24.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 4074c759-6ee0-4d54-9637-63d6c7a72766 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| 79338bc6-b99a-438e-ae33-8e6db9e38db6 | gcloud-ai-gpu-ubuntu-24.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |
| 2a9a6691-f759-448f-ae16-c1a04074f90b | gcloud-ai-gpu-ubuntu-22.04-580.173.02-open-13.0.2-bm-v1.14.38 | active | nvidia |
| 87809d38-df93-44ea-b5a7-4e7cb56c6b9a | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.9.1-bm-v1.14.20 | active | nvidia |
| 3ba1526c-8265-4e17-b0f8-d482d9a45eaf | gcloud-ai-gpu-ubuntu-22.04-570.211.01-open-12.8.1-bm-v1.14.38 | active | nvidia |

### Existing user-managed clusters

No existing user-managed clusters returned.

<!-- gcore-inventory-end -->
