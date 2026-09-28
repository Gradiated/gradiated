# Ops-mcp

The ops MCP server: read-only production diagnostics and instance registration for Gradiated staff and agents behind Google login.

## entrances

- login: a browser completes the MCP OAuth flow through Dex and Google, and a client receives a scoped token
  handler: createAuth in src/auth.ts
  trust: anonymous
  control: none — this is the entrance that establishes the operator identity; staff-only login holds its check
- tools: an operator calls an MCP diagnostic or registration tool
  handler: createHttp in src/http.ts
  trust: operator

## invariants

- staff-only login: An MCP login succeeds only for a verified gradiated.com Google identity with the expected issuer, audience and nonce.
  over: every identity token verifyStaff accepts: outside domains, look-alike domains, unverified email, a wrong nonce, another client, another service, expiry and forged signatures
  via: staff identity verification
  because: the tools read production logs and metrics across tenants and can register GPU machines, so a non-staff login would expose customer operations
  crossing: operator -> production-read
  refuted: removed the gradiated.com domain check from verifyStaff -> the outside and look-alike domain cases failed (2026-09-28)
  kinds: credential, identity
  checklist: capability-authorization declared as staff-only login
  checklist: revalidated-permission dismissed: denied identities and a rotated signing secret revoke existing sessions, which the renewable sessions tests cover
  checklist: message-authenticity declared as staff-only login
  checklist: encrypted-storage dismissed: token families are stored as hashes, not as bearer secrets
  checklist: key-rotation-compatibility dismissed: rotating the signing secret revokes every session by design
  checklist: canonical-encoding dismissed: the email is matched case-insensitively against one anchored domain pattern
  checklist: identity-continuity dismissed: there is no anonymous-to-identified succession to preserve
  checklist: separation-of-duties dismissed: no approval policy applies to login
