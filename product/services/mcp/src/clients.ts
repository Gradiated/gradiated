export interface ClientSetup {
  name: string;
  where: string;
  language: "shell" | "json" | "toml";
  snippet: (url: string) => string;
}

const json = (value: unknown) => JSON.stringify(value, null, 2);

export const CLIENTS: readonly ClientSetup[] = [
  {
    name: "Claude Code",
    where: "Run in your project, with the key exported as GRADIATED_API_KEY.",
    language: "shell",
    snippet: (url) =>
      `claude mcp add --transport http gradiated ${url} \\\n  --header "Authorization: Bearer $GRADIATED_API_KEY"`,
  },
  {
    name: "Codex",
    where:
      "Add to ~/.codex/config.toml. Codex reads the key from the environment.",
    language: "toml",
    snippet: (url) =>
      `[mcp_servers.gradiated]\nurl = "${url}"\nbearer_token_env_var = "GRADIATED_API_KEY"`,
  },
  {
    name: "Cursor",
    where: "Add to ~/.cursor/mcp.json or .cursor/mcp.json in a project.",
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
  {
    name: "VS Code",
    where:
      "Add to .vscode/mcp.json. VS Code asks for the key once and stores it.",
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
  {
    name: "Windsurf",
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
  {
    name: "Gemini CLI",
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
  {
    name: "Other clients",
    where:
      "Any client that supports Streamable HTTP. Send the workspace API key as a bearer token.",
    language: "shell",
    snippet: (url) =>
      `URL: ${url}\nHeader: Authorization: Bearer <workspace API key>`,
  },
];
