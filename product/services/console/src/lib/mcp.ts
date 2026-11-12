import type { components } from "@/api/schema";

export type McpTool = components["schemas"]["McpTool"];

export const GRADIATED_MCP_SERVER_ID = "gradiated";

export const GRADIATED_MCP_URL =
  import.meta.env.VITE_MCP_URL ?? "https://mcp.gradiated.com/mcp";

// How a server takes its credential. A value is sent as the named header.
export type McpCredential =
  | { kind: "none" }
  | {
      kind: "header";
      header: string;
      prefix: string;
      required: boolean;
      label: string;
      help: string;
    };

export interface McpCatalogEntry {
  id: string;
  name: string;
  description: string;
  url: string;
  credential: McpCredential;
}

export interface InstalledMcpServer {
  id: string;
  name: string;
  url: string;
  headers: Record<string, string>;
  enabled: boolean;
}

const bearer = (
  label: string,
  help: string,
  required = true,
): McpCredential => ({
  kind: "header",
  header: "Authorization",
  prefix: "Bearer ",
  required,
  label,
  help,
});

// Remote servers that accept Streamable HTTP without an OAuth sign-in.
export const MCP_CATALOG: readonly McpCatalogEntry[] = [
  {
    id: "deepwiki",
    name: "DeepWiki",
    description: "Documentation and Q&A for public GitHub repositories.",
    url: "https://mcp.deepwiki.com/mcp",
    credential: { kind: "none" },
  },
  {
    id: "context7",
    name: "Context7",
    description: "Current documentation and code examples for libraries.",
    url: "https://mcp.context7.com/mcp",
    credential: {
      kind: "header",
      header: "CONTEXT7_API_KEY",
      prefix: "",
      required: false,
      label: "API key",
      help: "Optional. A key from context7.com raises the rate limit.",
    },
  },
  {
    id: "microsoft-learn",
    name: "Microsoft Learn",
    description: "Search and read Microsoft and Azure documentation.",
    url: "https://learn.microsoft.com/api/mcp",
    credential: { kind: "none" },
  },
  {
    id: "aws-knowledge",
    name: "AWS Knowledge",
    description: "AWS documentation, guidance and regional availability.",
    url: "https://knowledge-mcp.global.api.aws",
    credential: { kind: "none" },
  },
  {
    id: "cloudflare-docs",
    name: "Cloudflare Docs",
    description: "Search Cloudflare's developer documentation.",
    url: "https://docs.mcp.cloudflare.com/mcp",
    credential: { kind: "none" },
  },
  {
    id: "hugging-face",
    name: "Hugging Face",
    description: "Search models, datasets, Spaces and papers on the Hub.",
    url: "https://huggingface.co/mcp",
    credential: bearer(
      "Access token",
      "Optional. A Hugging Face token gives access to your private resources.",
      false,
    ),
  },
  {
    id: "github",
    name: "GitHub",
    description: "Repositories, issues, pull requests and code search.",
    url: "https://api.githubcopilot.com/mcp/",
    credential: bearer(
      "Personal access token",
      "A fine-grained GitHub token. The model acts with its permissions.",
    ),
  },
  {
    id: "stripe",
    name: "Stripe",
    description: "Customers, payments, invoices and Stripe documentation.",
    url: "https://mcp.stripe.com",
    credential: bearer(
      "Restricted API key",
      "Use a restricted, test-mode key. The model acts with its permissions.",
    ),
  },
];

export const GRADIATED_SERVER: InstalledMcpServer = {
  id: GRADIATED_MCP_SERVER_ID,
  name: "Gradiated",
  url: GRADIATED_MCP_URL,
  headers: {},
  enabled: true,
};

export const DEFAULT_MCP_SERVERS: readonly InstalledMcpServer[] = [
  GRADIATED_SERVER,
];

// The Gradiated entry always points at this console's MCP server and cannot be removed.
export const installedServers = (
  stored: readonly InstalledMcpServer[] | undefined,
): InstalledMcpServer[] => {
  const servers = stored ?? DEFAULT_MCP_SERVERS;
  const gradiated = servers.find(({ id }) => id === GRADIATED_MCP_SERVER_ID);

  return [
    { ...GRADIATED_SERVER, enabled: gradiated?.enabled ?? true },
    ...servers.filter(({ id }) => id !== GRADIATED_MCP_SERVER_ID),
  ];
};

export const credentialHeaders = (
  credential: McpCredential,
  value: string,
): Record<string, string> =>
  credential.kind === "header" && value.trim()
    ? { [credential.header]: `${credential.prefix}${value.trim()}` }
    : {};

export interface PlaygroundTool {
  // The function name the model sees: server and tool, unique in one request.
  name: string;
  server: InstalledMcpServer;
  tool: McpTool;
}

const MAX_FUNCTION_NAME = 64;

const slug = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "") || "server";

export const playgroundTools = (
  servers: readonly { server: InstalledMcpServer; tools: readonly McpTool[] }[],
): PlaygroundTool[] => {
  const used = new Set<string>();

  return servers.flatMap(({ server, tools }) =>
    tools.map((tool) => {
      const base =
        `${slug(server.name)}__${tool.name.replace(/[^A-Za-z0-9_-]/g, "_")}`.slice(
          0,
          MAX_FUNCTION_NAME,
        );
      let name = base;
      for (let index = 2; used.has(name); index++)
        name = `${base.slice(0, MAX_FUNCTION_NAME - String(index).length - 1)}_${index}`;
      used.add(name);

      return { name, server, tool };
    }),
  );
};

export const functionTools = (tools: readonly PlaygroundTool[]) =>
  tools.map(({ name, tool }) => ({
    type: "function",
    function: {
      name,
      description: tool.description ?? tool.title ?? tool.name,
      parameters: tool.input_schema,
    },
  }));
