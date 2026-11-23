# AWS as a GPU host provider

Status: accepted 2026-11-20 (Josh Snyder). Infrastructure in
`infra/bootstrap/organization` and `infra/bootstrap/gpu-account`; host and
operator code in the paired application PR.

## Decision

Add AWS EC2 as a second GPU host provider beside RunPod. AWS hosts are
ordinary `GpuHost`s: they run the same `gpu-base` image, join the tailnet as
`gpu-bootstrap-<instance id>`, are enrolled and promoted to `tag:gpu-inference`
as `gpu-<instance UUID>`, and are scheduled through Virtual Kubelet. The
gateway, routing, qualification and drain are unchanged.

This supersedes, for GPU hosting only, two launch restrictions in
`infra/AGENTS.md`: a single AWS account, and no provider abstraction. The
abstraction is limited to the `InstanceProvider` interface and the provider
union in the `GpuHost` spec.

The need: PostHog's two decision models (Jeeves and JevK5) run today on
single-L4 `g6.xlarge` instances, five JevK5 and four Jeeves in each of two
regions plus one of each in development, and are to be served as PostHog-private
models through Gradiated on AWS capacity. The planned scale is three times
that fleet.

## Account

Hosts run in a separate member account, `gradiated-gpu-prod`
(`896018808397`, created 2026-11-20), in a `gpu-hosting` OU. Production's account holds RDS, Valkey, the EKS API,
Secrets Manager and KMS; a mistake in a host's or the operator's permissions
there could reach them. In the GPU account it cannot.

- **Network.** Public subnets, no inbound security-group rules, outbound HTTPS
  and Tailscale UDP only. No NAT, peering, transit attachment or route to
  production; a service control policy denies peering and transit attachments.
  Inference arrives inside Tailscale's WireGuard tunnel. Traffic between EC2
  public addresses in one region stays on the AWS network, per AWS.
- **Entry.** Only Identity Center's `AdministratorAccess` role in the
  management account may assume `OrganizationAccountAccessRole`; the default
  trust of the whole management account (which would admit CI's apply role
  and developers) is replaced.
- **Guardrails (SCP on the OU).** No leaving the organization, no root user,
  allowed regions only, no IAM users or access keys, every instance requires
  IMDSv2 with hop limit 1, and only Terraform may change CloudTrail,
  GuardDuty, EBS default encryption, metadata defaults or the serial console.
- **Baseline.** Multi-region CloudTrail with log validation, kept two years
  under governance-mode Object Lock for the first, VPC flow logs (CloudWatch
  Logs, 30 days),
  GuardDuty foundational detection (its runtime agent needs the SSM agent,
  which hosts disable), Inspector EC2 scanning in hybrid mode (agentless,
  from EBS snapshots), IAM Access Analyzer, EBS encryption by
  default with an account KMS key, account-wide S3 public access block, serial
  console off.

## Hosts

- Launched by Terraform from one launch template: a pinned AMI this account
  owns, baked from the Deep Learning Base NVIDIA AMI (root-volume replacement
  cannot name a public AMI, and AWS refuses to copy the Deep Learning AMIs), IMDSv2 required, hop limit 1, no key pair, encrypted gp3 root,
  termination protection, tag `gradiated:managed=gpu-fleet`.
- User-data installs a boot-time launcher and disables SSH and the SSM agent;
  the VM itself has no shell. Tailscale SSH (check mode) lands in the container,
  as on RunPod.
- The launcher reads `gradiated/gpu-bootstrap/<instance id>` with the bootstrap
  instance profile, which can read only the secret tagged with its own
  instance ARN and pull the `inference` repository. The secret names the
  pinned image (only that repository is accepted) and a single-use
  `tag:gpu-bootstrap` key. The launcher runs the container with
  `--gpus all --privileged --cgroupns private`: the host agent needs a writable
  private cgroup tree for pod limits, and the VM runs nothing else.
- After enrollment the operator force-deletes the secret and removes the
  instance profile, so an enrolled host has no AWS credentials.
- Re-imaging replaces the root volume with the launch template's current AMI
  (`CreateReplaceRootVolumeTask`), which keeps the instance ID and its
  capacity. The operator cannot launch, stop, terminate or modify instances.
- The fault domain is `aws:<availability zone>`.

