# Wizard onboarding plan: account creation, login, and free credit

- status: proposal for review
- date: 2026-08-27
- owner: Gradiated Ltd
- related: [CLI_ONBOARDING_PLAN.md](CLI_ONBOARDING_PLAN.md), [DATA_MODEL.md](DATA_MODEL.md), [ARCHITECTURE.md](ARCHITECTURE.md)

## Goal

A new user runs `npx -y @gradiated/wizard`, types only an email address and a
six-digit code, and ends up with: a verified Gradiated account, an
organization and workspace, a **$5 free credit**, a created API key, and
OpenCode configured. No console visit, no browser round-trip, no card.

## Verified architecture facts

These were confirmed against the repository before writing this plan:

- Auth is Better Auth `1.6.29` with the magic-link plugin over SES
  (`product/services/api/src/auth.ts`, `auth-email.ts`).
- Better Auth ships an `email-otp` plugin (verified in
  `node_modules/better-auth/dist/plugins/email-otp/`) whose
  `send-verification-otp` endpoint takes `{email, type}` with type
  `sign-in` — **sign-up and sign-in are the same flow**: an unknown email is
  created and verified on `verify-email`; a known email just signs in. This
  is exactly the unified "type your email, we send a code" behavior the
  product wants, and it is already written, hashed-OTP storage included.
- `balance_transactions.source_type` is a closed PostgreSQL enum-like check
  constraint: `stripe_checkout_session`, `stripe_refund`, `stripe_dispute`,
  `generation_settlement_batch`, `openrouter_payment`, `operator`
  (`product/packages/control/src/db/schema/organizations.ts:330`).
- API keys are created through the workspace route machinery; the raw secret
  is returned exactly once at creation (`routes/workspaces.ts:351`).
- Prepaid `billing_accounts.balance` gates admission in Valkey; permissive
  changes (positive top-ups) commit PostgreSQL first, then project
  (DATA_MODEL.md, synchronization table). A signup credit is exactly this
  permissive shape.
- There is no existing signup or self-serve account-creation route; the
  console currently assumes account creation through the browser.

## Design: one signup flow for web and CLI

There is a single signup/sign-in mechanism, and the CLI and the web console
are both clients of it. Nothing in the flow is CLI-specific:

1. The wizard calls Better Auth's standard email-otp endpoints (added to the
   API service through the existing Better Auth handler on `/api/auth/*`)
   with `type: "sign-in"`.
2. The same endpoints power a future "continue with email code" option in
   the console login page, with no second implementation to keep in sync.
3. The only CLI-specific pieces are the two thin wrapper routes that mint a
   key after authentication and apply the signup credit — exactly the parts
   the browser does not need and the parts that must stay product-owned.

This replaces the earlier plan for a custom `public_email_codes` table and
hand-rolled code lifecycle: Better Auth's `verification` storage already
covers code hashing (`storeOTP: "hashed"`), attempt limits
(`allowedAttempts`), expiry (`expiresIn`), and rotation (`rotate`). No new
table and no new code-verification code.

## User-facing flow

The wizard first searches for an existing key before offering anything:

1. `GRADIATED_API_KEY` environment variable;
2. the wizard credential store at `~/.gradiated/credentials.json`;
3. OpenCode's own `auth.json` credential for the `gradiated` provider.

Only when no key resolves does it ask, because an existing customer must not
be pushed into creating a duplicate account:

```text
$ npx -y @gradiated/wizard

  Gradiated setup
  ────────────────────────────────
  opencode  found
  codex     not found
  claude    not found

  No Gradiated key found.
  ? What would you like to do?
    1. Create a free account ($5 credit included)   <- new users
    2. Log in to an existing account                <- existing users
    3. Paste an existing API key                    <- console users

  Email: dev@example.com
  ✓ Code sent to dev@example.com (check spam if it is late)
  Code: 841902

  [signup path]
  ✓ Account created. $5.00 credit applied.
  ✓ API key created: grad_…4f2c   (stored locally; shown once)

  [login path]
  ✓ Logged in as dev@example.com.
  ✓ New API key created for workspace "default": grad_…9a1d (shown once)

  ✓ OpenCode configured (model: gradiated/z-ai/glm-5.3-flash)

  Start coding: opencode
```

