# Private Nomad bootstrap verification

Measured on 2026-09-14 (America/Los_Angeles), in the production EKS cluster.
Scope: the private control plane only. No GPU client or model job was enrolled.

## Results

- Nomad CE 2.0.6 runs on three separate nodes in us-east-1a, us-east-1b, and us-east-1c.
- The private API reports three voting Raft peers and exactly one leader.
- Autopilot reports Healthy=true and FailureTolerance=1. All three peers are healthy.
- The five secret containers exist in Secrets Manager. Server TLS and gossip are
  synced into Kubernetes. The CA, operator credential, and ACL bootstrap token
  remain outside Kubernetes. No secret values are stored in this report.
- ACL bootstrap succeeded. Anonymous requests to `/v1/operator/raft/configuration`
  return 403. HTTPS connections without a client certificate, and connections
  with an unrelated self-signed certificate, fail TLS authentication.
- A temporary Nomad variable was written at `gradiated/verification/recovery`.
  It remained readable through nomad-2 while nomad-0 was replaced, and after
  recovery. The variable was then deleted.
- nomad-0 rejoined with the same Raft ID, `0ee71005-25ac-1b09-59a4-f1512721bf0e`.
  Its IP changed from 10.40.101.143 to 10.40.116.80. After replacement, Autopilot
  again reported three healthy voters and one-failure tolerance.
- `/v1/nodes` returns an empty array. No GPU workload was moved.
- Model deployment run 34915304004 succeeded. ECR contains the DeepSeek image at
  `sha256:47615f35b1e1e3f24b060fbf892cfbdd7bf618416d52d842770cb12fba82c215`.
  The reported image size is 8,643,762,466 bytes. GPU execution of this image is
  a separate qualification step.

## Fixes found by the live checks

The four-worker scheduler setting prevented startup under a two-CPU container
limit. Nomad now selects the worker count from available CPUs.

A reused gossip name conflicted with an old pod address after replacement. The
name now includes the pod IP. The Raft ID remains on the persistent volume.
The restart check above passed with this change. Readiness now queries the leader
through the private HTTPS API, and the StatefulSet waits 15 ready seconds before
advancing its ordered rollout. TCP listener readiness alone had hidden this fault.

Two never-used bootstrap volumes had been provisioned in conflicting zones during
failed rollouts. They were replaced before a cluster formed. The successful
recovery check preserved the running cluster's volume and Raft identity.

## Limits and outstanding work

EC2 rejected the extra EKS nodes with VcpuLimitExceeded. The regional standard
On-Demand quota is eight vCPUs. Terraform has applied minimum and desired size six,
but only four nodes exist; Auto Scaling retries the launches. Increase the quota
to at least twelve vCPUs to reach six m7i.large nodes.

The unloaded private bootstrap uses a temporary 100m CPU request per Nomad server,
with a two-CPU limit and 1 GiB memory request. Restore the 500m request after the
capacity increase. These checks do not establish production load capacity.

Public NLB creation remains blocked by the separate AWS account restriction. The
account owner submitted a support ticket. Public RPC Services remain excluded
from the active Kustomize resources. No Runpod-to-Nomad connection was tested.

Before serving cutover: resolve both AWS restrictions, restore CPU reservations
and public RPC endpoints, test client-role certificates and Runpod connectivity,
qualify the model job and health-based recovery, and configure snapshot/restore,
certificate renewal, and quorum alerts.

## Reproduction

Use a local kubectl port-forward to a running Nomad pod's port 4646. Use the
operator certificate and CA from external secret storage. Do not disable TLS
verification. Supply the ACL token from a protected local file, not a logged command.

Read `/v1/status/leader`, `/v1/operator/raft/configuration`,
`/v1/operator/autopilot/health`, and `/v1/nodes`. Confirm the three voting peers and
healthy status. Repeat the operator request without an ACL token, and repeat TLS
connections without a certificate and with an unrelated certificate.

For a bounded recovery check, store a temporary variable, replace one follower
pod, read the variable through another pod, and confirm the original Raft ID
returns as a healthy voter. Delete the variable. Do not replace a second server
until all three are healthy again. This run did not test a simultaneous failure,
a zone outage, snapshot restore, or hostile-client containment.
