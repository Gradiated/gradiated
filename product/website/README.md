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
- `src/docs/` contains the public MDX documentation.
- `src/content.tsx` contains article content.
- `public/` contains files served without transformation.
- The existing root CSS files preserve the original visual system.

The docs use MDX compiled by Vite. Add a page to `src/docs/`, register its route
and navigation entry in `src/pages/DocsPage.tsx`, then run `pnpm build`.
