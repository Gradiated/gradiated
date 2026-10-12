# Product analytics

`product/packages/analytics` owns the TypeScript and runtime event contract.
The API emits completed business actions after authorization and a successful
service call. The console emits navigation and interactions, without duplicating
API events. Analytics does not replace billing records or operational metrics.

The console and Vercel website use PostHog's built-in `$pageview` tracking
on initial visits and client-side route changes (`capture_pageview: "history_change"`).
Console visits, including the login page, use `source: console`; website visits
use `source: website`. There are no custom pageview events. The website uses the
public token for production project 604827 from `VITE_POSTHOG_KEY` in Vercel's
Production environment. Local and preview builds are disabled unless their
environment supplies a separate `VITE_POSTHOG_KEY`. Website tracking is initialized
only by the browser entry point, so prerendering does not emit visits. Website
URL properties retain paths but exclude query strings and fragments; form
autocapture, exception capture and session recording are disabled.

## Identity and groups

Every product event has `schema_version: 1` and `source: api | console`.
PostHog `distinct_id` is the persisted user ID for authenticated events.
Sign-in initiation/link delivery use the browser's anonymous identity, joined
by the existing user identification after authentication. Email is a person
property, set at server signup and console identification.

Group types are `organization` and `workspace`, keyed by persisted UUIDs.
Workspace events include both `organization_id` and `workspace_id`, attaching
both `$groups`; org-only events attach only the organization group. Workspace
group properties are `organization_id` and `is_default`; organization group
properties include `status`. API events use the actual resource's ownership,
resolving it through the workspace store where necessary. The console
sets the selected groups when authenticated pages load. Scope changes reset
those groups; logout resets identity. The final SDK send hook reconstructs event groups to prevent its
automatic persistence merge attaching an unrelated workspace to org-only events.

Strict schemas exclude names, API secrets/digests/prefixes, prompts, trace
payloads, and checkout/download URLs. Page leaves, autocapture and session
recording are disabled. Standard pageviews retain URL paths but exclude query
strings and fragments, including initial person URL properties. URL properties
are stripped from custom console events at the final SDK boundary.

## Implemented events

**Org** means `organization_id`; **workspace** means both `organization_id`
and `workspace_id`. Common properties above apply to every row.

| Event                                 | Source  | Properties                              | Trigger                                                                        |
| ------------------------------------- | ------- | --------------------------------------- | ------------------------------------------------------------------------------ |
| `user_signed_up`                      | API     | workspace, `user_id`                    | New-user hook after personal scope provisioning; stable event UUID is user ID. |
| `user_signed_in`                      | API     | `user_id`, `session_id`                 | Auth session created; stable UUID is session ID. No selected group assumed.    |
| `organization_created`                | API     | org, `default_workspace_id`             | Explicit org creation succeeds.                                                |
| `organization_settings_updated`       | API     | org, `changed_fields`                   | PATCH succeeds; field names only.                                              |
| `workspace_created`                   | API     | workspace, `is_default`                 | Explicit creation, including a new org's default workspace.                    |
| `workspace_settings_updated`          | API     | workspace, `changed_fields`             | PATCH succeeds; field names only.                                              |
| `workspace_archived`                  | API     | workspace                               | Archive accepted; content deletion may remain pending.                         |
| `api_key_created`                     | API     | workspace, `api_key_id`, `has_expiry`   | Key creation succeeds; no secret or name.                                      |
| `api_key_revoked`                     | API     | workspace, `api_key_id`                 | Revocation succeeds.                                                           |
| `billing_checkout_started`            | API     | org, `amount_nano_usd`, `currency: USD` | Checkout created; integer-string amount, not payment completion.               |
| `task_settings_updated`               | API     | workspace, `task_id`, `changed_fields`  | Task PATCH succeeds; field names only.                                         |
| `training_run_requested`              | API     | workspace, `task_id`, `run_id`          | Manual request accepted, not actual execution start.                           |
| `training_run_cancellation_requested` | API     | workspace, `run_id`                     | Cancellation accepted, not actual termination.                                 |
| `task_version_promoted`               | API     | workspace, `task_id`, `version_id`      | Production version update succeeds.                                            |
| `sign_in_started`                     | Console | `method: google                         | github                                                                         | magic_link` | Sign-in initiated. |
| `sign_in_link_sent`                   | Console | `method: magic_link`                    | Magic-link request succeeds.                                                   |
| `sign_out_clicked`                    | Console | `user_id`                               | Explicit sign-out clicked; not proof of session termination.                   |
| `organization_selected`               | Console | org                                     | Explicit org choice.                                                           |
| `workspace_selected`                  | Console | workspace                               | Explicit workspace choice.                                                     |
| `api_key_create_clicked`              | Console | workspace                               | Create-key dialog opened.                                                      |
| `api_key_copy_clicked`                | Console | workspace, `api_key_id`                 | Copy clicked; no secret, not proof of clipboard success.                       |
| `billing_top_up_clicked`              | Console | org                                     | Valid top-up form submitted.                                                   |

