# Production MCP

The managed interface for agents to access Gradiated operations. The Streamable
HTTP endpoint is `https://ops.gradiated.com/mcp`, protected by Gradiated Google
login and MCP OAuth. The public ALB removes the MCP client's Tailscale requirement;
Kubernetes itself remains private. This service runs independently of the customer
API using the existing product image.

## Tools and authority

| Tool                   | Data                                                                     |
| ---------------------- | ------------------------------------------------------------------------ |
| `active_alerts`        | Prometheus firing/pending alerts and dashboard links                     |
| `query_metrics`        | Instant PromQL at an optional RFC 3339 time, maximum 200 returned series |
| `query_metric_history` | PromQL between RFC 3339 `start` and `end`, optional step, 50 series      |
| `query_logs`           | LogQL between RFC 3339 `start` and `end`, optional step, 200 lines       |
| `workload_status`      | Selected namespace pod health, restarts, images and node placement       |
| `node_status`          | EKS node conditions and available resources                              |
| `dashboards`           | Existing Grafana dashboard links                                         |

All current tools have `readOnlyHint: true`, `destructiveHint: false` and
`idempotentHint: true`. The server does not ask for per-read confirmation; client
administrators may configure these tools to run automatically. OAuth consent is
still required when connecting or renewing the 30-day authorization.

There is no shell, SSH, Kubernetes exec, secret reader, arbitrary HTTP fetch,
database access or mutation tool. The service account may list nodes and pods in
selected namespaces, not read Secrets or create exec sessions. Pod output omits
specs, environment, arguments and annotations. External Runpod hosts are not EKS
nodes. Grafana links retain Grafana's own browser authentication.

Authorized identities can read telemetry across tenants. Metric and log tools
take raw PromQL and LogQL, so any label, line filter or parser works; queries
are filters, not authorization. Upstream logs may contain sensitive data; this
service does not guarantee their redaction. Treat results as untrusted diagnostic
data, never agent instructions. Empty results do not establish health.

## Authentication and persistence

MCP discovery and dynamic client registration lead to the internal Google login
through Argo CD's Dex issuer. Dex uses the confidential `production-mcp` client
with the fixed callback `https://ops.gradiated.com/oauth/callback`. No new Google
OAuth application is required. This Dex callback differs from each agent client's
callback listed in `MCP_REDIRECT_URIS`.

