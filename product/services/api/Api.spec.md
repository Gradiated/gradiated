# Api

The public HTTP API: browser sessions, the management API, the Stripe webhook and the service ingest endpoints, over the control plane.

## entrances

- auth: a person signs up, signs in or signs out, and Better Auth sets or clears the session cookie
  handler: createAuthService in src/auth/service.ts
  trust: anonymous
  control: none — this is the entrance that establishes a session; Better Auth owns its checks
- auth test routes: a local or end-to-end test reads the magic link or one-time code it was sent
  handler: registerAuthTestRoutes in src/auth/test-routes.ts
  trust: anonymous
  control: none — createApp mounts these routes only when a test mailbox is configured, which production never does
- health: a load balancer or probe asks whether the process is live and its dependencies ready
  handler: registerHealthRoutes in src/routes/health.ts
  trust: anonymous
  control: none — it reports liveness and dependency state only
- models: anyone reads the public hosted-model catalog and its prices; external=true returns supported external provider models in the same format
  handler: registerModelRoutes in src/routes/models.ts
  external loader: createExternalModelCatalog in src/catalog/external-models.ts fetches OpenRouter on demand, caches in API process memory for five minutes, and deduplicates concurrent refreshes; default and external=false requests never call it
  trust: anonymous
  control: none — the catalog is public by design
- waitlist: a visitor joins the waitlist
  handler: registerWaitlistRoutes in src/routes/waitlist.ts
  trust: anonymous
  control: none — public sign-up, limited to 10 requests a minute per IP
- me: a signed-in user reads their own profile and organizations
  handler: registerMeRoutes in src/routes/me.ts
  trust: customer-session
- organizations: a signed-in user lists or creates organizations
  handler: registerOrganizationRoutes in src/routes/organizations.ts
  trust: customer-session
- workspaces: a member manages an organization's workspaces and their API keys
  handler: registerWorkspaceRoutes in src/routes/workspaces.ts
  trust: customer-session
- workspace credentials: a client with a workspace API key or OAuth access token, such as the MCP server, identifies the credential or calls that workspace's routes as its member
  handler: resolveCredentialUser in src/auth/workspace-credential.ts
  trust: workspace-credential
- OAuth authorization: an MCP client registers itself, sends the signed-in user through console consent and exchanges the code for an access token
  handler: mcpOAuthProvider in src/auth/oauth.ts
  trust: anonymous
  control: none — Better Auth's OAuth provider owns registration, PKCE and token checks; workspace consent holds the workspace choice
- playground MCP: a member's playground lists or calls tools on a remote MCP server the member chose
  handler: registerPlaygroundMcpRoutes in src/routes/playground-mcp.ts
  trust: customer-session
- usage: a member reads a workspace's usage
  handler: registerUsageRoutes in src/routes/usage.ts
  trust: customer-session
- generations: a member browses a workspace's generations and captured traces
  handler: registerGenerationRoutes in src/routes/generations.ts
  trust: customer-session
- billing: a member reads the billing account and balance transactions, or starts a top-up
  handler: registerBillingRoutes in src/routes/billing.ts
  trust: customer-session
- wizard key: the wizard, signed in as the user, creates an API key in the default workspace
  handler: registerWizardRoutes in src/routes/wizard.ts
  trust: customer-session
- Stripe webhook: Stripe reports a completed Checkout Session or payment
  handler: registerBillingRoutes in src/routes/billing.ts
  trust: stripe
- deployment status ingest: a GPU host reports the readiness of its model deployments
  handler: createDeploymentStatusIngestApp in src/ingest/deployment-status.ts
  trust: private-network
- profiling ingest: a GPU host sends a batch of profiling samples
  handler: createProfilingIngestApp in src/ingest/profiling.ts
  trust: service-token

## invariants

- signed Stripe webhooks: A Stripe webhook changes a balance only after its signature verifies against the webhook secret.
  over: every event that reaches the Stripe webhook route
  via: rejects and logs an invalid signature
  because: an unsigned or forged event would let anyone credit an organization's balance
  crossing: stripe -> control-plane
  refuted: returned success when the signature failed to verify -> rejects and logs an invalid signature failed (2026-09-28)
  kinds: message
  checklist: destination-confinement dismissed: the webhook sends nothing outbound
  checklist: message-authenticity declared as signed Stripe webhooks
  checklist: input-validation dismissed: the Stripe SDK parses the event only after the signature verifies
  checklist: retry-recognition declared as idempotent balance postings
  checklist: duplicate-suppression declared as idempotent balance postings
  checklist: keyed-ordering dismissed: credits commute, so no ordering domain applies
  checklist: acknowledgment-barrier dismissed: the route returns success only after the posting commits
  checklist: retry-classification dismissed: Stripe owns retries; the route only returns success or an error
