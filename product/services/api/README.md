# API

The TypeScript HTTP API for the console and website. Routes are authored with
described Zod schemas and generate the OpenAPI document and browser clients.

## Engineer onboarding

The console's `/onboarding?journey=post-training` steps use organization-owned routes. Each
requires a verified active organization admin, rejects staff impersonation and
returns `Cache-Control: no-store`. Local development calls the same providers:
set the keys below in the repository-root `.env` and run the `api` and `console`
mprocs processes. Production credentials belong in the API secret
`gradiated/prod/product/api` (`us-east-1`); preserve its other entries and never
use a `VITE_` variable.

| Route (under `/api/v1/organizations/{organization_id}`) | Purpose                                                                             | Limit per minute |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------- |
| `GET engineer-onboarding`                               | Recorded NDA, Slack channel, GitHub installations, contact channel, submission time | 60               |
| `POST engineer-onboarding/submission`                   | Starts the project once                                                             | 5                |
| `POST nda-documents`, `GET`/`POST …/signing-sessions`   | PandaDoc document and embedded signing                                              | 60; sessions 5   |
| `POST slack-invitations`                                | Creates the channel and sends a Slack Connect invite                                | 5                |
| `GET github-installations`                              | Lists the user's verified Gradiated installations                                   | 30               |

The NDA is optional: the customer opts in, and only a submission that names an
`nda_document_id` requires that document to be completed. The submission
rechecks the chosen GitHub installation with the user's token and requires a
Slack channel when `contact_channel` is `slack`. It records the submission once;
a repeat returns the current state with 200 and sends nothing. The first
submission emails the team, noting whether an NDA was signed, and posts nonempty
notes to the Slack channel. The email is sent before the submission is recorded;
if it fails the API answers 503 and records nothing, so a retry delivers it. Notes are not stored. Conflicts carry a `code`:
`nda_required`, `github_authorization_required`, `github_installation_unverified`
or `slack_channel_required`.

Progress is stored in `organizations.metadata.training_onboarding` (NDA, submission,
contact channel) and the `integrations` table (Slack channel, GitHub
installations); see [DATA_MODEL.md](../../../docs/DATA_MODEL.md).

Each provider is enabled when its secret is set: `PANDADOC_API_KEY`,
`SLACK_BOT_TOKEN`, and the existing `GITHUB_CLIENT_ID` and
`GITHUB_CLIENT_SECRET`. Use a PandaDoc sandbox key locally. Submissions are
emailed to `team@gradiated.com` through Resend.

### PandaDoc mutual NDA

The template ID, approved version (`GRADIATED_NDA_TEMPLATE` in
`src/legal/pandadoc.ts`) and the `Agreement.Date` field are constants; bump the
version when the legal text changes.

The API creates the document, waits for draft readiness, sends it and opens a
15-minute embedded signing session for the signed-in signer. `details` is null
while PandaDoc prepares the document. Reading a completed document records it
as the organization's NDA, replaced only for a new template version. The
PostHog party is pre-filled as PostHog Inc., James Hawkins, Co-CEO. Document creation is not retried automatically; after an uncertain
response, check PandaDoc for a draft before creating another.

Template setup:

1. A role named `Customer` with a required signature field and signing date.
2. Text Merge Fields `Customer.Company`, `Customer.Address`, `Customer.Name`,
   `Customer.Title`, `Customer.Email`, `PostHog.Company`, `PostHog.Signer` and
   `PostHog.Title`.
3. Agree the PostHog countersignature arrangement with the authorized signer.
   The API never fills a signature field.
4. In the template recipient permissions, enable **Email a PDF on completion**.
   In **Recipient experience → Document completion**, enable completion emails
   with the PDF attached.

Before setting the production key, test with a sandbox key: create, send, embedded signing,
completion with all parties, a pending countersignature, changed signer
details, an expired session, cross-organization access and a provider outage.

### Slack Connect

Engineers added to each channel are `GRADIATED_ENGINEER_SLACK_USER_IDS` in
`src/slack/connect.ts`.

Create an internal app from `slack-app-manifest.json` and install it in the
Gradiated workspace with the bot scopes `channels:manage`, `channels:read`,
`conversations.connect:write` and `chat:write`. Reinstall after changing
scopes. Confirm the workspace's Slack Connect plan and approval rules with its
owner.

`POST …/slack-invitations` creates one public `ext-<team>-gradiated` channel
per organization, adds the engineers and emails a Slack Connect invitation.
Later invitations reuse the organization's channel and ignore `channel_name`.
A taken name returns 409 `slack_channel_name_taken`. An organization may send
one invitation per 30 seconds; sooner returns 429 `slack_invitation_cooldown`
with `Retry-After`. Submission notes are posted as plain-text blocks. Mutating
Slack calls are not retried automatically.

Before setting the production token, test channel creation, engineer membership, invitation
delivery and acceptance, and an explicit retry with an authorized external
recipient.

### GitHub App installation

Verification reuses the **Gradiated**
GitHub App (`gradiated`) OAuth credentials in `gradiated/prod/product/github-auth`;
confirm they belong to that app. The app needs read-only Contents permission.
Customers install it from `https://github.com/apps/gradiated/installations/new`.
The app requests user authorization during installation, so GitHub returns to
its first callback URL. Development therefore uses the separate **Gradiated
[DEV]** app (`gradiated-dev`, callback `http://localhost:3000`) through
`gradiated/dev/env`: `GITHUB_APP_SLUG` and `VITE_GITHUB_APP_SLUG` select it, and
both default to `gradiated`.

`GET …/github-installations` uses the signed-in user's linked GitHub token to
list installations of the app, rejects suspended installations or those
without Contents access, and requires at least one repository the user and app
can both reach. Each item reports `repository_selection` (`all` or `selected`).
The submission records the verified installation as an organization
integration. It is not yet an authorization for background repository access,
which needs installation credentials and lifecycle webhooks.

Before enabling, test Google, GitHub and email sign-in with account linking,
selected repositories, a pending owner approval, suspension, uninstallation and
repository revocation.
