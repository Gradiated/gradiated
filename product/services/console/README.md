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

## Storybook previews

Browse Storybook at https://gradiated-storybook-gradiated.vercel.app; PR comments link to
the preview for that branch. Run locally from `product/`:

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
Uploaded LoRA adapters support ranks 1–8. The form rejects higher ranks before
transfer, and server validation enforces the same cap. Serving remains subject to
the deployment’s qualified rank limit.

Training → Model upload covers new and existing tasks, partial/selected files,
uploading, validating, invalid files/config, config replacement without a revision,
transfer and validation errors,
model-catalog retry, and uploaded versions awaiting qualification, including mobile.
Stories drive the actual form and mock only network boundaries.
Add stories under `src/` so reviewers can inspect them in the PR preview.

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

To verify only upload stories without replacing other screenshots, build Storybook
and run from the repository root:

```sh
gradctl browser storybook-screenshots \
  --story-prefix training-model-upload-- --output .agents/runtime/model-upload-stories
```

Storybook is configured for Vercel in `vercel.json`. The Gradiated team’s
`storybook` project is connected to `Gradiated/gradiated` with Root
Directory `product/services/console`, Node.js 22, and access to files outside
the root directory (the pnpm workspace and shared packages). The build compiles
contracts and analytics before Storybook and publishes `storybook-static`.

Vercel's Git integration posts the branch/commit preview link on the PR. These
builds run independently of GitHub Actions; on-demand concurrency allows previews
from different branches to run in parallel. Use Standard build machines and
one active build per branch to avoid paying for superseded previews. The
project's ignored-build script compares against Vercel's previous deployed SHA,
so unrelated changes skip deployment while missing history builds conservatively.
Shared contracts, analytics, workspace lockfile, and toolchain changes rebuild.
No production API credentials or application environment variables are needed:
Storybook uses mocked data and disables production analytics.

CI does not capture or commit PNGs. The local capture command above remains
available for ad hoc checks. The existing AWS-hosted
`https://storybook.gradiated.com` is the legacy main-branch build; it does not
show PR changes and stops receiving updates when the old workflow is removed.
Use the Vercel project's deployment URL for current builds. Moving the custom
domain requires a separate reviewed DNS/hosting change.

Model display names and provider icon paths live in the shared `@gradiated/contracts/model-catalog`. Selectors and model labels use that metadata, falling back to the exact ID for uncataloged models. Provider SVGs are served locally from `public/model-providers/`; exact IDs remain in API snippets and raw request data.