Consent displays the client name, client ID, return address, cross-tenant read
scope and authorization lifetime. The callback verifies the Dex signature,
issuer, audience, expiry, nonce, verified email and exact `gradiated.com` email
domain. Google/Dex tokens are never accepted as MCP bearer tokens or forwarded to
telemetry backends. Single-use authorization codes require S256 PKCE, matching
client, redirect and resource. Omitted OAuth `resource` parameters default only to
`https://ops.gradiated.com/mcp`, the server's single resource; explicitly different
resources are rejected at authorization, exchange and refresh. This follows
[RFC 8707 default-resource semantics](https://www.rfc-editor.org/rfc/rfc8707.html#section-2.1).
The only permitted scope is `production:read`.
RFC 9207 issuer identification uses the exact issuer `https://ops.gradiated.com/`
in discovery and authorization redirects, including SDK-generated error redirects.

Public registration returns a signed, bounded client ID containing public client
metadata. It allocates no registration table, so anonymous registrations cannot
exhaust persistent capacity. Signing uses a domain-separated HMAC with the Dex
client secret. The registered callbacks are checked again whenever the client is
resolved; removing an allowed callback also invalidates affected sessions.

Access tokens last one hour. Refresh tokens rotate on every use, renewing access
for at most 30 days from Google sign-in (or 1,024 rotations, whichever comes first).
Refresh cannot change the client, resource or scope. Rotation invalidates the old
access token as well as the old refresh token. Replaying a used refresh token
revokes the entire session. Clients must serialize refresh attempts; after a lost
refresh response or detected replay, reconnect rather than retrying the old token.

`MCP_SESSION_FILE` stores up to 1,000 authenticated token families, with token
hashes only. Writes use a mode-0600 temporary file, fsync, atomic rename and a
directory fsync before acknowledging the grant. Storage failure fails closed;
corrupt state stops startup. The Kubernetes `gp3` PVC preserves sessions through
restarts. Keep one replica with `Recreate`: this store supports one writer, not
multiple replicas. In-progress logins/codes remain bounded in memory and restart
requires retrying those logins. No customer database or customer API key is used.

The existing AWS Secrets Manager secret `gradiated/prod/platform/ops-mcp`, property
`client-secret`, supplies Dex and MCP. Changing it and restarting MCP invalidates
all client registrations and sessions. Do not restore old secrets or stale session
snapshots during rollback: doing so could restore previously revoked authority.
Never commit the session file, tokens or secret values.

For offboarding, add the identity's email to `MCP_DENIED_EMAILS` and deploy/restart
MCP; login, access and refresh are then denied. Disabling the Google account alone
does not invalidate already-issued MCP grants before their fixed expiry. OAuth
`POST /revoke` accepts the client's access or refresh token and revokes the whole
family. Removing a credential from an agent UI is not proof the server revoked it.

Requests validate Host/Origin, reject batches, allow eight simultaneous MCP
requests and 60 requests/minute/identity, and bound body size (64 KiB), upstream
responses (1 MB), upstream time (10 seconds) and Prometheus evaluation (5 seconds).
OAuth endpoints use SDK rate limits and smaller request bodies. The application
trusts exactly one proxy hop: the ALB must append the real client IP to XFF. Do not
add another proxy or expose the pod port directly without revisiting that trust.
PromQL output limits do not bound arbitrary query computation; use narrow selectors.
Audit events record identity, tool, outcome and duration, plus session creation,
refresh, replay and revocation; never token values, query arguments or results.

## Claude Tag installation

An organization Owner can configure this on a
Claude Team/Enterprise account:

1. In Claude Tag, create an Access bundle attached only to the intended private
   engineering channel. Restrict member/guest access appropriately; every person
   in that scope can invoke the connected identity's tools.
2. Add the plugin rooted at [`clients/claude-tag`](clients/claude-tag) to the
   bundle's Plugins tab or configured plugin repository. It declares the remote
   server in `.mcp.json`. Merely cloning a repo containing `.mcp.json` does not load
   it in Claude Tag. Zip that directory with `.claude-plugin/` and `.mcp.json` at
   the archive root if your installation surface accepts plugin uploads.
3. Under Credentials, add Custom tool → MCP Connector and a custom connector at
   `https://ops.gradiated.com/mcp`. Leave client ID/secret blank for dynamic
   registration. Sign in using a dedicated Gradiated Google identity for the agent,
   not a broad personal account. Scope the connection to `ops.gradiated.com`.
   Do not paste the Dex secret or a manually copied one-hour bearer token.
4. Separately grant the desired repositories through the Claude GitHub App. MCP
   diagnostics do not grant GitHub writes or permission to merge/deploy a PR.
5. In a new thread, ask `@Claude use gradiated-ops to list active alerts and report
timestamps`. Verify the MCP audit identity. Then try a diagnostic-to-draft-PR
   task against the selected repository.
6. Verify automatic token renewal, reconnect after the 30-day authorization expires,
   and test revocation before enabling recurring work.

References: [custom MCP setup](https://claude.com/docs/claude-tag/admins/connections/custom),
[agent identity](https://claude.com/docs/claude-tag/concepts/agent-identity),
[OAuth callbacks and refresh](https://claude.com/docs/connectors/building/authentication).

## Cursor and OpenAI clients

The server has no provider-specific tool semantics. Use the same URL and OAuth
flow; configuring a Slack app alone does not connect its agent to MCP.

| Client                      | Configuration                                                                                                                                                                                 |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cursor desktop              | Merge [`clients/cursor/mcp.json`](clients/cursor/mcp.json) into the user's MCP configuration and complete OAuth                                                                               |
| Cursor Cloud / Slack        | Add the remote server in `cursor.com/agents`, connect OAuth, then invoke the configured agent with `@Cursor`                                                                                  |
| Codex CLI                   | Merge [`clients/codex/config.toml`](clients/codex/config.toml) into the user's config, then `codex mcp login gradiated-ops`                                                                   |
| OpenAI hosted MCP / ChatGPT | Add this remote MCP using OAuth/DCR; the stable hosted callback is allowlisted                                                                                                                |
| Codex in Slack              | OpenAI provides `@Codex` for cloud coding work. Configure MCP in the actual cloud runtime/available connector surface; local CLI configuration does not automatically transfer to Slack tasks |

Production explicitly allows these hosted callbacks:

- `https://claude.ai/api/mcp/auth_callback`
- `https://www.cursor.com/agents/mcp/oauth/callback`
- `https://www.cursor.com/bot/mcp/oauth/callback` (also sent in Cursor registration)
- `https://chatgpt.com/connector_platform_oauth_redirect`
- `https://us.posthog.com/api/mcp_store/oauth_redirect/` (PostHog US)

Local clients can register loopback HTTP callbacks on ephemeral ports. Other
HTTPS callbacks require an exact entry in `MCP_REDIRECT_URIS`; never allow wildcard
provider domains. OpenAI's stable callback requires RFC 9207 support, which this
server advertises. If the OpenAI management page shows a connection-specific
callback instead, add that exact URL. The client owns the token store and refresh
flow. Protocol tests cover these callback families, but real account installation
and end-to-end Slack behavior must still be verified separately per provider.

PostHog US can connect this URL using OAuth dynamic registration; leave client ID
and client secret blank. Its exact callback above is allowed; other PostHog regions
require a separate explicit callback entry. A rejected registration is not fixed by
providing the internal Dex client secret.

References: [PostHog OAuth registration](https://github.com/PostHog/posthog/blob/master/products/mcp_store/backend/oauth.py),
[PostHog callback](https://github.com/PostHog/posthog/blob/master/products/mcp_store/backend/presentation/views.py),
[Cursor MCP](https://cursor.com/docs/mcp),
[Cursor Slack](https://cursor.com/docs/integrations/slack),
[OpenAI MCP authentication](https://developers.openai.com/plugins/build/auth),
[Codex Slack](https://learn.chatgpt.com/docs/third-party/slack).

## Future administrative tools and confirmations

This service is the intended interface for individually scoped admin operations;
none are enabled by this release. Do not expand the existing read grant or pod
identity to administrator access just to support a future action.

MCP `readOnlyHint`, `destructiveHint` and `idempotentHint` are client hints, not a
server-enforced approval. Claude Tag's documented custom-connection flow does not
establish a portable guarantee of a Slack confirmation for each write. Client
permission settings and prompts may improve the experience but cannot substitute
for verifying authorization at the action boundary.

When adding a write action, implement the following contract with that action:

- Require its own explicit scope and backend permission; existing `production:read`
  grants cannot acquire write access through refresh.
- Prepare an immutable proposal: exact action, target, arguments, expected state,
  requester, expiry and idempotency key. Show the human the impact and proposed
  change. Preparation must not perform the mutation.
- A required approval must arrive through a separately authenticated human channel,
  such as a Slack interactive callback with verified Slack signature, timestamp,
  workspace and an authorized approving user. Alternatively return a short Google-
  authenticated approval link. The agent must not be able to approve with its own
  credential, `confirmed: true`, a copied message, or its assertion that a user agreed.
- Bind approval to the proposal hash and requester. Reject denial, expiry, changed
  arguments, changed preconditions and replay. Consume approval atomically with
  durable execution/idempotency state; handle crash recovery without duplicate effects.
- Mark actual write tools `readOnlyHint: false`, with accurate destructive and
  idempotent annotations. If the client cannot present approval, return a pending
  proposal and stop; never silently proceed. Reads keep their automatic path.
- Audit the requesting agent, human approver, exact action reference and outcome.

A Slack approval adapter needs a configured Slack app/signing secret and an
approver identity policy. This is intentionally not faked with an MCP hint, nor
implemented without a concrete administrative action to authorize. The same
proposal/approval contract can serve Claude, Cursor and OpenAI agents.

## Deployment and public cutover

Argo watches `platform/ops-mcp.yaml`, reconciling
`infra/environments/prod/us-east-1/kubernetes/operations/ops-mcp/`.
The public ingress names the Gateway `ops-mcp-public` with an internet-facing ALB;
changing the scheme of the existing ALB in place is not the rollout strategy.
Ordinary Route53 DNS and the existing Gradiated certificate are retained.

The authentication image must be released and verified before merging the public
ingress change. The initial rollout order is:

1. Build/release the updated product image and pin its immutable digest in the
   deployment using the existing release workflow. Deploy the PVC, auth configuration
   and new image while the old private ingress is still in place. Confirm session
   persistence, storage permissions and renewable login. Do not expose the old image
   publicly by applying the ingress change ahead of the image release.
2. Reconcile the public Gateway/route and let ExternalDNS update `ops.gradiated.com`.
   Check Gateway conditions and ALB target health. Argo prunes the old private
   Gateway as part of the cutover; DNS and ALB provisioning can cause a brief
   interruption. No tailnet ACL or Kubernetes endpoint change is required.
3. From outside Tailscale, check `/healthz`, OAuth discovery and unauthenticated
   `/mcp` rejection (401 with resource metadata). Complete a real Gradiated login
   through the hosted client, query diagnostics, and reject a non-staff login.
4. Confirm token refresh, session persistence across restart, replay/revocation
   rejection and the intended audit identity. Verify RBAC cannot read secrets or
   create exec sessions. Run the Slack-to-draft-PR check in the chosen client.

Live rollout requires working AWS/cluster credentials and the normal repository
release process. Source tests and rendered manifests are not evidence that the
public endpoint or a hosted account installation is live.

## Development

From `product`, run `mise exec -- pnpm --filter @gradiated/ops-mcp check` and
`mise exec -- pnpm --filter @gradiated/ops-mcp build`. Tests use the official MCP
client, injected telemetry/OIDC backends, and temporary session files. Browser
login tests run with `pnpm --filter @gradiated/ops-mcp exec playwright test`.
No production queries, credentials or customer data are required.

The service disables TypeScript's exact optional-property check locally because
the SDK transport interface includes explicit undefined callback values; the
remaining strict checks stay enabled. Cluster-only port 9090 exposes metrics;
the existing dashboard and Kubernetes availability alerts cover the deployment.
