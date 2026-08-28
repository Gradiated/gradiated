# Developer docs

- status: current product design
- date: 2026-08-28

The developer docs are part of `gradiated.com`. They help a developer connect an OpenAI or Anthropic SDK to Gradiated.

## Information architecture

The docs use these groups:

1. Get started
   - Overview
   - Quickstart
   - Models and pricing
2. Inference
   - OpenAI SDK
   - Anthropic SDK
   - Service tiers
   - Streaming
   - Tool calling
   - Parameters and model support
   - Errors, limits, and retries
3. Integrations
   - OpenCode
   - Codex
   - Claude Code
4. Reference
   - API reference

API use comes before coding-agent integrations. The docs do not use a Guides group.

## Inference base URL

Both SDKs use `https://api.gradiated.com` as the base URL. The SDK adds its
request path. The public gateway routes OpenAI and Anthropic request paths to
the same Rust service.

## Public model catalog

`GET https://api.gradiated.com/api/v1/models` returns all supported non-retired models without authentication. The response includes exact model IDs, availability, token prices, context limits, output limits, and supported parameters.

The Models and pricing page renders this endpoint. Each model row has a copy action for the exact model ID. The desktop view uses a compact table. The mobile view uses stacked cards.

## Account session

The docs and console use the same Better Auth service at `api.gradiated.com`.

The browser sends the API session cookie with `credentials: include`. The docs cannot read the cookie. A user who is logged in to the console is also logged in to the docs.

The Management API accepts only configured origins. Production accepts the console, the apex website, and the `www` website. In local development, the website Vite server proxies Management API requests to port 3001.

The docs support email links, GitHub login, and Google login. A successful login returns the user to the same docs page.

## API keys

The docs select the active organization and default workspace. They show selectors only when the user has more than one choice.

The Quickstart page starts with tabbed language examples. The shared base URL follows the request example. Python and Node examples put the SDK selector in the code block. A compact API key action sits beside the language tabs. The primary OpenAI and Anthropic SDK examples use the same action.

An owner or administrator can create and copy an API key with one action. The Management API returns the secret once. The docs copy the raw secret and keep it in React memory for the current tab.

The docs do not put the secret in local storage, session storage, cookies, URLs, analytics, or persisted caches. A logout, workspace change, organization change, or explicit clear action removes the secret.

All copied examples use `GRADIATED_API_KEY`.

## Management API

The API reference links to the generated Management API reference. The Management API manages workspaces, billing limits, workspace members, and model availability.

The public reference excludes Better Auth routes, health checks, wizard routes, provider webhooks, and their private schemas. These routes remain available to their internal clients.

## Service tiers

The docs use these values:

| Tier      | Price change | Purpose                                                     |
| --------- | -----------: | ----------------------------------------------------------- |
| `fast`    |         +50% | Interactive work where response delay affects the user.     |
| `default` |            — | Normal application traffic.                                 |
| `flex`    |         −30% | Asynchronous work where latency is not the primary concern. |

`flex` uses the normal request and response workflow. It does not create a batch job.

## Writing standard

Use ASD-STE100 Simplified Technical English.

- Use short sentences.
- Use active voice.
- Put the result before background information.
- Use one instruction per sentence.
- Use the same term for the same object.
- Do not use marketing claims.
- Do not describe a control that is clear from its label.
- Keep a paragraph only when it helps a developer choose, configure, verify, or recover.
- Explain why a setting matters when the reason is not clear from the code.
- Do not tell the user to open the console when the docs can perform the action.
- State the exact recovery action for each error.

## Acceptance checks

- A console user can open the docs without another login.
- The Quickstart page shows the shared base URL below the request example.
- The Quickstart page shows Python, Node, and cURL tabs with a compact API key action.
- Python and Node code blocks contain an OpenAI SDK and Anthropic SDK selector.
- The OpenAI SDK page covers installation, Chat Completions, Responses, streaming, and tool calls.
- The Anthropic SDK page covers installation, Messages, streaming, and tool calls.
- Each SDK page puts the compact API key action beside its primary example.
- The public model catalog does not require a session or API key.
- The Models and pricing page shows live catalog prices and copies exact model IDs.
- A guest can log in and return to the same docs page.
- The docs select the default workspace.
- An owner or administrator can create and copy a raw key with one action.
- The secret does not enter browser storage.
- The model catalog loads from the public Management API endpoint.
- An unconfigured browser origin does not receive gateway CORS access.
- The Management API reference does not show authentication, health, wizard, or provider webhook routes.
- Code blocks have syntax highlighting and a copy action.
- Equivalent code examples use one tab group.
- Service-tier examples include Python, Node, and cURL. Python and Node include OpenAI and Anthropic SDK variants.
- Streaming and tool-calling examples include Python and Node with OpenAI and Anthropic SDK variants.
- Next-page cards show separate labels and titles.
- The website builds without TypeScript or MDX errors.
