# Audit Gradiated docs pages against the code

You check part of the public developer docs at `gradiated.com/docs` against
the code in this repository. You do not edit files. Another agent reads your
findings, checks each one, and edits the docs.

Your pages:

{{PAGES}}

The pages are MDX files in `product/website/src/docs/`.

## What to check

Check every factual claim on your pages: each path, field, parameter, value,
header, status code, error code, limit, default, command, package name, file
path, label the developer sees, and described behavior.

For each code example, trace what the API sends back, including every
streaming chunk, the final usage chunk, tool call deltas and error bodies.
Check that the example runs without an error once a developer sets
`GRADIATED_API_KEY` and replaces `YOUR_MODEL`.

Commands, file paths and labels on the integration pages (OpenCode, Codex,
Claude Code) must match the wizard source in `product/services/wizard/`
exactly.

## Where the facts live

Code and tests are the proof. A docs page, a plan in `docs/`, a commit message
or a code comment is not.

| Topic                                     | Source of truth                                                                                 |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Inference routes, auth, headers           | `product/services/gateway/src/` (`http.rs`, `request.rs`, `auth.rs`, `protocol.rs`) and tests   |
| Streaming and response shapes             | `product/services/gateway/src/completion.rs`, `completion/`, `runtime/`                         |
| Error codes, HTTP statuses                | `product/services/gateway/src/error.rs`, `admission.rs`                                         |
| Service tiers and price changes           | `product/packages/contracts/src/service-tiers.ts`, `product/services/gateway/src/service_tier.rs` |
| Model catalog fields and parameters       | `product/packages/contracts/src/model-catalog.ts`, `product/services/api/src/routes/models.ts`  |
| SystemOne requests                        | `product/packages/contracts/src/systemone.ts`, `product/services/gateway/src/systemone.rs`      |
| Coding agent setup                        | `product/services/wizard/src/` and its tests                                                    |

You may fetch `https://api.gradiated.com/api/v1/models` to see the live
catalog.

Shell commands run from the repository root, one at a time: no `cd`,
`git -C`, loops, `&&` or `;`. Use the Read, Grep and Glob tools for files.

## What to report

Report only claims that the code contradicts, and examples that would fail.
Do not report style, wording you would prefer, or claims you could not check.
Do not report internal details that the docs leave out on purpose, such as
service names, hosts, GPUs or upstream providers.

For each finding, give:

- `page`: the docs file and line, such as `errors.mdx:21`.
- `claim`: the exact text on the page.
- `problem`: what the code does instead, in one or two plain sentences.
- `evidence`: one to three `path:line` references.
- `fix`: the smallest change that makes the page correct.

Return an empty list if every claim is correct.
