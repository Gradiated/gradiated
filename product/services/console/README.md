# Console

## Settings state

TanStack Query owns server state; Zustand owns workspace selection and local
flows. React Hook Form handles forms with explicit submission.

For immediate settings edits, use `useOptimisticPatch` with a stable mutation
key and query prefix. Its scope serializes writes sharing that key. Commit each
server response to the query cache, then invalidate after the final queued save.
Read settings through `useOptimisticValue` with the same mutation key and a pure
patch reducer: pending edits overlay confirmed query data, and failed edits drop
out without undoing newer edits. Keep controls enabled while saving and show the
hook's error. Errors are scoped to the mutation key when the resource changes.
`useWorkspaceSettings` composes this for workspace policies.

Use `OptionSelect` from `src/components/option-select.tsx` for finite option lists. It wraps the shared shadcn/Radix
select with typed values, disabled options, placeholders, and a required
accessible label.

## Brand assets

The console uses the Gradiated logo supplied on 2026-09-11.

- `public/brand/gradiated-full.svg` is the full logo on the sign-in page.
- `src/components/logo.tsx` exports the reusable `Logo` component.
  The workspace menu uses this inline SVG without a background.
  Its fill uses `currentColor` and follows the console text color in each theme.
- `public/brand/gradiated-icon.svg` is the square SVG browser tab icon.
- `public/favicon.ico` contains the same icon at 16, 32, 48, 64, 128, and
  256 pixels.
- `public/apple-touch-icon.png` contains the same icon at 180 pixels.

The SVG files retain the supplied artwork and proportions.
The full logo changes to white in dark mode through the `dark:invert` class.
The website has separate brand assets.

Use `<Logo />` for an accessible logo at the default size of 32 pixels.
Use `className` to set a different size or color.
Use `<Logo aria-hidden="true" />` when nearby text already labels the control.
The component crops the empty margin around the artwork.
The workspace menu centres a 24-pixel logo in a 32-pixel container.
The container keeps the sidebar's direct SVG sizing rule off the logo.

Run `pnpm dev` from the product directory to start the local services.
Open `http://127.0.0.1:3000/login` to inspect the full logo.
The logo files also load directly from their public paths.

Run these checks from the product directory:

```sh
pnpm --filter @gradiated/console check
pnpm --filter @gradiated/console build
```

Validation on 2026-09-11: both checks passed.
The sign-in logo was inspected in the browser at its 28-pixel display height.
The browser icons passed file size and source artwork checks.
The local server and production build contain the new assets.
The authenticated sidebar logo was inspected and measured at 24 pixels.
Dark mode was not inspected in the browser.