- private readiness reports: Deployment status is accepted only on the private GPU control listener and is bound to its configured provider.
  over: every deployment status report on the private listener
  via: fixed provider binding and deployment/runtime validation
  because: GPUs and cluster workloads are trusted serving components, while public clients must not submit readiness observations
  crossing: private-network -> control-plane
  kinds: identity, message
  checklist: capability-authorization declared as private readiness reports
  checklist: message-authenticity declared as private-network authentication; there is no bearer token or signature on this path
  checklist: input-validation declared as exact deployment, provider and runtime-revision validation
  checklist: identity-continuity declared as a fixed provider on this listener
  checklist: separation-of-duties dismissed: SDK qualification runs in EKS before a replica is made available; GPU reports alone cannot promote an unqualified pod
- tokened profiling reports: A profiling batch is accepted only with the profiling bearer token.
  over: every request to the profiling ingest route: a missing token, a non-Bearer scheme and a wrong token of the same length
  via: profiling ingestion
  because: an open ingest route would let anyone write to ClickHouse
  crossing: service-token -> control-plane
  refuted: removed the bearer token check -> the missing, non-Bearer and wrong-token cases failed (2026-09-28)
  kinds: credential
  checklist: capability-authorization declared as tokened profiling reports
  checklist: revalidated-permission dismissed: a batch applies in the request that carries the token
  checklist: message-authenticity dismissed: batches carry a bearer token, not a signature
  checklist: encrypted-storage dismissed: the token lives in Secrets Manager and the environment, not in a store this service writes
  checklist: key-rotation-compatibility dismissed: the token is rotated by redeploying with the new secret
  checklist: separation-of-duties dismissed: no approval policy applies to profiling batches
- session boundary: Every API route outside the public set rejects a request without a session before any control service runs.
  over: every method and path registered on the API app, less the public set: auth, health, docs, the OpenAPI document, models, waitlist and the Stripe webhook
  via: session boundary
  because: the control services trust the user id they receive, so a route that reaches one without a session would act for nobody and expose tenant data
  crossing: customer-session -> control-plane
  refuted: replaced requireUser in the usage route with a fixed user id -> the usage case of session boundary failed (2026-09-28)
  kinds: identity
  checklist: capability-authorization dismissed: a session names a user, not a bounded capability; membership boundary decides what that user may reach
  checklist: canonical-encoding dismissed: Better Auth resolves the session cookie; nothing here normalizes an identity
  checklist: identity-continuity dismissed: there is no anonymous-to-identified succession; a request either carries a session or is refused
- key confinement: A workspace API key or OAuth access token authorizes only its own workspace's routes, as its member, and never credential management or changes to the workspace.
  over: every request with a credential: another workspace's routes, API keys, playground credentials, the workspace resource itself, and routes outside workspaces such as /api/v1/me
  via: a workspace API key on management routes, a workspace OAuth access token on management routes
  because: a leaked inference key or OAuth token must not reach other workspaces, mint longer-lived credentials or archive its workspace
  crossing: workspace-credential -> control-plane
  kinds: credential, identity
  checklist: capability-authorization declared as key confinement
  checklist: revalidated-permission dismissed: each request re-reads the credential's revocation and expiry and the member's membership
  checklist: encrypted-storage dismissed: keys and access tokens are stored as SHA-256 hashes
  checklist: identity-continuity dismissed: a credential always acts as one member
- workspace consent: An OAuth access token carries the workspace the user chose on the consent page, and only one the user can use, or it authorizes nothing.
  over: every consent: a workspace in another organization, an archived workspace, another user's session and a session with no choice
  via: selectOAuthWorkspace, sends a session without a chosen workspace to the consent page
  because: a token without a bounded workspace would act across every workspace the user can reach
  crossing: customer-session -> control-plane
  kinds: identity
  checklist: capability-authorization declared as workspace consent
  checklist: revalidated-permission dismissed: membership is checked again on every request the token makes
- public MCP destinations: The playground MCP proxy connects only to public addresses over HTTPS, without following redirects, and stores nothing it was sent.
  over: every connection the proxy opens: loopback, private, link-local, metadata and mapped IPv6 addresses, hostnames that resolve to them, plain HTTP and redirects
  via: createOutboundFetch
  because: the URL comes from the member, and the API can reach internal services and cloud metadata that a member must not
  crossing: customer-session -> control-plane
  kinds: message
  checklist: destination-confinement declared as public MCP destinations; the address check runs on the resolved address the socket uses
  checklist: input-validation declared as the connection schema: http(s) URLs only and at most ten headers, none the proxy sets itself
  checklist: encrypted-storage dismissed: headers are used for one request and never stored or logged
