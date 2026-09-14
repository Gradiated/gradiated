# Gradiated website

This folder contains the Gradiated website. It uses React, TypeScript, Vite, and the existing site CSS.

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

## Deploy with Vercel

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

The Carat publication date is 2 September 2026, as requested. Build verification
must include the public article HTML, not only the development preview.

Publication checks passed for Carat and Thesis: shared headings/dates, canonical
URLs, Article JSON-LD, library entries, and production interactions. A temporary
draft fixture loaded in development with `noindex` and had no production route,
static HTML, library entry, or sitemap entry. The fixture was then removed.
The registry and diagram tests pass. The existing bundle-size warning remains.

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

The September 2026 layout fix passed DevEx checks, the production build, and
browser checks at 390, 768, 1024, and 1440px with synthetic catalog data.
Desktop and mobile screenshots were reviewed. Live API data was not checked.

Docs tab rules stop at the tab labels. The language tab header has no full-width
rule. SDK variant rules also use the width of their labels. These styles are
in `src/styles/pages.css`. The production build and browser checks for tab
width and tab switching passed.
The outer tab panel uses the same top margin for SDK variants and plain code
blocks. Browser checks confirmed equal gaps for Python, Node, and cURL at
390px and 1440px.

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

The evaluation card uses a larger title, a compact plot, and one legend row
per model. The title has no score summary. Desktop and mobile layouts were
reviewed. The website build passed.

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

The cost line maps zero cost to 94% of the canvas height, so the reduced
cost sits near the bottom of the chart.

The traffic bars fade inside the canvas. The cost line stays fully opaque
and uses a 3px stroke so it remains visible near the chart floor.

The inference page reuses `DocsModelCatalog` for live model prices and copy-ID
actions. It replaces the placeholder model cards. Model requests link to
`team@gradiated.com`. The video reel and its captions are removed from the
inference page. The catalog uses the full section width.

The inference catalog uses the `site` variant. It keeps the bordered docs
table layout, with website font, color, and radius tokens. The docs variant
keeps its existing styling.

Console links use `CONSOLE_BASE_URL` from `src/urls.ts`. Vite development uses
`http://localhost:3000`; production builds use `https://console.gradiated.com`.
Set `VITE_CONSOLE_BASE_URL` at build time to override this destination.

The navigation’s Latest writing thumbnails use the library artwork presets
and the shared `WaferArtwork` animation. Hover or keyboard focus on an article
row starts the same animation as a library card. Reduced motion is respected.

Artwork hover transitions retain one scatter path and the current progress.
A repeated hover fades and disperses from the current frame, then assembles
the artwork again. It does not reset chip positions or restart at full opacity.

Reading pages hide the unused opening lattice from the first paint. Its old
animation was removed, but its static lines otherwise remain until the four-second
entrance timer removes them. This prevents temporary lines on mobile articles.
