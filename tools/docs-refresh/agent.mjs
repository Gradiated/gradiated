import path from "node:path";

export const agentResultSchema = {
  type: "object",
  additionalProperties: false,
  required: ["prBody", "update", "threads", "notes"],
  properties: {
    prBody: {
      type: "string",
      description: "Markdown pull request description for the whole branch compared with main.",
    },
    update: {
      type: "string",
      description: "Markdown bullets on what changed in this run only, or 'No changes today.'",
    },
    threads: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["thread", "reply", "resolve"],
        properties: {
          thread: { type: "string", description: "Review thread id from the context." },
          reply: { type: "string" },
          resolve: { type: "boolean" },
        },
      },
    },
    notes: {
      type: "string",
      description: "Notes for the workflow maintainer, or 'None.'",
    },
  },
};

export const auditGroups = [
  { name: "start", pages: ["Overview (`index.mdx`)", "Quickstart", "Models and pricing", "API reference"] },
  { name: "sdks", pages: ["OpenAI SDK", "Anthropic SDK"] },
  { name: "reference", pages: ["SystemOne SDK", "Service tiers", "Errors"] },
  { name: "integrations", pages: ["OpenCode", "Codex", "Claude Code"] },
];

export const auditResultSchema = {
  type: "object",
  additionalProperties: false,
  required: ["findings"],
  properties: {
    findings: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["page", "claim", "problem", "evidence", "fix"],
        properties: {
          page: { type: "string" },
          claim: { type: "string" },
          problem: { type: "string" },
          evidence: { type: "array", items: { type: "string" } },
          fix: { type: "string" },
        },
      },
    },
  },
};

const writeTools = new Set(["Edit", "Write", "MultiEdit", "NotebookEdit"]);

const readOnlyBash = [
  "git log", "git show", "git diff", "git grep", "git blame", "git status", "git ls-files", "git rev-parse",
  "ls", "wc", "rg", "grep", "head", "tail", "sort", "uniq", "jq",
].map((command) => `Bash(${command}:*)`);

const readTools = ["Read", "Grep", "Glob"];

const webTools = ["WebFetch(domain:api.gradiated.com)", "WebFetch(domain:gradiated.com)"];

export const auditTools = [...readTools, ...readOnlyBash, ...webTools];

export const allowedTools = [
  ...readTools, "Edit", "Write", "TodoWrite",
  ...readOnlyBash,
  "Bash(pnpm --dir product --filter gradiated-com build)",
  "Bash(pnpm --dir product --filter gradiated-com test)",
  ...webTools,
];

const baseTools = (rules) => [...new Set(rules.map((rule) => rule.replace(/\(.*$/, "")))];

export const editGuard = (root, isAllowed) => async (input) => {
  if (input.hook_event_name !== "PreToolUse" || !writeTools.has(input.tool_name)) return {};

  const target = input.tool_input?.file_path ?? input.tool_input?.notebook_path ?? "";
  const relative = path.relative(root, path.resolve(root, String(target))).split(path.sep).join("/");
  if (isAllowed(relative)) return {};

  return {
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: `You may edit only the docs paths listed in the instructions, not ${relative}.`,
    },
  };
};

const environmentNotes = `You run unattended in CI. No person will answer questions.

Shell commands run from the repository root. Run each command on its own: no \`cd\`, \`git -C\`,
loops, \`&&\` or \`;\`. A pipe between allowed commands is fine. Allowed commands: ${readOnlyBash
  .map((rule) => rule.slice(5, -3))
  .join(", ")}, and the website build and test commands in the instructions. Any other command is
denied; a denied command does not mean the shell is off. Use the Read, Grep and Glob tools for files.

Do not add attribution lines, such as "Generated with Claude Code", to anything you write.`;

const describe = (block) => {
  const input = block.input ?? {};
  const target =
    input.file_path ?? input.path ?? input.pattern ?? input.command ?? input.url ?? input.description ?? "";
  return `${block.name} ${String(target).replaceAll("\n", " ").slice(0, 160)}`;
};