Capacity: `g6` capacity in us-east-1 moves between zones. A reserved host
(`reserved = true`) first takes an open On-Demand Capacity Reservation, which
fails at once in a zone with no capacity, then launches into it. Every host is reserved, so no unreserved host can take a stopped host's slot.
PostHog's hosts `posthog-l4-01`, `-02` and `-04` (us-east-1d) and `-03`
(us-east-1c) each run in their own reservation (`imports.tf`). The account's G/VT quota is 64 vCPUs, with 160 requested.

## Operator access

`gradiated-gpu-fleet-operator` in the GPU account trusts only
`gradiated-prod-gpu-fleet` and `gradiated-prod-ops-mcp`. It can describe hosts,
start them, replace their root volumes, move the bootstrap profile (passing
only that role) and create, replace and delete bootstrap secrets, which it
cannot read back.

## PostHog models

Jeeves and JevK5 are PostHog-private models (`posthog/...`) served to their
API keys. Their hosts carry `extraTaints: gradiated.com/reserved=posthog`; their
pools reserve `posthog` and select `gradiated.com/provider: aws` and
`gradiated.com/gpu-product: L4`. No other model schedules there, and no prompt
or response is persisted on the hosts.

The four reserved hosts are three in us-east-1d and one in us-east-1c: that was
the L4 capacity available on 2026-11-20. Two replicas of each model fill all four,
so at least one model has both replicas in us-east-1d, and an outage of that
zone takes it down. Spreading both models needs a second us-east-1c (or another
zone's) reservation, then a `gradiated.com/fault-domain` spread on each pool.

## Rollout

1. Done 2026-11-20: SCPs enabled on the organization root, `bootstrap/organization`
   and `bootstrap/gpu-account` (no hosts) applied. Request the G/VT on-demand
   vCPU quota (`L-DB2E81BA`, currently 0) in the new account.
2. `gpu_provider_operator_role_arns` (platform-iam) and
   `gpu_provider_pull_role_arns` (registry-secrets) are set; CI applies them on merge.
3. Merge the application PR; add one host, register it through ops-mcp and
   qualify one model. Confirm the host agent's cgroup control and GPU locks
   inside Docker on that host.
4. AWS hosts start observe-only in gpu-fleet; automated re-imaging follows as
   a separate change.
5. Done 2026-11-23: the four L4 hosts are registered as GpuHosts reserved for
   `posthog`. The `jeeves-l4` and `jevk5-l4` pools serve in production directly,
   without a qualification stage, because PostHog was not yet calling the
   models. The worker SDK-qualifies each pod before routing to it.
6. Run `product/inference/runtimes/posthog/parity.py` against the live pods,
   then PostHog cuts over.

## CPU smoke test (2026-11-20)

Measured on an `m7i.large` launched from the launch template, then terminated:
IMDSv2 with hop limit 1, the bootstrap profile and the pinned AMI applied; SSH
and the SSM agent stopped; the launcher waited for, read and validated its own
secret (seen in the console log); the cross-account image pull was refused until
the `registry-secrets` grant is applied, as expected. Root-volume replacement
kept the instance ID, created a volume encrypted with the account key, deleted
the old one and re-ran the launcher from scratch. Naming the public AMI failed
(`InvalidSnapshot.NotFound`); naming the baked AMI succeeded. With the profile
removed, the host could not read a newly written secret. The IAM policy
simulator confirmed the operator's allowed and denied actions. Found and fixed:
the launch template's network interface conflicted with an instance subnet, and
a failed pull left the registry token on disk. Not covered without a GPU and the
merged PRs: the image pull, the tailnet join, enrollment and scheduling.

## Before customer traffic

- Connect the account to Drata. (GuardDuty, Inspector, Access Analyzer, root
  activity and security-control changes already forward to production's
  security bus, so they reach the findings log and incident.io.)
- Give `readonly` and `admin` Identity Center access to the account
  (`bootstrap/identity-center`, whose guard currently admits one account).
- Record the account in the vendor register and the risk register.

## Not chosen

- **Our production account.** Workable with separate subnets and tag-scoped
  IAM, but every guardrail would be a condition inside the account that holds
  production data.
- **EKS GPU nodes.** Simpler networking, but puts customer GPU workloads inside
  the production cluster's trust boundary and splits the fleet into two
  operating models.
- **VPC peering for a private path.** Possible later (the CIDR does not overlap
  production); it adds routes into production's VPC that need their own review.
