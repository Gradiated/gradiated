# Static website and docs SEO

- status: implemented
- date: 2026-08-28

## Decision

Build every public website route as static HTML.

Use one metadata registry for page titles, descriptions, canonical URLs, social
tags, and structured data. Generate a sitemap and robots file from the same route
registry.

Generate a clean Markdown file for each docs page. Use that file for the docs
`Copy page` action and the LLM index files.

## Reason

The website and docs change infrequently. Static HTML gives search engines and
users the complete page in the first response. It also removes the docs page
loading flash.

The model catalog, prices, and account state can change. Keep this data remote.
Load it after the static page content.

## Generated artifacts

- One `index.html` file for each public route.
- One portable `.md` file for each docs route.
- `sitemap.xml`.
- `robots.txt`.
- `llms.txt`.
- `llms-full.txt`.

## Verification

`pnpm --dir website build` runs the static renderer and SEO check. The check
requires unique page metadata, one page heading, canonical URLs, social tags,
structured data, a complete sitemap, and valid docs Markdown.