const runSession = async ({ label, prompt, options }) => {
  const { query } = await import("@anthropic-ai/claude-agent-sdk");
  const tag = label ? `[${label}] ` : "";
  let result = null;

  for await (const message of query({ prompt, options })) {
    const prefix = `${tag}${message.parent_tool_use_id ? "    " : ""}`;

    if (message.type === "assistant") {
      for (const block of message.message?.content ?? []) {
        if (block.type === "tool_use") console.log(`${prefix}→ ${describe(block)}`);
        if (block.type === "text" && block.text.trim()) console.log(`${prefix}${block.text.trim().slice(0, 2000)}`);
      }
    }

    if (message.type === "result") result = message;
  }

  if (!result) throw new Error(`${tag}the session ended without a result`);

  const tokens = (result.usage?.input_tokens ?? 0) + (result.usage?.cache_read_input_tokens ?? 0);
  console.log(
    `${tag}finished: ${result.subtype}, ${result.num_turns} turns, ${Math.round(result.duration_ms / 60000)} min, ` +
      `$${result.total_cost_usd.toFixed(2)} (list price), ${tokens} input and ${result.usage?.output_tokens ?? 0} output tokens`,
  );
  for (const denial of result.permission_denials ?? []) {
    console.log(`${tag}denied: ${denial.tool_name} ${JSON.stringify(denial.tool_input).slice(0, 200)}`);
  }

  if (result.subtype !== "success" || result.is_error || !result.structured_output) {
    throw new Error(`${tag}failed: ${result.subtype} ${(result.errors ?? []).join("; ")}`);
  }

  return result.structured_output;
};

const sessionEnv = (overrides) => ({
  ...process.env,
  GH_TOKEN: "",
  GITHUB_TOKEN: "",
  // Subagents and commands must finish inside the run, or the final answer misses their findings.
  CLAUDE_CODE_DISABLE_BACKGROUND_TASKS: "1",
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
  ...overrides,
});

const pool = async (items, limit, worker) => {
  const results = new Array(items.length);
  let next = 0;
  const lanes = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const index = next++;
      results[index] = await worker(items[index]);
    }
  });
  await Promise.all(lanes);
  return results;
};

// With a Gradiated key, audits run on Gradiated's own API, as a customer would call it.
// Without one, they run on Anthropic with the cheaper model passed in.
export const runAudits = async ({ root, template, model, gradiatedApiKey, concurrency }) => {
  const env = gradiatedApiKey
    ? sessionEnv({
        ANTHROPIC_BASE_URL: "https://api.gradiated.com",
        ANTHROPIC_AUTH_TOKEN: gradiatedApiKey,
        ANTHROPIC_API_KEY: "",
        ANTHROPIC_MODEL: model,
        ANTHROPIC_DEFAULT_HAIKU_MODEL: model,
        ANTHROPIC_DEFAULT_SONNET_MODEL: model,
        ANTHROPIC_DEFAULT_OPUS_MODEL: model,
      })
    : sessionEnv({});

  const audit = async (group) => {
    const prompt = template.replace("{{PAGES}}", group.pages.map((page) => `- ${page}`).join("\n"));
    const options = {
      cwd: root,
      model,
      maxTurns: 120,
      tools: baseTools(auditTools),
      allowedTools: auditTools,
      permissionMode: "dontAsk",
      settingSources: [],
      persistSession: false,
      systemPrompt: { type: "preset", preset: "claude_code", append: environmentNotes },
      outputFormat: { type: "json_schema", schema: auditResultSchema },
      env,
      stderr: (data) => process.stderr.write(data),
    };

    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        const { findings } = await runSession({ label: `audit ${group.name}`, prompt, options });
        return { group, findings };
      } catch (error) {
        console.log(`[audit ${group.name}] attempt ${attempt} failed: ${error.message}`);
        if (attempt === 2) return { group, error: error.message };
      }
    }
  };

  return pool(auditGroups, concurrency, audit);
};

export const runAgent = async ({ root, prompt, isAllowed, model, effort, maxBudgetUsd }) =>
  runSession({
    prompt,
    options: {
      cwd: root,
      model,
      effort,
      maxBudgetUsd,
      maxTurns: 400,
      tools: baseTools(allowedTools),
      allowedTools,
      permissionMode: "dontAsk",
      settingSources: [],
      persistSession: false,
      systemPrompt: { type: "preset", preset: "claude_code", append: environmentNotes },
      outputFormat: { type: "json_schema", schema: agentResultSchema },
      hooks: { PreToolUse: [{ hooks: [editGuard(root, isAllowed)] }] },
      env: sessionEnv({}),
      stderr: (data) => process.stderr.write(data),
    },
  });