`--signup` and `--login` skip the menu; `--yes` with no key prints guidance
instead of prompting. The user never touches a browser, and the wizard never
asks for a password: both paths are Better Auth email identities, so a
wizard-created account can later sign in to the console with the existing
magic link, and an existing account's wizard login needs no console visit.

Under the hood, options 1 and 2 use the **same** email + code exchange
(`send-verification-otp` with `type: "sign-in"` then `verify-email`): the
account is created on first verification if the email is new and signed into
if it exists. The menu choice only changes what happens after verification —
signup wrapper applies the credit and prints it; login wrapper does not.

## Product decisions (proposed values, configurable)

| Decision               | Value at launch          | Rationale                                                        |
| ---------------------- | ------------------------ | ---------------------------------------------------------------- |
| Free credit amount     | **$5.00**                | User decision; matches competitor anchor (Sail gives $5/month)   |
| Grant shape            | One-time per org         | Not monthly; monthly recurring is a P4 decision after abuse data |
| OTP length / TTL       | 6 digits / 5 min (plugin defaults; 10 min if preferred) | Better Auth `email-otp` defaults; configurable in `auth.ts` |
| Code attempts          | 3 per code (plugin default) | Brute-force bound; rotation mints a fresh code on resend      |
| Resend behavior        | `rotate` (new code, old invalidated) | Plugin default                                       |
| Signup protections     | Out of scope for now (section 4) | Advanced controls come later as a separate decision       |

## Implementation

### 1. Auth configuration (`product/services/api/src/auth.ts`)

Add the email-otp plugin beside magic-link:

```ts
import { emailOTP } from "better-auth/plugins";

emailOTP({
  otpLength: 6,
  expiresIn: 600,                 // 10 minutes
  allowedAttempts: 3,
  storeOTP: "hashed",
  sendVerificationOTP: sesSignupCodeSender, // new sender in auth-email.ts
})
```

`disableSignUp` stays `false` so the sign-in OTP creates-and-verifies new
accounts; that single behavior is what makes signup and login one flow.

### 2. Email sending (`auth-email.ts` extension)

Add `createSesOtpCodeSender` beside the magic-link sender: same SESv2 client
and `from` address, subject "Your Gradiated verification code", text and HTML
bodies containing only the six digits and the expiry. No link, because the
wizard is the client (and the console's OTP variant shows the same code in
the browser). The existing test transport pattern gets a parallel
`createTestOtpTransport` for the e2e suite.

SES production access is a prerequisite; if the account is still in sandbox,
request production access as part of this work (AWS support item, days of
lead time — start it first).

### 3. Wrapper routes (`product/services/api/src/routes/signups.ts`)

Two thin, authenticated-after-OTP routes plus the session creation the
plugin provides. All request and response shapes are Zod schemas added to
the existing route manifest so OpenAPI, the browser client and the Rust
fixtures regenerate and CI rejects drift, exactly like every other route.

| Route | Behavior |
| ----- | -------- |
| `POST /api/v1/public/wizard/code` | Body `{email}`. Proxies to Better Auth `send-verification-otp` (`type: "sign-in"`), returning `202 {status:"code_sent"}`. Thin public wrapper so the wizard has one stable surface; signup protections (section 4) will attach here later without a contract change. |
| `POST /api/v1/public/wizard/session` | Body `{email, code}`. Proxies to Better Auth `verify-email` (`type: "sign-in"`), returning the Better Auth session cookie. Lives in the public route group so the wizard never needs to speak Better Auth's own protocol quirks; it is a stability boundary, not a second auth system. |
| `POST /api/v1/public/wizard/key` | Requires the session from the previous call. One transaction: resolve user → single-org default workspace (or most recently selected) → create one API key named `local` (created by the wizard on this machine) → project the credential into Valkey via the existing serving-projector path. Returns `{api_key, organization_id, workspace_id, workspace_name, credit_nano_usd}` where `credit_nano_usd` is the org's signup grant, `0` when the org predates the flow. The key appears here and nowhere else. |
| `GET /api/v1/me` (existing) | Returns the orgs/workspaces for the session; the wizard uses it only in the multi-org case to report which workspace the key landed on. |

