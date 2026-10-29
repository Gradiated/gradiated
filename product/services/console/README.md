# Console

## Analytics

Core console interactions use `@gradiated/analytics`; completed business actions
come from the API. See the [event catalogue and configuration](../../../docs/PRODUCT_ANALYTICS.md)
for properties, workspace/organization groups and notification setup.

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

## Playground

`/playground` chats with hosted chat models and, when training is enabled,
tasks with a production version. The browser streams `/v1/chat/completions`
from the gateway with a playground credential, so signed-in members never
handle a key. Each member has one hidden key named Playground per workspace,
which the API keys page does not list; every credential request rotates its
secret and resets its one-hour expiry. The query cache reuses it until five
minutes before expiry, renews it after a 401 and clears it on sign-out.

Settings come from the model's catalog entry. The panel shows only the
parameters the model accepts, because the gateway drops the others. Each field
shows the value that is sent: the service tier (flex, default or fast, with its
price change), the reasoning effort, temperature and top P (1 until changed),
and max tokens (the catalog default length). Seed, penalties, stop sequences
and JSON output are under Advanced. The conversation, settings and last model persist per workspace in local
storage, and sign-out clears them. The gateway validates the values that are
sent. Locally, Vite proxies `/v1/` to the
gateway on port 3002. Storybook mocks the stream; `Pages/Playground*` and
`Playground/Chat message` stories cover the page and reply states.

Assistant replies render Markdown, including lists, fenced code, quotes and GFM
tables/task lists. Prompts and reasoning stay literal. Raw HTML is skipped, unsafe
link protocols are filtered, and images display their alt text without fetching
remote resources. Copy reply preserves the original Markdown. Formatting stories
also cover incomplete streaming content and narrow screens.

## Task training

Task settings offer manual-only, daily, weekly and custom five-field UTC cron
schedules. Saving an empty schedule disables automatic training. The next-run
preview uses the same Temporal-compatible calendar rules as the backend.

The training gate starts session identification before waiting for feature flags,
so direct task URLs and reloads do not depend on visiting another console page.
Loading training data and trace content uses skeletons.

The Data table loads older pages automatically at the bottom. Empty hour windows
wait for further scrolling to avoid scanning sparse history on opening the tab.
Opening a trace adds `traceId` to the task URL; shared links and
reloads open Data and find the trace across older pages. Scroll to the bottom
of an open trace to load earlier generations across pages. Failed page loads
keep the loaded rows and offer Retry. Billing balance history also loads automatically
at the bottom, in pages of 100 transactions. Both tables show skeleton rows
while loading the next page.

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
Data, and Settings, plus trace content, test results, and the judge selector. Tab and detail stories
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
PR code. Its bot commits trigger the usual source checks. Screenshot-only commits from
either the console or website skip both capture workflows, preventing them
from triggering one another. PNG-only PRs and main-branch PNG-only pushes
also skip capture. In-flight publishers retry over sibling screenshot commits,
preserving both sets, and discard captures when source files change.

Main-branch builds publish to a private S3 bucket through CloudFront. A successful
Terraform run also republishes Storybook, so the initial hosting provisioning
can finish before publication. The `public-ingress` module owns the bucket,
certificate, distribution, and DNS; `deployment-iam` grants the existing
production deployment role access. GitHub's production environment applies to
hosting deployment.

Model display names and provider icon paths live in the shared `@gradiated/contracts/model-catalog`. Selectors and model labels use that metadata, falling back to the exact ID for uncataloged models. Provider SVGs are served locally from `public/model-providers/`; exact IDs remain in API snippets and raw request data.
