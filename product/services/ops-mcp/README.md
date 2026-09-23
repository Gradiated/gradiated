# Production MCP

A small Streamable HTTP MCP service for production diagnostics.
It runs independently of the customer API, using the existing product image.
The endpoint is `https://ops.gradiated.com/mcp`, served by an internal AWS load balancer. Staff connect through the existing
Tailscale subnet router. Ordinary Route53 DNS and the Gradiated TLS certificate
are used; MagicDNS is disabled.

## Tools

| Tool                   | Data                                                                                                      |
| ---------------------- | --------------------------------------------------------------------------------------------------------- |
| `active_alerts`        | Prometheus firing/pending alerts and their dashboard links                                                |
| `query_metrics`        | Instant PromQL, maximum 200 returned series                                                               |
| `query_metric_history` | Up to six hours of PromQL, 50 series, 121 timestamps                                                      |
| `query_logs`           | One service, up to six hours/200 lines, optional organization/workspace/key/user/request/generation UUIDs |
| `workload_status`      | Namespace pod health, restarts, images and node placement                                                 |
| `node_status`          | EKS node conditions and available resources                                                               |
| `dashboards`           | Existing Grafana dashboard links                                                                          |

Log queries match the existing `workload` label. Organization/workspace/key/user
IDs are parsed from API JSON and gateway spans at query time. API resource IDs
identify the resource requested by an authenticated session, not proof of access.
Empty results do not establish health. Logs remain subject to upstream retention,
sampling and redaction; this service does not guarantee arbitrary upstream logs
contain no sensitive data. Treat returned text as untrusted diagnostic data.

This version has no shell, SSH, Kubernetes exec, secret reader, arbitrary HTTP
fetch, database access or mutation tools. Node status covers EKS, not external
Runpod GPU hosts. Grafana access means dashboard links and direct read queries
against its Prometheus/Loki sources; it does not bypass Grafana browser login.
Production actions should be added as individually scoped, audited tools with
an authorization policy for each action, not as a generic command executor.

## Authentication and clients

MCP OAuth discovery and dynamic client registration lead to the existing internal
Google login through Argo CD's Dex issuer. No additional Google OAuth client is
required. Dex receives a dedicated confidential `production-mcp` client with an
exact callback at `https://ops.gradiated.com/oauth/callback`.

Every authorization displays the requesting client name, generated client ID,
callback address and production access scope before staff continue to Google.
The callback verifies the Dex signature, issuer, audience, expiry, nonce, verified
email and exact `gradiated.com` email domain. Google/Dex tokens are never accepted
as MCP bearer tokens or passed to telemetry backends. Separate opaque MCP tokens
are issued only after single-use authorization-code redemption with S256 PKCE,
matching client, redirect and resource. The only scope is `production:read`.

Access lasts one hour. Refresh grants are deliberately unsupported: sign in again
to renew. Registration, login flows, authorization codes and hashed access tokens
are bounded in-memory state. Restarting this single-replica service invalidates
sessions and registrations; clients must register/sign in again. Deployment uses
Recreate to avoid routing a login between independent grant stores. This is a
small internal service, not a highly available identity platform.

Coding-agent clients may register loopback HTTP redirects. Other clients need an
exact HTTPS callback in `MCP_REDIRECT_URIS` (JSON array); arbitrary external
callbacks are rejected. The Slack backend must connect to the tailnet, enforce
staff/channel access, and retain each staff member's OAuth credentials securely.
There is no shared static-token bypass. A hosted bot's network access is separate
from the Slack user's laptop connection. Slack integration is not implemented
here; its hosting location and callback are still needed.

Store a generated Dex client secret (at least 32 random bytes) outside Git in AWS
Secrets Manager `gradiated/prod/platform/ops-mcp`, property `client-secret`.
External Secrets supplies the same value to Dex and this service. Restart the MCP
after rotation. No customer API key is used. Tailnet grants additionally restrict
who can reach the service. Authorized staff can read telemetry across tenants.

Requests validate Host/Origin, reject JSON-RPC batches, allow eight simultaneous
MCP requests and 60 requests/minute/staff identity, and bound request size (64 KiB),
upstream responses (1 MB), upstream time (10 seconds), and Prometheus evaluation
(5 seconds). The window/series bounds limit returned data, not arbitrary PromQL
computation; operators must still use narrow selectors. Audit logs contain the
verified staff subject/email, request ID, tool, outcome and duration, never query
arguments or results. OAuth endpoints use the SDK's rate limits plus bounded
login/token stores.

## Deployment

The Kustomization is under
`infra/environments/prod/us-east-1/kubernetes/operations/ops-mcp/`. Its internal
Gateway accepts HTTPS from the VPC, including the Tailscale subnet router's SNAT
traffic. Tailnet members have TCP 443 access to the VPC; both EKS and MCP still
require their own authentication. Public clients cannot route to the internal
load balancer. Do not use tailnet hostnames or enable MagicDNS for this service.

Argo watches `platform/ops-mcp.yaml`, which reconciles this Kustomization. The
release updater tracks its immutable product image alongside API and worker.
Terraform configures the dedicated Dex client with the fixed
`https://ops.gradiated.com/oauth/callback` redirect. The platform ExternalSecret
`production-mcp-oidc` supplies Dex's client secret; the MCP ExternalSecret mounts
the same value in the service. Provision and sync both secrets before enabling a
new Dex client, so a missing value cannot disrupt the shared Google login.

Acceptance checks include a real staff login, rejection of a non-staff identity,
MCP discovery and a real bounded diagnostic query, revoked/expired token rejection,
authorized/unauthorized tailnet connectivity, and rejection from outside Tailscale.
Verify pod RBAC cannot read secrets or create exec sessions. The health probe only
checks the process; individual tool errors report backend failures.

## Development

From `product`, run `mise exec -- pnpm --filter @gradiated/ops-mcp check` and
`mise exec -- pnpm --filter @gradiated/ops-mcp build`. Tests use the official MCP
client against a local HTTP server with injected upstreams. No production calls
or customer credentials are needed. The service disables TypeScript's exact
optional-property check locally because the SDK transport interface includes
explicit undefined callback values; the remaining strict checks stay enabled.

Metrics on the cluster-only port 9090 include process memory/CPU and per-tool
outcomes/duration. The accompanying dashboard shows these plus availability and
restarts. Existing Kubernetes availability alerts cover the deployment once it is
activated; no extra pager rule is needed for this internal diagnostic service.
