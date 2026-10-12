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

## Build

Run the type check and production build:

```bash
pnpm build
```

Preview the production build:

```bash
pnpm preview
```

## PR screenshots

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

The Website screenshots workflow runs on relevant PRs and main-branch pushes,
uploads captures, and commits them to same-repository PR branches with a
before/after comment, following the console Storybook workflow. Forks receive
artifacts. Captures are informative and do not enforce a pixel comparison.
Screenshot-only commits from either the website or console skip both capture
workflows, preventing them from triggering one another. In-flight publishers
retry over sibling screenshot commits, preserving both sets, and discard captures
when source files change. Production website build and SEO
checks remain part of the Product tests PR gate.

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
- `src/pages/ArticlePage.tsx` renders every article with the same layout.
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
duplicate routes. Paths use `/library/<slug>/` or `/notes/<slug>/`. An optional
`updatedAt` date must not precede `publishedAt`. `image` is optional and defaults
to the site mark. Use a site-relative image path. Dates use quoted `YYYY-MM-DD`.

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

## Hardware library

Articles declare `category: hardware` to appear under `/library/?show=hardware`.
Omitted categories default to Notes. The same metadata supplies cards, navigation
and reading-page labels. Existing company Methods stay in their authored sequence.

The sand article uses `layout: journey`, preserving its sticky illustrations in
the shared website shell. Drafts are included locally and in Vercel Preview
deployments (`VERCEL_ENV=preview`). Preview drafts are prerendered with noindex
metadata and omitted from the sitemap. Production excludes drafts until their
metadata is set to published. The prose is rendered at
build time from `content/articles/sand/script.md`, with the ordered scene manifest
validated by the renderer. The animation geometry is scoped to its mounted page
and cleaned up on navigation. The imported animation files are a preserved
snapshot; later illustration edits must be coordinated with the writing preview. Its four overview chapters belong to the continuous
journey; future chapter guides will organise separate deeper articles, with one
primary chapter and contextual links from others. Add guide links only when the
destination exists.

The writing workspace retains its working draft. Refresh the portable website
edition with `node scripts/sync-sand-draft.mjs --source /path/to/script.md`.
Visual cue blocks stay in the working draft and are omitted from the portable
website edition. Add `--watch` while editing to update the website preview on saves. Production
builds use the checked-in edition and do not depend on another local folder.

The sand card uses one set of particles for a dune, wind and a logic circuit.
Hover and keyboard focus morph those particles; leaving restores the dune.
Reduced motion keeps a still dune. Offscreen artwork stops its frame loop.
