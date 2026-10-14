import { createHash } from "node:crypto";

const styles = `
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; color: #171714; background: #efeee9; font-family: Inter, "SF Pro Text", ui-sans-serif, system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
main { min-height: 100svh; display: flex; align-items: center; justify-content: center; padding: 40px 24px; }
.shell { width: 100%; max-width: 384px; }
.brand { display: block; width: auto; height: 28px; margin-bottom: 24px; }
.card { padding: 36px; border: 1px solid #deddd6; border-radius: 12px; background: #fff; box-shadow: 0 20px 25px -5px #0000000d, 0 8px 10px -6px #0000000d; }
h1 { margin: 0; font-size: 24px; line-height: 32px; font-weight: 700; letter-spacing: -.025em; text-align: center; }
p { margin: 12px 0 0; font-size: 14px; line-height: 22px; color: #686760; }
.intro { text-align: center; }
strong { color: #171714; font-weight: 500; overflow-wrap: anywhere; }
.scope { margin: 24px 0; padding: 16px; border: 1px solid #deddd6; border-radius: 8px; background: #f7f6f2; }
.scope p { margin: 4px 0 0; }
.scope h2 { margin: 0; font-size: 14px; line-height: 20px; font-weight: 500; }
button { width: 100%; min-height: 36px; display: flex; align-items: center; justify-content: center; gap: 10px; padding: 8px 12px; border: 1px solid #deddd6; border-radius: 6px; background: #f7f6f2; color: #171714; line-height: 20px; font-family: inherit; font-size: 14px; font-weight: 500; cursor: pointer; box-shadow: 0 1px 2px #0000000d; }
button:hover { background: #efeee9; }
a { color: #171714; text-underline-offset: 3px; }
button:focus-visible, summary:focus-visible, a:focus-visible { outline: 3px solid #8f8d8380; outline-offset: 2px; }
button svg { width: 16px; height: 16px; flex-shrink: 0; }
.note { text-align: center; font-size: 12px; line-height: 18px; }
details { margin-top: 24px; border-top: 1px solid #deddd6; padding-top: 16px; color: #686760; font-size: 12px; }
summary { cursor: pointer; }
dt { margin-top: 12px; font-weight: 500; }
dd { margin: 4px 0 0; font-family: ui-monospace, monospace; overflow-wrap: anywhere; line-height: 18px; }
::selection { background: #d7f36e; color: #171714; }
@media (max-width: 420px) { .card { padding: 24px; } }
`;

export const pagePolicy = `default-src 'none'; style-src 'sha256-${createHash("sha256").update(styles).digest("base64")}'; img-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'`;

export const escaped = (value: string) =>
  value.replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ]!,
  );

export const authPage = (title: string, content: string, redirect?: string) =>
  `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${escaped(title)} · Gradiated</title>${redirect ? `<meta http-equiv="refresh" content="0;url=${escaped(redirect)}">` : ""}<style>${styles}</style></head><body><main><div class="shell"><img class="brand" src="/brand/gradiated.svg" alt="Gradiated" width="1258" height="288"><section class="card"><h1>${escaped(title)}</h1>${content}</section></div></main></body></html>`;

export const consentPage = (
  client: string,
  clientId: string,
  redirect: string,
  state: string,
) =>
  authPage(
    "Production access",
    `<p class="intro">Connect <strong>${escaped(client)}</strong> to Gradiated production.</p>
<div class="scope"><h2>Diagnostics and GPU registration · 30 days</h2><p>View production alerts, metrics, logs, dashboards and workload status across all tenants, and prepare GPU hosts for Kubernetes. Access renews automatically for up to 30 days; reconnect after that.</p></div>
<form method="post" action="/oauth/consent"><input type="hidden" name="state" value="${escaped(state)}"><button type="submit"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.38a4.61 4.61 0 0 1-2 3.03v2.52h3.24c1.9-1.75 2.98-4.33 2.98-7.38ZM12 22c2.7 0 4.96-.9 6.62-2.39l-3.24-2.52c-.9.6-2.04.97-3.38.97-2.6 0-4.81-1.76-5.6-4.12H3.06v2.6A10 10 0 0 0 12 22ZM6.4 13.94a6 6 0 0 1 0-3.88v-2.6H3.06a10 10 0 0 0 0 9.08l3.34-2.6ZM12 5.94c1.47 0 2.79.51 3.82 1.51l2.87-2.87A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.94 5.46l3.34 2.6C7.19 7.7 9.4 5.94 12 5.94Z"/></svg>Continue with Google</button></form>
<p class="note">Use your gradiated.com Google account.</p>
<details><summary>Connection details</summary><dl><dt>Client ID</dt><dd>${escaped(clientId)}</dd><dt>Return address</dt><dd>${escaped(redirect)}</dd></dl></details>`,
  );
