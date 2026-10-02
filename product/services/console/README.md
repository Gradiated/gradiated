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

## Storybook and PR screenshots

Browse the main-branch build at https://storybook.gradiated.com. Run locally from
`product/`:

```sh
pnpm install --frozen-lockfile
pnpm exec turbo run build --filter=@gradiated/contracts
pnpm --filter @gradiated/console storybook
```

Stories render the real console routes with a fresh query client and memory
history. MSW serves synthetic fixtures; authentication and unimplemented API
mutations cannot reach the real backend. Training is enabled and analytics are
disabled only for Storybook. Page stories cover sign-in, API keys, models,
usage, logs, billing, training, and every task-detail tab: Model, Training runs,
Data, and Settings, plus trace content and test results. Tab and detail stories
select the actual tab and open the panel through a play function.
Add stories under `src/`; screenshot capture discovers every page story automatically.

Capture PNGs locally from the repository root with the pinned browser runtime:

```sh
uv run --locked --project tools/browser playwright install chromium
cd product
pnpm --filter @gradiated/console screenshots
```

Capture uses Chromium at 1440×1000, UTC, en-US, light theme, reduced motion, and
a fixed date. Each story has an isolated browser context and external requests
are blocked. Screenshots replace the committed `screenshots/*.png` only after
all stories render successfully. GitHub's image diff shows changed pages in PRs.

The Storybook workflow builds and captures relevant PRs, uploads artifacts, then
commits changed PNGs to same-repository PR branches and adds a before/after
comment. Forks receive downloadable artifacts. Capture and publication jobs are
informative and never block merging; there is no pixel comparison or approval
threshold. A separate publication job handles the write key without executing
PR code. Its bot commits trigger the usual source checks and skip another Storybook
capture, avoiding a screenshot update loop. PNG-only PRs and main-branch
PNG-only pushes also skip capture.

Main-branch builds publish to a private S3 bucket through CloudFront. A successful
Terraform run also republishes Storybook, so the initial hosting provisioning
can finish before publication. The `public-ingress` module owns the bucket,
certificate, distribution, and DNS; `deployment-iam` grants the existing
production deployment role access. GitHub's production environment applies to
hosting deployment.
