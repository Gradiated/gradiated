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

Start the Vite development server:

```bash
pnpm exec vite --host 0.0.0.0 --port 8675
```

Open `http://localhost:8675`.

## Build

Run the type check and production build:

```bash
pnpm build
```

Preview the production build:

```bash
pnpm exec vite preview --port 8675
```

## Structure

- `src/components/` contains shared site components.
- `src/pages/` contains route-level pages.
- `src/content.tsx` contains article content.
- `public/` contains files served without transformation.
- The existing root CSS files preserve the original visual system.