The key route contains no credit logic. The grant is not wizard-specific;
it belongs to the organization-creation event (next section).

**Key provenance.** `api_keys.created_by` already records the creating user
(`organizations.ts:138`), and wizard minting runs under the user's session,
so every `local` key is attributable with no schema change. An organization
that already has its credit (or a $0-credit org of any age) works
unchanged: the flow mints a `local` key on the org's workspace and reports
`credit_nano_usd: 0` — no grant attempt, no error. The wizard's credit line
is printed only when the response carries a nonzero amount.

**Credit: general signup logic, not wizard logic.** The $5 grant fires
inside the single shared "create organization for a self-serve signup"
operation in the control package — the same code the console's first sign-in
path uses to bootstrap an org for a brand-new user. Every entry point
inherits it automatically: wizard OTP signup, console magic-link signup, and
any future OAuth signup. A user joining an existing organization through an
invitation never creates an organization, so the grant never fires for them.
Nothing in the flow reads a client header or user agent, and there is no
wizard branch anywhere in the credit path.

**Login semantics.** A code-based login is possession-of-inbox
authentication, the same trust level as the existing magic link, so no new
authentication principle is introduced. Because raw keys are shown exactly
once and digests cannot be reversed, key-minting always creates a **new**
key (named `local`, so users can find and revoke wizard-created keys in the
console); it never attempts to reprint an old one. An email with no account
simply becomes a signup through the same endpoints, which keeps the wizard's
menu cosmetic rather than load-bearing.

Failure semantics follow the house style: any projection failure after the
PostgreSQL commit returns `503` with the committed state left in place;
retrying the key route is safe and creates at most one additional key row.

Email domain checks happen at key-mint, not at OTP send, so the blocklist
can be refreshed without leaking whether a domain is blocked at request time.

### 4. Signup protections — out of scope for this work

No rate limiting, IP budgets, disposable-domain blocklist or grant caps in
this first iteration. Existing bounds are already in place: the email-otp
plugin owns code attempts, expiry and rotation, the unique
`(source_type, source_id)` constraint caps the grant at one per
organization, and the prepaid balance gate stops serving at zero. SES
sending rate and the existing alerting bound delivery-side abuse.

More advanced signup protections (Valkey-windowed IP budgets, disposable
domain lists, per-origin grant caps, possibly a captcha) are a separate
future decision record, driven by observed abuse rather than speculation.
The wrapper routes are designed so such controls slot in at the `code`
route without changing any contract.

### 5. Free credit mechanics

The grant lives in the shared organization-creation operation, not in any
route or client. When a self-serve signup creates its organization, the same
transaction inserts:

- `balance_transactions`: `type='credit'`, `amount=5_000_000_000` (nano-USD,
  $5.00), `source_type='operator'`, `source_id='signup-grant:<org>'`,
  `balance_after=5_000_000_000`.
- `billing_accounts.balance=5_000_000_000` in the same transaction (the
  existing balance-mutation helper does the lock-insert-update pattern).
- Then the permissive Valkey projection: `GatewayAccount.balance` applied as
  a delta by transaction ID through the existing versioned Lua script, so a
  lost acknowledgement cannot double-grant.

The unique `(source_type, source_id)` constraint is the permanent backstop:
any future path that somehow re-grants to the same organization fails the
insert and degrades to "already granted".

The amount is a constant in the shared org-creation code ($5), so marketing
experiments change it in a reviewed commit, not a config toggle. Invoiced
organizations are untouched; this only ever creates prepaid accounts.

Abuse blast radius: a farmed account is capped at $5 of prepaid inference and
is killed by normal prepaid admission at zero balance. At GLM-5.3 Flash
pricing that is roughly 60M input tokens. Farming economics are addressed by
the future signup-protections decision record (section 4), not by this work.

### 6. Wizard changes (`@gradiated/wizard`, P1 package)

- New `account.ts` module: one email-code exchange
  (`POST /public/wizard/code` → `POST /public/wizard/session` →
  `POST /public/wizard/key`) used for both menu options; the signup choice
  only changes the "$5.00 credit applied" line.