Signup records its initial personal scope in one `user_signed_up` event, without
also emitting explicit org/workspace creation events. Training remains gated.

## Draft follow-up events

These are proposed, not emitted or accepted by the current schemas.

| Event                                           | Owner                     | Proposed properties                                                                                      |
| ----------------------------------------------- | ------------------------- | -------------------------------------------------------------------------------------------------------- |
| `model_created`                                 | API/control mutation      | `model_id`, `model_kind`; workspace/org for private models. Current catalogue API is read-only.          |
| `invitation_created`, `invitation_accepted`     | API                       | org, `invitation_id`, `role`; no invite token/email.                                                     |
| `billing_top_up_completed`                      | Billing webhook           | org, `balance_transaction_id`, `amount_nano_usd`, `currency`; deduplicate by transaction.                |
| `training_run_completed`, `training_run_failed` | Training lifecycle/worker | workspace, `task_id`, `run_id`, optional `version_id`, bounded failure category; include scheduled runs. |
| `first_inference_completed`                     | Settlement/worker         | workspace, `model_id`, first generation ID; durable once-per-workspace milestone.                        |
| `connect_snippet_copied`                        | Console                   | workspace, language, integration method; no snippet contents.                                            |

## Configuration and notifications

Use the same PostHog project for the API and console in each environment, with
separate development and production projects.

- Console: `VITE_POSTHOG_KEY`, `VITE_POSTHOG_HOST` (US ingestion by default).
  Production builds use the required `CONSOLE_POSTHOG_KEY` GitHub variable.
- Website: set `VITE_POSTHOG_KEY` to project 604827's public token in the Vercel
  Production environment. Production Vercel builds reject a missing key.
  `VITE_POSTHOG_HOST` can override the US ingestion host. Leave Development and
  Preview keys unset, or use a separate project's key to keep that traffic out
  of production. Keep token values in deployment configuration, outside Git.
- API: `POSTHOG_KEY`, `POSTHOG_HOST` (US ingestion by default). Production loads
  its existing `api` secret from `gradiated/prod/product/api` in Secrets Manager;
  add these fields there and roll the API through normal deployment. No new
  infrastructure is needed. An unset key disables that emitter.
- Local API analytics stay off by default. Set its key to the console's
  development project when testing. Tests use fake transports.
- Enable `organization` and `workspace` [group analytics](https://posthog.com/docs/product-analytics/group-analytics)
  in the target PostHog project.

Create a PostHog realtime destination or workflow filtered to `user_signed_up`
and `source = api`, then choose Slack/email/webhook delivery. The person email
and org/workspace IDs are available for the message. Key creation and training
requests can use their respective API events. Checkout initiation must not
trigger a payment-received notification: that follow-up event is not implemented.
See [Slack destinations](https://posthog.com/docs/cdp/destinations/slack) and
[Workflows](https://posthog.com/docs/workflows). No destinations or outbound
notifications are configured by the repository.

## Delivery and verification

The server uses the [capture endpoint](https://posthog.com/docs/api/capture).
Network errors, 429s and 5xx responses retry once, with a 3-second timeout per
attempt and a stable UUID/timestamp. At most 1,000 deliveries and 1,000 ownership
lookups are pending. Shutdown drains pending work. Failures log
`analytics_delivery_failed` without payloads and do not fail business actions.
This is server-sourced best-effort analytics with an in-memory queue, not durable
notification delivery; process loss or prolonged outages can lose events.
Repeated idempotent mutations may emit repeated events; signup/session UUIDs
are stable. Wrong-source events and unknown properties are rejected.

From `product`, run:

```sh
mise exec -- pnpm exec turbo run check --filter=@gradiated/analytics --filter=@gradiated/api --filter=@gradiated/console --env-mode=loose
```

After configuration, verify signup, resource creation and scope switching in
PostHog before enabling notifications.
