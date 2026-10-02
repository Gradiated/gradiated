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

## Task training

Task settings offer manual-only, daily, weekly and custom five-field UTC cron
schedules. Saving an empty schedule disables automatic training. The next-run
preview uses the same Temporal-compatible calendar rules as the backend.

The training gate starts session identification before waiting for feature flags,
so direct task URLs and reloads do not depend on visiting another console page.
Loading training data and trace content uses skeletons.

“View test results” opens the stored held-out answers and judge decisions through
the workspace-authorized version evaluation API. Qwen pricing is a temporary
placeholder; new evaluations label output-only cost estimates, while historical
runs without cost show the input/output rates.

Run the isolated synthetic-data browser regression without a database or login:

```sh
pnpm --filter @gradiated/console exec playwright test --config playwright.task-ui.config.ts
```

It starts a dedicated local Vite server, mocks session/API/flag responses, blocks
external domains, and verifies direct reload, comparison choices, schedule
persistence, held-out results and trace-content skeletons. Browser output stays
under ignored `.agents/runtime/`.

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

Workspace settings expose `default_judge_model` as **Default judge model**. Capture copies it once into a new task’s `judge_model_id`; task settings expose **Judge model** as an independent override. Changing the workspace default affects only subsequently seeded tasks. Existing tasks retain their previous workspace judge during migration. Runs snapshot the task judge at admission.