- Flow order: detect agents → resolve key (env, stored credential, OpenCode
  `auth.json`) → **if none: menu [create account / log in / paste key]** →
  catalog → model → config write. No smoke generation (see below).
- Menu is skipped with `--signup`, `--login`, or a resolved key. Pasting an
  existing key remains the third option for console users.
- Login multi-org behavior: the key is created on the default or most recent
  workspace; the wizard prints which one and links the console for choosing
  another.
- The wizard prints the credit balance after signup key-mint (from the
  response's `credit_nano_usd`).
- No smoke generation. The wizard writes config and stops; the user's first
  real request in their agent is the smoke test, and one less API call, one
  less message, and one less failure mode at setup time. `gradiated test`
  remains a separate command for anyone who wants the explicit check.

### 7. Console and website

- Console (P3): the login page already offers Google, GitHub, and
  "Email me a sign-in link" (magic link,
  `product/services/console/src/pages/login-page.tsx:170`), and its copy
  already says "Create an account or continue" — so the console already
  covers both signup and login without this plan. The optional P3 addition
  is only an "email me a code" **variant** of the existing email option
  (6-digit code instead of a link, same email-otp endpoints) for users who
  prefer codes or open mail on another device. A banner on the keys page
  noting wizard-created keys (`local` name) is also optional.
- Website quickstart: replace "create a key in the console" with the wizard
  as step 1 for new users; console instructions remain for existing users.
- Privacy page: add the email handling statement for OTP codes (storage as
  hashes in Better Auth's verification table, expiry, no marketing email
  without separate consent).

## Testing

- **Unit**: JSONC merge unaffected; grant idempotency helper.
- **API e2e** (existing route test style, using the plugin's test transport):
  send OTP → verify → session → key-mint → assert PostgreSQL rows (user, org,
  workspace, billing account, exactly one credit movement with the right
  `source_id`) and the Valkey credential projection. Login case: existing
  account with an org, new `local` key, **no** credit row. Invited-user
  case: user added to an existing org, key on that org, no credit. Console
  parity case: a first sign-in through the console path creates the org and
  receives the same grant. Credit idempotency: forcing a second grant for
  the same org fails on the unique constraint. Wrong code 3 times →
  plugin-locked; expired code → re-request.
- **Wizard e2e**: stub server scenario extended with the three wrapper
  routes; assert the written OpenCode config and credential files end to end
  from a fresh `HOME`.
- **Manual gate before enablement**: one real SES email end to end on
  production.

## Observability and rollout

- Metrics: OTP sends / verifies / key-mints / credit grants. Alerts: verify
  failure spike, OTP-send failure (SES) — reuse the existing Alertmanager
  wiring.
- Rollout: no feature flag. The wizard routes are available to everyone as
  soon as they merge and deploy; the staging soak and the manual SES gate
  happen before that deploy. If an emergency disable is ever needed, the
  gateway's 404-shaped routing or removing the route in a release is the
  mechanism, not a runtime flag.
- Work order (each its own reviewed PR):
  1. SES production access request (long lead time — start it first).
  2. email-otp plugin in `auth.ts` + OTP sender + test transport.
  3. Org-creation signup-credit hook (shared logic; console and wizard both
     inherit) + Valkey projection (reuses existing helpers).
  4. Wizard wrapper routes + Zod schemas + generated clients + Rust fixtures.
  5. Wizard `account.ts` + flow reorder + e2e.
  6. Docs, quickstart, privacy statement.
  7. Staging soak, then deploy.

## Explicit non-goals

- No monthly recurring credit (P4 decision after abuse data).
- No password or OAuth identity creation in the wizard; both paths are
  Better Auth email identities and any later console login uses magic link
  or the same OTP.
- No custom code-verification table or lifecycle; Better Auth's email-otp
  plugin owns code hashing, attempts, expiry and rotation.
- No org invitations, team features or multi-workspace selection UI at
  login; the most recent workspace is used and the console remains the
  place to choose another.
- No smoke generation in the wizard; `gradiated test` is a separate command.
- No changes to OpenRouter, invoiced accounts or the gateway.
