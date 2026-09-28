# Control

The TypeScript control plane: PostgreSQL schema and services for organizations, workspaces, API keys, the model catalog, billing, settlement, usage and traces.

## invariants

- digest-only API keys: A raw API key secret is made only where its digest row is written, and only the digest is stored.
  protects: generateApiKeySecret in src/workspaces/api-key-secret.ts
  chokepoint: createWorkspaceApiKeyService in src/workspaces/service.ts
  over: every key the workspace API key service creates
  via: stores only the digest of a well-formed secret
  because: a leaked database row or backup must not disclose a bearer credential the gateway would accept
  crossing: customer-session -> control-plane
  refuted: stored the raw secret bytes in the digest column -> stores only the digest of a well-formed secret failed; the chokepoint refuted itself automatically (2026-09-28)
  kinds: credential, storage
  checklist: scoped-reads declared as membership boundary
  checklist: capability-authorization dismissed: the Rust gateway accepts keys, and its cargo tests hold that check
  checklist: revalidated-permission dismissed: key creation is synchronous and checks the editor role in the same call
  checklist: message-authenticity dismissed: no signed message crosses this boundary
  checklist: encrypted-storage dismissed: the stored form is a one-way SHA-256 digest of a 256-bit secret, and nothing decrypts it
  checklist: key-rotation-compatibility dismissed: nothing is encrypted, so no key rotates; a customer rotates by creating a new key and revoking the old one
  checklist: input-validation dismissed: the HTTP layer validates names and expiry with Zod before this service runs
  checklist: revision-preservation dismissed: API keys have no revision history
  checklist: separation-of-duties dismissed: no approval policy applies to key creation
  checklist: commit-ordered-effects dismissed: the secret is returned only after the insert completes, and no other external effect follows
  checklist: durable-dispatch-intent dismissed: key creation dispatches no external work
  checklist: declared-target-coverage dismissed: the service writes one PostgreSQL row and fans out to no registry of stores
  checklist: completion-evidence dismissed: creation completes in one synchronous insert
- membership boundary: A user reaches an organization and its workspaces only as an active member of that customer organization.
  over: every organization and workspace read through requireMembership and requireWorkspaceMembership, for suspended members, non-members, distribution-channel members and another organization's workspace
  via: organization access
  because: organization membership is the only human authorization boundary, so a gap here exposes one tenant's keys, usage, traces and billing to another
  crossing: customer-session -> control-plane
  refuted: dropped the active-status condition from activeCustomerMember -> hides the organization and workspace from a suspended member failed (2026-09-28)
  kinds: read, identity
  checklist: scoped-reads declared as membership boundary
  checklist: capability-authorization dismissed: a session names a user, not a bounded capability; membership and role decide what it may do
  checklist: redaction dismissed: the API returns records whole to members, and API key digests never leave the service
  checklist: canonical-encoding dismissed: users, organizations and workspaces are compared by UUID
  checklist: identity-continuity dismissed: there is no anonymous-to-identified succession inside the control plane
- idempotent balance postings: A balance transaction source is applied at most once: a replay returns the first row, and a replay with another amount or organization is refused.
  over: every posting through postBalanceTransaction, from settlement and from Stripe top-ups
  via: billing
  because: settlement and Stripe both retry, and a double posting would charge or credit an organization twice
  crossing: serving-state -> control-plane
  refuted: accepted a replayed source with a different amount or organization -> both replay rejection tests failed (2026-09-28)
  kinds: state
  checklist: revalidated-permission dismissed: postings come from system roles, not from a user's permission
  checklist: separation-of-duties dismissed: no approval policy applies to postings
  checklist: legal-state-succession declared as idempotent balance postings
  checklist: supersession-safety dismissed: a posting never replaces an earlier one; the ledger is append-only
  checklist: worker-fencing dismissed: the settlement session advisory lock elects one writer, and the source key makes a late duplicate harmless
  checklist: commit-ordered-effects dismissed: a posting issues no external effect
  checklist: resumption-coverage dismissed: settlement resumes from posted sources, which the settlement store tests cover
