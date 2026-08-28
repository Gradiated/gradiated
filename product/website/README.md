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

The rewrite keeps React Router routes working after a direct page load.

## Structure

- `src/components/` contains shared site components.
- `src/pages/` contains route-level pages.
- `src/careers.ts` contains the public job descriptions and role metadata.
- `src/docs/` contains the public MDX documentation.
- `src/content.tsx` contains article content.
- `public/` contains files served without transformation.
- The remaining root CSS files preserve legacy page styles.

The docs use MDX compiled by Vite. Add a page to `src/docs/`, register its route
and navigation entry in `src/pages/DocsPage.tsx`, then run `pnpm build`.

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
