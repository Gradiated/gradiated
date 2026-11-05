# Gradiated website

This folder contains the Gradiated website. It uses React, TypeScript, Vite, and the existing site CSS.

## Product access

The shared navigation and docs account link open the console at
`VITE_CONSOLE_BASE_URL` (default: `https://console.gradiated.com`, or
`http://localhost:3000` in development). Users can sign in and use inference
without joining a waitlist.

Post-training remains in private beta. The training page opens the waitlist
drawer, which submits to `POST /api/v1/waitlist` and sends a post-training
confirmation email. The console's existing `training` feature flag continues
to limit training access.

## Install

Run this command from this folder:

```bash
pnpm install
```

Use the repository toolchain when mise is available:

```bash
mise exec -- pnpm install
```

## Run locally

Use the pinned Node version, then start the site:

```bash
nvm use
pnpm dev
```

If your shell does not use `nvm`, `pnpm dev` uses the repository's `mise`
configuration to run Vite with Node 22.

Vite uses its default development port. Open `http://localhost:5173`.

### Self-serve onboarding prototype

The homepage’s **Get started** action opens `/get-started/` after the existing
console account flow in production. In local development, both homepage actions
open `/get-started/?preview=signup`: the existing console sign-in and organization
setup pages appear before the wizard. Run both the console (`pnpm --filter
@gradiated/console dev`) and website (`pnpm --filter gradiated-com dev`) servers.
The local demo simulates Google/GitHub sign-in and provides an **Open demo sign-in
link** button for email, without OAuth requests, email delivery or a running API.
The page reads the signed-in user through the existing
generated API client, sends guests to `/login?next=engineer`, and sends unfinished
organizations to `/onboarding?next=engineer`. The existing Google/GitHub/magic-link
sign-in and organization setup return to the wizard. The console's optional
`VITE_WEBSITE_URL` sets the return host (defaults to localhost:5173 in development
and gradiated.com in production). Only the fixed `next=engineer` destination is
accepted; invitation acceptance keeps priority.

Accounts with multiple active organizations choose explicitly before starting a
draft; the selected ID is preserved through console organization setup. Recoverable
staff-session failures return through the console recovery path rather than
ordinary sign-in. `/get-started/` is prerendered with noindex metadata so direct
deployed links and login handoffs resolve without a client-side navigation first.

Name, email and company come from the account, rather than new wizard questions.
Drafts are scoped to the user and organization. NDA signer fields stay editable
because the signer may be someone else. The local preview hands the entered
account details back from the console only after organization setup, checking
the message origin and source frame. `/get-started/?preview=account` resumes a
completed preview account in the same tab; without one, it also starts at account
creation. A new homepage click always starts at account creation. All simulated
account operations are disabled in production and isolated from real session
queries and workspace selection.

The wizard is a clickable preview of getting a human forward deployed engineer
working async: a short introduction, mutual NDA details, Slack/GitHub setup and
the final project review. The introduction explains self-serve setup without a
sales call and a real human working with the customer’s codebase in Slack.
The final review includes an optional context note; there is no project
questionnaire before setup. Setup uses the console account pages’ centered card,
Inter typography, logo, form controls and full-width action layout. The website
serves the same product logo and a local Inter Latin font with its license.
In the demo, **Fill with an example** fills in
synthetic details so the whole flow can be explored without entering personal
information. **Start over** clears the local draft.

The local demo stores progress only in this browser and simulates signing. Account
creation and identity reuse follow the existing product flow. The optional live
NDA integration below creates and verifies PandaDoc documents; it is disabled by
default. Slack Connect invitations are implemented behind their own configuration
switch below. Slack messages, GitHub access, engineer assignment, trace ingestion,
experiments and payments are not implemented. Scope, pricing and experiment
approval remain explicit steps with the engineer.

