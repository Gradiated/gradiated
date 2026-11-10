import assert from "node:assert/strict";
import test from "node:test";
import { isAllowed, parseStatus } from "./refresh.mjs";

test("the agent may change only docs pages and their registration", () => {
  for (const file of [
    "product/website/src/docs/quickstart.mdx",
    "product/website/src/docs/new-page.mdx",
    "product/website/src/pages/DocsPage.tsx",
    "product/website/src/metadata.ts",
    "docs/DEVELOPER_DOCS.md",
  ]) {
    assert.ok(isAllowed(file), file);
  }

  for (const file of [
    "product/website/src/ashby-jobs.generated.ts",
    "product/website/public/ashby-jobs.sha256",
    "product/website/src/docs/nested/page.mdx",
    "product/services/gateway/src/error.rs",
    ".github/workflows/docs-refresh.yml",
    "tools/docs-refresh/prompt.md",
    "docs/ARCHITECTURE.md",
  ]) {
    assert.ok(!isAllowed(file), file);
  }
});

test("status parsing separates untracked files", () => {
  assert.deepEqual(parseStatus(" M product/website/src/docs/errors.mdx\0?? product/website/src/docs/new.mdx\0"), [
    { untracked: false, file: "product/website/src/docs/errors.mdx" },
    { untracked: true, file: "product/website/src/docs/new.mdx" },
  ]);
});

test("the edit guard blocks writes outside the docs paths", async () => {
  const { editGuard } = await import("./agent.mjs");
  const guard = editGuard("/repo", isAllowed);
  const attempt = (tool_name, file_path) => guard({ hook_event_name: "PreToolUse", tool_name, tool_input: { file_path } });

  assert.deepEqual(await attempt("Edit", "/repo/product/website/src/docs/errors.mdx"), {});
  assert.deepEqual(await attempt("Write", "product/website/src/docs/new.mdx"), {});
  assert.deepEqual(await attempt("Read", "/repo/.github/workflows/docs-refresh.yml"), {});

  for (const file of ["/repo/.github/workflows/docs-refresh.yml", "/repo/product/website/src/docs/../../../../tools/x.mjs", "/etc/passwd"]) {
    const result = await attempt("Edit", file);
    assert.equal(result.hookSpecificOutput.permissionDecision, "deny", file);
  }
});

test("audit findings and failures reach the main prompt", async () => {
  const { formatAudits } = await import("./refresh.mjs");
  const text = formatAudits([
    {
      group: { pages: ["OpenAI SDK"] },
      findings: [
        {
          page: "openai-sdk.mdx:121",
          claim: "text = chunk.choices[0].delta.content",
          problem: "The final usage chunk has no choices.",
          evidence: ["product/services/gateway/src/completion.rs:755"],
          fix: "Skip chunks without choices.",
        },
      ],
    },
    { group: { pages: ["Errors"] }, findings: [] },
    { group: { pages: ["Codex"] }, error: "rate limited" },
  ]);

  assert.match(text, /`openai-sdk.mdx:121`: The final usage chunk has no choices./);
  assert.match(text, /### Errors\n\nNo findings./);
  assert.match(text, /### Codex\n\nThe audit failed \(rate limited\). Audit these pages yourself./);
});

test("tokens in git URLs are redacted from errors", async () => {
  const { redact } = await import("./refresh.mjs");
  assert.equal(
    redact("git push https://x-access-token:ghs_abc123@github.com/Gradiated/gradiated.git failed"),
    "git push https://x-access-token:***@github.com/Gradiated/gradiated.git failed",
  );
});
