export interface Setup {
  where: string;
  language?: "shell" | "json" | "toml";
  snippet?: (url: string) => string;
}

export interface ClientSetup {
  name: string;
  // Sign in through the browser and choose a workspace; no key to copy.
  oauth?: Setup;
  apiKey?: Setup;
}

const json = (value: unknown) => JSON.stringify(value, null, 2);

export const CLIENTS: readonly ClientSetup[] = [
  {
    name: "Claude (claude.ai and Claude Desktop)",
    oauth: {
      where:
        "In Settings → Connectors, add a custom connector with this URL, then select Connect and sign in.",
      snippet: (url) => url,
    },
  },
  {
    name: "ChatGPT",
    oauth: {
      where:
        "In Settings → Apps, with developer mode on, create an app with this URL and OAuth authentication, then sign in.",
      snippet: (url) => url,
    },
  },
  {
    name: "Claude Code",
    oauth: {
      where: "Add the server, then run /mcp in Claude Code and sign in.",
      language: "shell",
      snippet: (url) => `claude mcp add --transport http gradiated ${url}`,
    },
    apiKey: {
      where: "Or pass a key exported as GRADIATED_API_KEY.",
      language: "shell",
      snippet: (url) =>
        `claude mcp add --transport http gradiated ${url} \\\n  --header "Authorization: Bearer $GRADIATED_API_KEY"`,
    },
  },
  {
    name: "Codex",
    oauth: {
      where: "Add the server and sign in.",
      language: "shell",
      snippet: (url) =>
        `codex mcp add gradiated --url ${url}\ncodex mcp login gradiated`,
    },
    apiKey: {
      where:
        "Or add to ~/.codex/config.toml; Codex reads the key from the environment.",
      language: "toml",
      snippet: (url) =>
        `[mcp_servers.gradiated]\nurl = "${url}"\nbearer_token_env_var = "GRADIATED_API_KEY"`,
    },
  },
  {
    name: "Cursor",
    oauth: {
      where:
        "Add to ~/.cursor/mcp.json or .cursor/mcp.json in a project; Cursor asks you to sign in.",
      language: "json",
      snippet: (url) => json({ mcpServers: { gradiated: { url } } }),
    },
    apiKey: {
      where: "Or send a key from the environment.",
      language: "json",
      snippet: (url) =>
        json({
          mcpServers: {
            gradiated: {
              url,
              headers: { Authorization: "Bearer ${env:GRADIATED_API_KEY}" },
            },
          },
        }),
    },
  },
  {
    name: "VS Code",
    oauth: {
      where: "Add to .vscode/mcp.json; VS Code asks you to sign in.",
      language: "json",
      snippet: (url) => json({ servers: { gradiated: { type: "http", url } } }),
    },
    apiKey: {
      where: "Or have VS Code ask for a key once and store it.",
      language: "json",
      snippet: (url) =>
        json({
          inputs: [
            {
              type: "promptString",
              id: "gradiated-api-key",
              description: "Gradiated API key",
              password: true,
            },
          ],
          servers: {
            gradiated: {
              type: "http",
              url,
              headers: { Authorization: "Bearer ${input:gradiated-api-key}" },
            },
          },
        }),
    },
  },
  {
    name: "Windsurf",
    apiKey: {
      where: "Add to ~/.codeium/windsurf/mcp_config.json.",
      language: "json",
      snippet: (url) =>
        json({
          mcpServers: {
            gradiated: {
              serverUrl: url,
              headers: { Authorization: "Bearer ${env:GRADIATED_API_KEY}" },
            },
          },
        }),
    },
  },
  {
    name: "Gemini CLI",
    apiKey: {
      where: "Add to ~/.gemini/settings.json.",
      language: "json",
      snippet: (url) =>
        json({
          mcpServers: {
            gradiated: {
              httpUrl: url,
              headers: { Authorization: "Bearer $GRADIATED_API_KEY" },
            },
          },
        }),
    },
  },
  {
    name: "Other clients",
    oauth: {
      where:
        "Clients that support MCP authorization discover the sign-in flow from the server's 401 response.",
    },
    apiKey: {
      where:
        "Otherwise send a workspace API key as a bearer token over Streamable HTTP.",
      language: "shell",
      snippet: (url) =>
        `URL: ${url}\nHeader: Authorization: Bearer <workspace API key>`,
    },
  },
];