The NDA field mapping follows the current [PostHog mutual NDA template](https://docs.google.com/document/d/1K-1ErUrHbvNs8ed8CXSQIuA0xJdg55sC/edit)
read from Drive. The customer supplies legal company name, address, signer name,
signer title and signer email. PostHog Inc., James Hawkins (Co-CEO), and the
PostHog address from the template are pre-filled. Signatures and dates must be
captured by the signing service; a typed name here is not a signature. The
local signing demo previews these details only and does not execute an agreement.
Fetch the current template when implementing signing rather than storing a local
contract copy. Its restrictions on AI use of confidential material and software
modification require separate written permission before that work begins.

A selected GitHub repository is required. Slack Connect is the default working
channel; customers can explicitly select email only when their team cannot use
Slack. Repository access and Slack invitations are pending actions in the preview,
with live Slack invitations available after configuration. Private repository access waits for both NDA
signatures.

#### Automatic Slack Connect invitations

The Slack step creates a private `ext-<company>-gradiated` channel, adds the
configured Gradiated engineers, and emails a Slack Connect invitation to the
verified signed-in organization admin. Customers accept it from their workspace;
their admin may also need to approve it. Setup can continue while acceptance is
pending. Email remains the fallback when Slack is unavailable.

The console-only `POST /api/v1/organizations/{organization_id}/slack-invitations`
requires admin membership, a verified account email, and a provider-confirmed
completed NDA belonging to that user and organization. The client cannot supply
another recipient. The generated API client is used by the website. DEV previews
simulate the invitation and create no Slack resources; use
`/get-started/?preview=account&step=slack` to preview this step directly.

One-time setup before enabling real invitations:

1. Create an internal Slack app using `product/services/api/slack-app-manifest.json`
   and install it in Gradiated's workspace. Grant
   bot scopes `groups:write`, `groups:read`, and `conversations.connect:write`.
   Reinstall after changing scopes. Confirm the workspace's Slack Connect plan,
   invitation permissions, and admin approval rules with its owner.
2. Configure server-only `SLACK_BOT_TOKEN`, comma-separated Gradiated engineer
   member IDs in `SLACK_ENGINEER_USER_IDS`, and `SLACK_CONNECT_ENABLED=true`.
   Production values belong in the existing API secret configuration; preserve
   its other entries. No Slack token was configured or invitation sent here.
3. Test with an authorized external recipient: channel creation, engineer
   membership, invitation delivery/acceptance, workspace approval restrictions,
   and retry behavior. Do not enable production until this passes.

Retries reuse a private channel only when its purpose contains the exact
Gradiated organization ID. A name collision or a creation interrupted before
that marker was saved needs operator review; no stranger is invited to an
existing unrelated channel. Mutating Slack calls are never retried automatically
after an uncertain response. An explicit retry can resend an invitation; pending
invite errors remain errors rather than being reported as delivered. The browser
keeps its last acknowledged invite result for display, not as proof of current
membership. Joined status is reported only when Slack confirms existing
membership; there is no webhook-driven acceptance tracking in this change.

See Slack's [channel creation](https://docs.slack.dev/reference/methods/conversations.create/)
and [email invitations](https://docs.slack.dev/reference/methods/conversations.inviteShared/).

#### Embedded PandaDoc NDA signing

The provided template is [Gradiated mutual NDA](https://app.pandadoc.com/a/#/templates/bTmxaYhTaU2tQ28fLhVrHn).
The template ID is configured by default. A sandbox check against the actual
template verified all five customer Merge Fields, the agreement date, customer
signature assignment, silent send, signing-session creation, and browser loading
through the official embedded-signing SDK. No signature was collected; completed
signature verification and the full authenticated onboarding flow still need
end-to-end validation. Credentials were used only from the ignored local `.env`.

The NDA details form opens an on-page review/signing step. In DEV account preview,
**Simulate signing** advances the demo without calling PandaDoc or collecting any
signature unless local sandbox signing is configured. To use the real signing
window inside the preview, add `PANDADOC_SANDBOX_PREVIEW=true` and
`PANDADOC_SANDBOX_SIGNER_EMAIL` to the ignored repository-root `.env`, alongside
the sandbox key and template configuration, then restart the website dev server.
Use a test address in the sandbox key owner's allowed domain. The dev-only Vite
middleware binds to same-origin localhost requests, substitutes that sandbox
email, and checks the document's `[DEV]` marker before silently sending it. It
holds document access in memory and only advances after provider-confirmed
completion. It is absent from production builds; production still uses the
authenticated API. No credentials are exposed through `VITE_` settings.

In the live flow, the backend creates a document, waits for draft
readiness, sends with `silent: true` to suppress signing emails, and creates a
15-minute session for the verified signed-in signer. The browser loads PandaDoc's
official `pandadoc-signing` component. Signing events only trigger a status check;
the API must report `document.completed`, a completed customer recipient, and a
filled customer signature field before the UI advances. Merely signing one side while
another required signer is pending does not unlock the next step.

Backend configuration (never put these credentials in `VITE_` variables):

| Setting | Value |
| --- | --- |
| `PANDADOC_NDA_ENABLED` | `false` by default; enable only after template approval and sandbox verification |
| `PANDADOC_API_KEY` | Server-side PandaDoc API key from the same workspace as the template |
| `PANDADOC_NDA_TEMPLATE_ID` | Defaults to `bTmxaYhTaU2tQ28fLhVrHn`; use a separate test template for sandbox testing |
| `PANDADOC_NDA_TEMPLATE_VERSION` | Required explicit approved revision; bump when legal content changes |
| `PANDADOC_NDA_DATE_FIELD` | Optional exact date-field Merge Field name, e.g. `Agreement.Date`; filled from server time at document creation, not a claim of signing time |

An engineer with infrastructure access can add these settings to the existing
API Secrets Manager JSON `gradiated/prod/product/api` in `us-east-1`, preserving
existing values. No key has been uploaded by this PR. Validate the production
workspace's API entitlement and use separate sandbox credentials for tests.

Required PandaDoc template setup before enabling:

- A role named exactly `Customer`, with a required signature field and automatic
  actual customer signing date. The customer must sign in to Gradiated using the
  same verified email as the signer and have organization admin access. This
  first integration does not grant a signing session for a different person's
  email; that person must authenticate themselves.
- Text-field Merge Field names `Customer.Company`, `Customer.Address`, `Customer.Name`,
  `Customer.Title`, `Customer.Email`, `PostHog.Company`, `PostHog.Signer`, and
  `PostHog.Title` where the API-populated values belong. Match the exact names,
  or update the mapping deliberately. The API supplies both field values and
  variables with these names. The current template uses `Customer_Name` for the
  company, `Customer_Signatory_Name` for the signer, `Customer_Signatory_Title`
  for the title, `Customer_Address`, and `Customer_Email`; configure their Merge
  Field names separately from those field IDs. The PostHog date field already
  uses `Agreement.Date`; set `PANDADOC_NDA_DATE_FIELD=Agreement.Date` to fill it.
- Confirm the intended pre-executed PostHog signature/acceptance arrangement with
  the authorized company signer. Pre-filled names or API date values are not
  signatures. The API does not forge or pre-fill signature fields. If a PostHog
  signing role is still required, PandaDoc stays pending until it is completed;
  an unassigned required role or per-document approval workflow needs attention.
- Verify the full approved NDA text is shown and that the resulting completed
  PDF and PandaDoc signature certificate/audit trail contain the intended parties,
  signatures, dates, and exact agreement. Keep the completed legal record in
  PandaDoc under the company's retention/access policy. Record IDs and ownership
  metadata live in PandaDoc; there is no new local contract database in this PR.

The API binds documents to the organization, creator, signer email and template
revision through provider-side metadata, checks active organization admin access,
and checks the customer signature field. The browser retains only the document
ID for reopening; short-lived signing sessions are not persisted. Reloads require
reverification. Editing signer/company details invalidates the current document
selection and requires a new signature. Provider failures never count as signing.
Document creation is not automatically retried, to avoid silently producing
duplicate contracts after an uncertain network response; check PandaDoc for an
existing draft before creating another copy if the initial response was lost.

Before rollout, test create → silent send → embedded session → all-parties
completion with a sandbox key; customer-only completion while countersigning is
pending; wrong/missing signature fields; unauthorized/cross-organization access;
changed signer details; expired session recovery; missing credentials; provider
outage; reload/resume; and signed-record retention. GitHub's eventual backend
integration must independently verify the NDA document's current status and
ownership before granting code access; frontend state is never that authorization.

References: [embedded signing](https://developers.pandadoc.com/docs/embedded-signing),
[silent send](https://developers.pandadoc.com/reference/send-document),
[field/date prefill](https://developers.pandadoc.com/docs/prefill-fields),
and [document details](https://developers.pandadoc.com/reference/document-details).

#### GitHub App setup for the reviewing engineer

This PR is a local onboarding prototype. No GitHub App private key is required
to run or review it. The repository field and demo account are not proof of a
GitHub installation. There is no installation callback, webhook handler or
server-side repository verification in this PR. Keep the live connection
unavailable until those are implemented and configured; never use a browser
checkbox or local-storage value as authorization.

Reuse the existing **Gradiated** GitHub App (`gradiated`), which currently powers
GitHub login. The owner has confirmed public visibility and configured
read-only Contents permission. Verify these settings during implementation.
The customer installation URL is
`https://github.com/apps/gradiated/installations/new`.

Before enabling the live flow:

1. Check whether an existing private key for this exact app is already available
   in the production secret store. Reuse it if suitable. The OAuth client secret
   used for login is not an app private key. A new PEM has been downloaded by the
   app owner but has not been uploaded; obtain it through an approved secure
   channel only if no suitable existing key is available. Never attach it to the
   PR, paste it in chat, commit it or put it in a `VITE_` environment variable.
2. The API's existing ExternalSecret imports
   `gradiated/prod/product/github-auth` from AWS Secrets Manager in `us-east-1`
   (`infra/environments/prod/us-east-1/kubernetes/workloads/api-secret.yaml`).
   An engineer with access should add the PEM under `GITHUB_APP_PRIVATE_KEY`,
   preserving existing `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` values.
   This is a proposed new backend setting, not one currently consumed by the
   API. Add environment parsing and private-key configuration as part of the
   implementation. Missing configuration must disable repository connection
   without breaking existing GitHub login. Use a separate test app/key for local
   development rather than copying production credentials to a laptop.
3. Preserve the existing Better Auth login callback. Add a backend installation
   setup URL in the app registration and enable Redirect on update. Alternatively,
   if choosing OAuth during installation, implement its callback deliberately:
   GitHub disables the separate setup URL in that mode. Do not toggle this option
   on the current login app without testing the existing sign-in journey.
4. Add authenticated, organization-authorized connection endpoints using the
   generated API contract. Bind a short-lived, single-use state to the signed-in
   Gradiated user and organization. Verify GitHub identity through app user
   authorization and check the installation belongs to this app and is accessible
   to that GitHub user. Do not trust a returned `installation_id`, state alone,
   an email match, or an installation webhook as proof of customer ownership.
5. Authenticate on the backend as the app installation, check it is active with
   the required Contents permission, and list the repositories actually granted
   to it. Save the verified installation/repository IDs against the authorized
   Gradiated organization. Replace the manual repository field with Connect
   GitHub and a verified repository selection. Enable Continue only from the
   server-confirmed state and enforce that condition again on the backend.
6. Configure an HTTPS webhook endpoint and a separate random webhook secret in
   backend secret storage. Verify signatures; handle duplicate and out-of-order
   deliveries. Handle installation creation/deletion/suspension and
   `installation_repositories` changes, and recheck current access before work.
   Treat a request awaiting organization-owner approval as pending, not connected.
7. Configure and verify the embedded NDA integration above before requesting
   installation access to private repositories. The NDA is now the first step;
   the local signing simulation is not a signed agreement. Check NDA completion
   again on the backend before authorizing a live repository connection.
8. Test existing Google/GitHub/email login, a separate customer organization,
   selected repositories, an already-installed app, a user who requires admin
   approval, forged callback IDs/state, cross-customer installation binding,
   revoked repository access, suspension/uninstallation and missing credentials.
   Deploy and validate this backend integration before activating the live CTA.

References: [installation setup URL and spoofing warning](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/about-the-setup-url),
[app installation authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation),
[user installation/repository checks](https://docs.github.com/en/rest/apps/installations),
and [app registration settings](https://docs.github.com/en/apps/maintaining-github-apps/modifying-a-github-app-registration).

## Build

Run the type check and production build:

```bash
pnpm build
```

Preview the production build:

```bash
pnpm preview
```

## Local screenshots

Build the site, then capture its pages and interactions with the existing
repo-local Playwright runtime:

```bash
cd product
mise exec -- pnpm --filter gradiated-com build
cd ..
uv run --locked --project tools/browser playwright install chromium
uv run --locked --project tools/browser python tools/browser/website_screenshots.py
```

The capture set covers the desktop homepage, mobile menu, docs, inference,
training page, and desktop/mobile post-training waitlist drawer. PNGs live in
`screenshots/`. Captures use fixed viewport sizes, date, locale and light theme,
reduced motion, isolated profiles, and an empty model catalog fixture. External
requests are blocked; capture does not log in or submit the waitlist.

Website changes are reviewed through Vercel's PR preview links. CI does not
capture or commit screenshots; the local command above remains available for
ad hoc checks. Website build and SEO checks remain part of the Product tests
PR gate.

## Deploy with Vercel

### Analytics

Production visits on `gradiated.com` and `www.gradiated.com` send PostHog
`$pageview` events to the production project (604827), using its public project
token supplied by `VITE_POSTHOG_KEY` in the Vercel Production environment.
The production Vercel build fails if this variable is missing. Initial visits and client-side route changes carry `source: website`.
Query strings and fragments are removed from event and person URL properties.
Autocapture, exception capture and form tracking are disabled. Session replay
uses PostHog defaults and project settings, with no SDK replay overrides.
Initialization runs only in the browser, outside static prerendering.

Local and Vercel preview builds do not send events by default. Set
`VITE_POSTHOG_KEY` to a development project's public token to test them.
`VITE_POSTHOG_HOST` overrides the default US ingestion host. Never put a
PostHog personal API key in a `VITE_` variable.

### Hosting

Create a Vercel project for this repository.

Set the Vercel Root Directory to `product/website`.

Vercel reads `vercel.json`, runs `pnpm build`, and serves `dist`.

The build writes one static HTML file for each public route. Vercel serves these
files directly. `vercel.json` redirects old docs routes to their current routes.

## Structure

- `src/components/` contains shared site components.
- `src/pages/` contains route-level pages.
- `src/metadata.ts` defines titles, descriptions, canonical URLs, social tags,
  and structured data for all public routes.
- `src/careers.ts` contains the public job descriptions and role metadata.
- `src/docs/` contains the public MDX documentation.
- `content/articles/*.mdx` is the source of truth for articles and their metadata.
- `src/articles.ts` discovers articles and filters drafts by build mode.
- `src/pages/ReadingPages.tsx` renders articles in the shared site shell,
  including the guide's journey layout.
- `src/pages/HandbookPage.tsx` renders the Handbook index and individual pages.
- `src/content.tsx` contains legacy shared content, including the Thesis body.
- `public/` contains files served without transformation.
- `public/.well-known/security.txt` is the RFC 9116 security contact. The build
  fails once its `Expires` date passes; renew it at least yearly.
- The remaining root CSS files preserve legacy page styles.

The docs use MDX compiled by Vite. Add a page to `src/docs/`, register its route
and navigation entry in `src/pages/DocsPage.tsx`, then run `pnpm build`.

## Article frontmatter and publication

Add an MDX file to `content/articles/`. Start it with YAML frontmatter:

```yaml
---
title: "Article title"
description: "A unique summary for readers and search engines."
path: /library/article-slug/
status: draft
publishedAt: "2026-09-02"
image: /brand/png/gradiated-mark-dark-1024.png
---
```

Set `status: published` to include the article in production. Drafts are visible
in development, but have no production route, library entry, or sitemap entry.
Drafts are not a private storage mechanism: do not put secrets in article files.
No article-specific routes or metadata branches are needed.

The shared page renders the title and publication date. Start the MDX body with
prose, not another H1. MDX can import interactive components. Existing footnotes
and shared code blocks work in every article. The Thesis MDX file currently uses
its existing React body to preserve the current copy.

The registry validates required fields, calendar dates, paths, status, and
duplicate routes. Paths use `/library/<slug>/`, `/notes/<slug>/`, or `/sand-to-thought/` and its subpages. Articles default to `collection: library`; the semiconductor guide uses `collection: sand-to-thought` and is excluded from Library cards and navigation lists. An optional
`updatedAt` date must not precede `publishedAt`. `image` is optional and defaults
to the site mark. Use a site-relative image path. Dates use quoted `YYYY-MM-DD`.

The description is optional. Omit it to hide the article's introductory summary;
search and social metadata then use the article title as a fallback.

Frontmatter feeds the library, visible heading/date, canonical metadata, social
tags, Article JSON-LD, static rendering, and sitemap. The browser updates the same
metadata on navigation. `pnpm build` checks the generated SEO output for every
article, including publication dates and structured-data consistency.

From `product/`, run the registry tests with:

```bash
mise exec -- pnpm exec tsx --test website/scripts/article-metadata.test.ts
```

## Article footnotes

Use standard footnote syntax in an MDX article:

```md
A measured claim.[^method]

[^method]: Describe the method and scope here.
```

The MDX pipeline adds linked references and return links. Shared article styles
are in `article.css`.

The production build renders every public page to static HTML. It also generates
portable Markdown for each docs page, `sitemap.xml`, `robots.txt`, `llms.txt`,
and `llms-full.txt`. The docs `Copy page` button copies the generated Markdown.
Live account state and the model catalog still load from the Management API.

The build runs `scripts/check-seo.mjs`. This check requires unique metadata, one
page heading, canonical URLs, social tags, structured data, and a complete
sitemap.

The careers index is at `/careers/`. Each job in `src/careers.ts` generates a
route under `/careers/<slug>/`. The shared page structure, compensation text,
work schedule, interview process, and application link are in
`src/pages/JobPage.tsx`. Applications use `team@gradiated.com` and do not need
an external service.

The home page service-tier section keeps tier names, discount values, and
descriptions in `src/components/ServiceTierSection.tsx`. Update that table when
the service-tier pricing changes.

The home page, shared header, shared footer, and theme control use Tailwind
utilities. Keep new layout rules in their components unless a shared design
token belongs in `src/tailwind.css`.

The model catalog in `src/components/docs/DocsModelCatalog.tsx` owns its table
styles. The prose table rules in `src/styles/pages.css` exclude
`data-model-table` to preserve cell padding and alignment. The catalog uses
cards when its container is less than 700px wide.

Docs tab rules stop at the tab labels. The language tab header has no full-width
rule. SDK variant rules also use the width of their labels. These styles are
in `src/styles/pages.css`.
The outer tab panel uses the same top margin for SDK variants and plain code
blocks.

The training page shows one evaluation named `Support resolution` in
`src/components/design/Benchmark.tsx`. The user supplied source scores of 55% for Base GLM-5.3-Flash, 75% for
Post-trained GLM-5.3-Flash — SFT + GRPO, and 90% for Sol. The user requested
display values of 54%, 76%, and 88%, respectively. These are user-selected
display values; they are not independently verified measurements. Costs assume 8,000 uncached input tokens and 1,000 output tokens per task.
Base GLM uses $0.15/$0.50 per million tokens from
[OpenRouter](https://openrouter.ai/z-ai/glm-5.3-flash).
Sol uses the current $4/$20 promotional rate from
[OpenAI](https://developers.openai.com/api/docs/models/gpt-5.6-sol).
Rates were checked on 13 September 2026. Derived task costs are $0.0017 for
base and $0.052 for Sol. Post-trained cost is an explicit estimate of 20%
above base ($0.00204), pending measured data. The horizontal axis uses a
logarithmic USD scale from $0.0005 to $0.15. The
score scale is 0–100%. The previous example scores and judge metadata are removed.

The chart displays cost per 100 tasks: $0.17 base, $0.204 post-trained, and
$5.20 Sol. The log scale remains. The visible assumption note and estimate
label are removed at the user’s request; the calculation assumptions above
remain the source of truth.

At the user’s request, the displayed labels now say “Cost per task” and
“/ task” while retaining the 100× display scaling. These displayed costs do
not represent the original 8k-input/1k-output task calculation.

The evaluation subtitle is “Post-training GLM 5.3 Flash for a support resolution
agent improved the outcomes substantially, at 1/25th of the cost of Sol.” The user described 20 custom retail scenarios based on
τ²-bench. Training used 50 synthetic retail conversations from
`inclusionAI/AReaL-tau2-data` for SFT, then GRPO in an environment inferred from
the traces. Each evaluation scenario contained 12 requests across multiple
orders. A pass required the entire final backend state to match the requested
outcome. These results are not production customer data or official τ²-bench
leaderboard results. They do not measure policy compliance or communication
quality.

The training traffic animation applies an illustrative 80% cost reduction to
the whole line, spend meter, and hover values when Gradiated is enabled. The
transition settles within about one second. Token traffic is unchanged.
Reduced-motion mode updates the cost immediately without moving the traffic.

The inference page reuses the `site` variant of `DocsModelCatalog` for live
model prices and copy-ID actions, with the website's font, color, and radius
tokens. Model requests link to `team@gradiated.com`.

Console links use `CONSOLE_BASE_URL` from `src/urls.ts`. Vite development uses
`http://localhost:3000`; production builds use `https://console.gradiated.com`.
Set `VITE_CONSOLE_BASE_URL` at build time to override this destination.

## Sand to Thought

The semiconductor guide lives at `/sand-to-thought/`, with its own top navigation
link immediately after Library. The old `/library/how-to-get-an-answer-out-of-sand/`
address redirects to it, preserving section fragments. Library contains Notes and
Handbook. Article subjects (`category`) remain separate from their collection.

The guide opens with the animated dune-to-circuit artwork and continues directly
into the illustrated article. Its contents list is generated from the script’s
existing headings, using the docs’ sidebar styling and mobile contents control.
Chapter links jump within this page and the active chapter follows the reader.
Future chapter guides and deeper articles can live under this collection without
turning the opening journey into a catalogue.

The sand article uses `layout: journey`, preserving its sticky illustrations in
the shared website shell. Drafts are included locally and in Vercel Preview
deployments (`VERCEL_ENV=preview`). Preview drafts are prerendered with noindex
metadata and omitted from the sitemap. Production excludes drafts until their
metadata is set to published. Sand to Thought is published through all five
current chapters. `content/articles/sand/publication.json` records
`publishedThrough: "computer"` and the public closing paragraph. Development and
Vercel previews render the complete script. Moving the boundary to a later
chapter's final scene publishes that chapter on the next production deployment.
The boundary must fall at the end of the script or immediately before the next
chapter heading. Production omits later prose, contents links and diagram nodes.
The complete script is still validated on every build. The prose is rendered at
build time from `content/articles/sand/script.md`, with the ordered scene manifest
validated by the renderer. The animation geometry is scoped to its mounted page
and cleaned up on navigation. The imported animation files are a preserved
snapshot; later illustration edits must be coordinated with the writing preview. Its five overview chapters belong to the continuous
journey; future chapter guides will organise separate deeper articles, with one
primary chapter and contextual links from others. Add guide links only when the
destination exists.

The checked-in `content/articles/sand/script.md` is the canonical prose source.
The local authoring workspace links its `script.md` to this file. Saving updates
both local views, while commit and push update the branch preview. The portable
authoring edition has its own build tool and animation copy. Private visual cues
remain in the authoring workspace and are not published. Production builds use
only checked-in website files and do not depend on another local folder.

Timing follows the adder and heat discussion, before the memory chapter. Memory
builds from a latch and register into addressed arrays with manual read and write
controls. Chapter 5 develops MAR/MDR, fast storage registers, multiplexers, an ALU
and control. Its LC-3 example adds R3 to R0, then follows stored instructions
through PC, instruction fetching, IR and execution. An illustrative controller
shows how gates and stored state coordinate a transfer and wait for memory.
Detailed treatments remain future articles.

`runtime/computer-scenes.js` builds the new diagrams using the existing SVG/GSAP
helpers. `runtime/scroll-progress.js` keeps each later illustration steady while
its text crosses the reading line, with transitions in the gaps. It preserves the
opening artwork's centre-to-centre choreography. Check this mapping with
`node --test scripts/sand-scroll-progress.test.mjs`. The writing preview uses the
same geometry and mapping; coordinate animation snapshots as well as the prose
when editing either copy.

The sand card uses one set of particles for a dune, wind and a logic circuit.
Hover and keyboard focus morph those particles; leaving restores the dune.
Reduced motion keeps a still dune. Offscreen artwork stops its frame loop.

Check the publication boundary with `node --test scripts/sand-publication.test.mjs`.

## Article citations

All blog posts should use citations for factual claims that need supporting sources.
Add and verify them as posts are written or revised.

Use `[@source-key]` after the sentence it supports, after punctuation. For several
sources together, use `[@source-one; @source-two]`. Reusing a key reuses its number.
Numbers follow first appearance. Citations link to a References section at the end
of the article, with return links for each occurrence. Source links open in a new
tab, while citation numbers and return links navigate within the article. This is
a bibliography, separate from explanatory footnotes.

Keep sources in a companion JSON file beside the prose. For `example.mdx`, use
`example.references.json`. For either journey's `script.md`, use
`script.references.json` in the same directory. For example

```json
{
  "example-paper": {
    "authors": ["Surname, A. B.", "Surname, C. D."],
    "title": "Article title in sentence case",
    "publication": "Nature Phys.",
    "volume": "22",
    "pages": "1–5",
    "year": 2026,
    "url": "https://doi.org/10.example/paper"
  }
}
```

The shared formatter uses Nature-style author names, article titles, italic
publication names, bold volumes, pages and years. Supply names as shown above and
use an organisation as the author for an unsigned institutional source. Authors,
title and an absolute HTTP(S) URL are required. Publication, volume, pages, year,
publisher and accessed date are optional, so books, documentation, videos and web
sources can also be recorded. Metadata is rendered as plain text, not HTML or
Markdown.

Link to the most specific verified supporting passage available. For web pages,
prefer a stable section anchor and, where supported, a text fragment such as
`#section:~:text=encoded%20opening,encoded%20ending` to scroll to and highlight the
relevant text. Encode each selector's text separately and check it against the
source. Use short, distinctive ranges, not a whole page. Preserve a section
anchor as a fallback where one exists. For PDFs, use `#page=N` with the one-based
PDF page number, which may differ from the printed page number. Verify the page
before linking it. A source supporting several claims may need more than one
highlighted passage. Keep the DOI URL when there is no more precise, reliable
publisher or author-hosted destination. Highlighting depends on the reader's
browser and the source site, so the underlying source must remain usable without
it. Check targeted links in the in-app browser and revisit them when revising
the associated claims.

This syntax works in standard article MDX and both scrolling journeys. Code and
existing link labels stay literal. Sources not cited in the rendered article are
omitted, including sources used only beyond a journey's publication boundary.
Articles without citations produce no bibliography. Missing sources and invalid
cited source details fail the build. Vite watches companion files for local edits.

Prefer primary research, official technical documentation and original teaching
materials. Verify that each source supports the specific statement being cited.
Adding this infrastructure does not supply or validate sources for older prose.
Keep citation research and editorial changes scoped to the passages being revised.
