import { CLIENTS, type Setup } from "./clients.js";
import { PROMPTS } from "./prompts.js";
import type { ToolDefinition } from "./tools/definitions.js";

const escape = (text: string) =>
  text.replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ]!,
  );

const toolBehaviour = ({ annotations }: ToolDefinition) =>
  annotations.openWorldHint
    ? "Calls a model"
    : annotations.readOnlyHint
      ? "Reads"
      : annotations.destructiveHint
        ? "Deletes"
        : "Changes";

const toolRow = (tool: ToolDefinition) => {
  const properties = tool.inputSchema.properties;
  const argumentsList = Object.entries(properties)
    .map(([name, schema]) => {
      const required = tool.inputSchema.required.includes(name);
      const description =
        typeof schema.description === "string" ? schema.description : "";

      return `<li><code>${escape(name)}</code>${required ? "" : " <span class=muted>optional</span>"}${description ? ` — ${escape(description)}` : ""}</li>`;
    })
    .join("");

  return `<tr>
  <td><code>${escape(tool.name)}</code><div class=muted>${toolBehaviour(tool)}</div></td>
  <td>${escape(tool.description)}${argumentsList ? `<ul>${argumentsList}</ul>` : ""}</td>
</tr>`;
};

const setup = (label: string, entry: Setup | undefined, mcpUrl: string) =>
  entry
    ? `<p><strong>${label}.</strong> ${escape(entry.where)}</p>${
        entry.snippet
          ? `\n<pre><code>${escape(entry.snippet(mcpUrl))}</code></pre>`
          : ""
      }`
    : "";

export const renderIndexPage = ({
  mcpUrl,
  consoleUrl,
  tools,
}: {
  mcpUrl: string;
  consoleUrl: string;
  tools: readonly ToolDefinition[];
}): string => `<!doctype html>
<html lang=en>
<head>
<meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>Gradiated MCP server</title>
<style>
  :root { color-scheme: light dark; font-family: Inter, system-ui, sans-serif; line-height: 1.55; }
  body { max-width: 52rem; margin: 3rem auto; padding: 0 1.25rem; }
  h1 { font-size: 1.75rem; margin-bottom: .25rem; }
  h2 { margin-top: 2.5rem; font-size: 1.2rem; }
  h3 { margin: 1.5rem 0 .25rem; font-size: 1rem; }
  pre { padding: .85rem 1rem; border-radius: .5rem; overflow-x: auto; background: color-mix(in srgb, currentColor 7%, transparent); }
  code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .9em; }
  table { width: 100%; border-collapse: collapse; }
  td { padding: .65rem .5rem; vertical-align: top; border-top: 1px solid color-mix(in srgb, currentColor 15%, transparent); }
  td:first-child { white-space: nowrap; }
  ul { margin: .35rem 0 0; padding-left: 1.1rem; }
  .muted { opacity: .65; font-size: .85em; }
  a { color: inherit; }
</style>
</head>
<body>
<h1>Gradiated MCP server</h1>
<p>Lets an AI client read and manage one Gradiated workspace: its models, usage, generations, tasks, trained versions and their reports, and call its models.</p>
<pre><code>${escape(mcpUrl)}</code></pre>
<p>The server uses Streamable HTTP. Clients that support MCP authorization sign you in with your Gradiated account, and you choose the workspace the client may use; no key is needed. Other clients send a workspace API key from <a href="${escape(consoleUrl)}/api-keys">the console</a> as <code>Authorization: Bearer</code>. Either way the tools act in one workspace, with the permissions of the member who signed in or created the key.</p>

<h2>Connect a client</h2>
${CLIENTS.map(
  (client) => `<h3>${escape(client.name)}</h3>
${setup("Sign in", client.oauth, mcpUrl)}
${setup("API key", client.apiKey, mcpUrl)}`,
).join("\n")}

<h2>Tools</h2>
<table>
${tools.map(toolRow).join("\n")}
</table>

<h2>Prompts</h2>
<p>Clients that support MCP prompts offer these as commands.</p>
<table>
${PROMPTS.map(
  (prompt) => `<tr>
  <td><code>${escape(prompt.name)}</code></td>
  <td>${escape(prompt.description)}<ul>${prompt.arguments
    .map(
      (argument) =>
        `<li><code>${escape(argument.name)}</code>${argument.required ? "" : " <span class=muted>optional</span>"} — ${escape(argument.description)}</li>`,
    )
    .join("")}</ul></td>
</tr>`,
).join("\n")}
</table>
</body>
</html>
`;
