// Daily developer docs refresh. The workflow runs three steps:
//
//   prepare  find the open docs PR, check out its branch (or main), gather context
//   agent    run the Claude Agent SDK with prompt.md and the context; it edits docs only
//   publish  keep allowed paths, build, commit, push, and open or update the PR
//
// The agent gets no GitHub token. Only publish pushes, with the docs app token.
// Run a copy of this directory from outside the checkout: prepare switches branches.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const toolDir = path.dirname(fileURLToPath(import.meta.url));
const root = spawnSync("git", ["rev-parse", "--show-toplevel"], { encoding: "utf8" }).stdout.trim() || process.cwd();
const runtime = path.join(root, ".agents/runtime/docs-refresh");
const outDir = path.join(runtime, "out");
const statePath = path.join(runtime, "state.json");

export const branch = process.env.DOCS_REFRESH_BRANCH ?? "automation/docs-refresh";
export const title = "Update developer docs";
const repo = process.env.GITHUB_REPOSITORY ?? "Gradiated/gradiated";
const botIdentity = ["github-actions[bot]", "41898382+github-actions[bot]@users.noreply.github.com"];
// Set per command: git config would also change the identity of every worktree of a local clone.
const botEnv = {
  GIT_AUTHOR_NAME: botIdentity[0],
  GIT_AUTHOR_EMAIL: botIdentity[1],
  GIT_COMMITTER_NAME: botIdentity[0],
  GIT_COMMITTER_EMAIL: botIdentity[1],
};

export const allowedPaths = [
  /^product\/website\/src\/docs\/[^/]+\.mdx$/,
  /^product\/website\/src\/pages\/DocsPage\.tsx$/,
  /^product\/website\/src\/metadata\.ts$/,
  /^docs\/DEVELOPER_DOCS\.md$/,
];

export const isAllowed = (file) => allowedPaths.some((pattern) => pattern.test(file));

export const redact = (text) => text.replace(/x-access-token:[^@\s]+@/g, "x-access-token:***@");

const run = (command, args, options = {}) => {
  const result = spawnSync(command, args, {
    cwd: root,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
    stdio: options.inherit ? "inherit" : ["pipe", "pipe", "pipe"],
    input: options.input,
    env: { ...process.env, ...options.env },
  });

  if (result.status !== 0 && !options.allowFailure) {
    const message = `${command} ${args.slice(0, 4).join(" ")} failed (${result.status}): ${result.stderr ?? ""}`;
    throw new Error(redact(message).trim());
  }

  return { ok: result.status === 0, stdout: result.stdout ?? "", stderr: result.stderr ?? "" };
};

const git = (...args) => run("git", args).stdout.trim();
const gh = (args, options) => run("gh", args, options).stdout;
const ghJson = (args) => JSON.parse(gh(args) || "null");

const graphql = (query, variables) => {
  const args = ["api", "graphql", "-f", `query=${query}`];
  for (const [key, value] of Object.entries(variables)) {
    args.push(typeof value === "number" ? "-F" : "-f", `${key}=${value}`);
  }
  return ghJson(args).data;
};

const fence = (text, language = "text", marker = "```") => `${marker}${language}\n${text}\n${marker}`;

const truncate = (text, limit) => (text.length > limit ? `${text.slice(0, limit)}\n[truncated]` : text);

const readState = () => JSON.parse(readFileSync(statePath, "utf8"));

const writeState = (state) => writeFileSync(statePath, `${JSON.stringify(state, null, 2)}\n`);

const readOut = (name, fallback) => {
  const file = path.join(outDir, name);
  return existsSync(file) ? readFileSync(file, "utf8").trim() : fallback;
};

const [owner, name] = repo.split("/");

const maintainer = (association) => ["OWNER", "MEMBER", "COLLABORATOR"].includes(association);

// Bot reviews worth answering; our own comments and the review gate's status are not.
const reviewBot = (login) => /codex|graphite/i.test(login ?? "");

const feedbackQuery = `
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      body
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          path
          line
          comments(first: 30) { nodes { author { login } authorAssociation body } }
        }
      }
      reviews(last: 30) { nodes { author { login } authorAssociation body state submittedAt } }
      comments(last: 50) { nodes { author { login } authorAssociation body createdAt } }
    }
  }
}`;

const collectFeedback = (number, since) => {
  const pr = graphql(feedbackQuery, { owner, name, number }).repository.pullRequest;
  const counts = (login, association) => maintainer(association) || reviewBot(login);

  const threads = pr.reviewThreads.nodes
    .filter((thread) => !thread.isResolved)
    .filter((thread) => thread.comments.nodes.some((c) => counts(c.author?.login, c.authorAssociation)))
    .map((thread) => ({
      id: thread.id,
      location: `${thread.path}${thread.line ? `:${thread.line}` : ""}`,
      comments: thread.comments.nodes.map((c) => `${c.author?.login ?? "unknown"}: ${truncate(c.body, 3000)}`),
    }));

  const recent = (date) => !since || date > since;

  const comments = [
    ...pr.reviews.nodes
      .filter((r) => r.body?.trim() && recent(r.submittedAt) && counts(r.author?.login, r.authorAssociation))
      .map((r) => `${r.author?.login} (review, ${r.state}): ${truncate(r.body, 3000)}`),
    ...pr.comments.nodes
      .filter((c) => recent(c.createdAt) && counts(c.author?.login, c.authorAssociation))
      .map((c) => `${c.author?.login}: ${truncate(c.body, 3000)}`),
  ];

  return { body: pr.body, threads, comments };
};

// The checkout keeps no credentials, so the agent never holds the job token; fetch with it explicitly.
const fetchBranch = (name) => {
  const url = process.env.GH_TOKEN ? `https://x-access-token:${process.env.GH_TOKEN}@github.com/${repo}.git` : "origin";
  git("fetch", "--no-tags", url, `+refs/heads/${name}:refs/remotes/origin/${name}`);
};

const lastBotCommitDate = () => {
  const date = git("log", "-1", "--no-merges", "--format=%cI", `--author=${botIdentity[0]}`, "origin/main..HEAD");
  return date || null;
};

const commitWindow = () => {
  const merged = ghJson([
    "pr", "list", "--repo", repo, "--head", branch, "--state", "merged",
    "--limit", "1", "--json", "number,mergedAt,mergeCommit",
  ]);
  const floor = new Date(Date.now() - 30 * 86400_000).toISOString();
  const fallback = new Date(Date.now() - 14 * 86400_000).toISOString();
  const since = merged?.[0]?.mergedAt ?? fallback;

  return { since: since < floor ? floor : since, lastMerged: merged?.[0]?.number ?? null };
};

const rejectedProposals = () => {
  const cutoff = new Date(Date.now() - 60 * 86400_000).toISOString();
  const closed = ghJson([
    "pr", "list", "--repo", repo, "--head", branch, "--state", "closed",
    "--limit", "10", "--json", "number,title,body,mergedAt,closedAt,url",
  ]);

  return (closed ?? [])
    .filter((pr) => !pr.mergedAt && pr.closedAt > cutoff)
    .slice(0, 3)
    .map((pr) => {
      const { comments } = collectFeedback(pr.number, null);
      return [
        `### #${pr.number}, closed ${pr.closedAt.slice(0, 10)}`,
        truncate(pr.body ?? "", 4000),
        comments.length ? `Maintainer comments:\n${comments.map((c) => `- ${c}`).join("\n")}` : "",
      ].join("\n\n");
    });
};

const prepare = () => {
  rmSync(runtime, { recursive: true, force: true });
  mkdirSync(outDir, { recursive: true });

  fetchBranch("main");

  const open = ghJson([
    "pr", "list", "--repo", repo, "--head", branch, "--state", "open",
    "--limit", "1", "--json", "number,url,baseRefName",
  ])?.[0];

  const state = { pr: open?.number ?? null, url: open?.url ?? null, merged: false, conflict: false };
  let feedbackSince = null;

  if (open) {
    fetchBranch(branch);
    git("checkout", "-B", branch, `origin/${branch}`);
    feedbackSince = lastBotCommitDate();

    const behind = git("rev-list", "--count", `HEAD..origin/main`) !== "0";
    if (behind) {
      const merge = run("git", ["merge", "--no-edit", "origin/main"], { allowFailure: true, env: botEnv });
      if (!merge.ok) {
        run("git", ["merge", "--abort"], { allowFailure: true });
        state.conflict = true;
        writeState(state);
        console.log(`Branch ${branch} conflicts with main; a maintainer must resolve it.`);
        return;
      }
      state.merged = true;
    }
  } else {
    git("checkout", "-B", branch, "origin/main");
  }

  state.base = git("rev-parse", "HEAD");

  const window = commitWindow();
  const commits = git(
    "log", "origin/main", `--since=${window.since}`, "--no-merges", "--date=short",
    "--format=%h %ad %s", "--invert-grep", "--grep=^deploy(prod): release",
    "--", ".", ":(exclude)research", ":(exclude).agents", ":(exclude)infra", ":(exclude).github",
  );

  const sections = [
    "## Context for today's run",
    `Date: ${new Date().toISOString().slice(0, 10)}`,
    `Commits on main since ${window.since.slice(0, 10)}${window.lastMerged ? ` (when docs PR #${window.lastMerged} merged)` : ""}, newest first. Release, research, infrastructure and CI-only commits are left out:`,
    fence(truncate(commits || "(none)", 40_000)),
  ];

  if (open) {
    const feedback = collectFeedback(open.number, feedbackSince);
    const branchDiff = git("diff", "--stat", "origin/main...HEAD");

    sections.push(
      `## Open docs pull request #${open.number}`,
      `You are on branch \`${branch}\`, which already holds this pull request's changes${state.merged ? " with main merged in" : ""}. Files changed compared with main:`,
      fence(branchDiff || "(no changes)"),
      "Current pull request description:",
      fence(truncate(feedback.body ?? "", 8000), "markdown", "````"),
      "### Unresolved review threads",
      feedback.threads.length
        ? feedback.threads
            .map((t) => [`Thread \`${t.id}\` at \`${t.location}\`:`, ...t.comments.map((c) => `> ${c.replaceAll("\n", "\n> ")}`)].join("\n"))
            .join("\n\n")
        : "None.",
      "### Comments since the last docs update",
      feedback.comments.length ? feedback.comments.map((c) => `- ${c.replaceAll("\n", "\n  ")}`).join("\n") : "None.",
    );
  } else {
    sections.push("## Open docs pull request", `None. You are on a fresh branch from main. If you make changes, a new pull request opens.`);
  }

  const rejected = rejectedProposals();
  sections.push(
    "## Proposals closed without merging in the last 60 days",
    rejected.length ? rejected.join("\n\n") : "None.",
  );

  const prompt = `${readFileSync(path.join(toolDir, "prompt.md"), "utf8")}\n${sections.join("\n\n")}\n`;
  writeFileSync(path.join(runtime, "prompt.md"), prompt);
  writeState(state);
  console.log(`Prepared ${open ? `PR #${open.number}` : "a fresh branch"}; ${commits.split("\n").filter(Boolean).length} commits in the window.`);
};

export const formatAudits = (audits) => {
  const sections = audits.map(({ group, findings, error }) => {
    const heading = `### ${group.pages.join(", ")}`;
    if (error) return `${heading}\n\nThe audit failed (${error}). Audit these pages yourself.`;
    if (!findings.length) return `${heading}\n\nNo findings.`;

    const items = findings.map((finding) =>
      [
        `- \`${finding.page}\`: ${finding.problem}`,
        `  Claim: ${finding.claim.replaceAll("\n", " ")}`,
        `  Evidence: ${finding.evidence.map((ref) => `\`${ref}\``).join(", ")}`,
        `  Suggested fix: ${finding.fix.replaceAll("\n", " ")}`,
      ].join("\n"),
    );
    return `${heading}\n\n${items.join("\n")}`;
  });

  return ["## Audit findings", ...sections].join("\n\n");
};

const agent = async () => {
  const state = readState();
  if (state.conflict) return;

  const { runAgent, runAudits } = await import("./agent.mjs");
  let prompt = readFileSync(path.join(runtime, "prompt.md"), "utf8");

  const gradiatedApiKey = process.env.DOCS_REFRESH_GRADIATED_API_KEY;
  const model = gradiatedApiKey
    ? process.env.DOCS_REFRESH_AUDIT_MODEL || "moonshotai/kimi-k3.1-pro"
    : process.env.DOCS_REFRESH_FALLBACK_AUDIT_MODEL || "claude-sonnet-5-5";
  console.log(`Auditing the docs with ${model}${gradiatedApiKey ? " on Gradiated" : ""}.`);

  const audits = await runAudits({
    root,
    template: readFileSync(path.join(toolDir, "audit-prompt.md"), "utf8"),
    model,
    gradiatedApiKey,
    concurrency: Number(process.env.DOCS_REFRESH_AUDIT_CONCURRENCY || (gradiatedApiKey ? "2" : "4")),
  });
  const findings = formatAudits(audits);
  writeFileSync(path.join(runtime, "audits.md"), `${findings}\n`);
  prompt = `${prompt}\n${findings}\n`;

  const output = await runAgent({
    root,
    prompt,
    isAllowed,
    model: process.env.DOCS_REFRESH_MODEL || "claude-opus-5-5",
    effort: process.env.DOCS_REFRESH_EFFORT || "high",
    maxBudgetUsd: Number(process.env.DOCS_REFRESH_MAX_BUDGET_USD || "20"),
  });

  const prBody = output.prBody.replace(/\n*🤖 Generated with \[Claude Code\]\([^)]*\)\s*$/u, "");
  writeFileSync(path.join(outDir, "pr-body.md"), `${prBody.trim()}\n`);
  writeFileSync(path.join(outDir, "update.md"), `${output.update.trim()}\n`);
  writeFileSync(path.join(outDir, "threads.json"), `${JSON.stringify(output.threads, null, 2)}\n`);
  writeFileSync(path.join(outDir, "notes.md"), `${output.notes.trim()}\n`);
};

export const parseStatus = (output) =>
  output
    .split("\0")
    .filter(Boolean)
    .map((entry) => ({ untracked: entry.startsWith("??"), file: entry.slice(3) }));

const changes = () => parseStatus(run("git", ["status", "--porcelain", "--untracked-files=all", "-z"]).stdout);

const changedFiles = () => changes().map((change) => change.file);

const discardOutsideScope = () => {
  const outside = changes().filter((change) => !isAllowed(change.file));
  if (!outside.length) return;

  console.log(`Discarding changes outside the docs paths:\n${outside.map((c) => `  ${c.file}`).join("\n")}`);
  const tracked = outside.filter((c) => !c.untracked).map((c) => c.file);
  const untracked = outside.filter((c) => c.untracked).map((c) => c.file);
  if (tracked.length) run("git", ["checkout", "HEAD", "--", ...tracked]);
  if (untracked.length) run("git", ["clean", "-fq", "--", ...untracked]);
};

const pushUrl = () => `https://x-access-token:${process.env.DOCS_APP_TOKEN}@github.com/${repo}.git`;

const comment = (number, body) => {
  gh(["pr", "comment", String(number), "--repo", repo, "--body-file", "-"], { input: body });
};

const replyToThreads = () => {
  let threads = [];
  try {
    threads = JSON.parse(readOut("threads.json", "[]"));
  } catch (error) {
    console.log(`Ignoring unreadable threads.json: ${error.message}`);
  }

  for (const thread of Array.isArray(threads) ? threads : []) {
    if (!thread?.thread || !thread.reply) continue;
    graphql(
      `mutation($id: ID!, $body: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $id, body: $body}) { comment { id } } }`,
      { id: thread.thread, body: thread.reply },
    );
    if (thread.resolve !== false) {
      graphql(`mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id } } }`, { id: thread.thread });
    }
  }
};

const footer = () => {
  const server = process.env.GITHUB_SERVER_URL ?? "https://github.com";
  const runUrl = process.env.GITHUB_RUN_ID ? `${server}/${repo}/actions/runs/${process.env.GITHUB_RUN_ID}` : null;
  return [
    "",
    "---",
    `Opened by the [docs refresh workflow](${server}/${repo}/blob/main/.github/workflows/docs-refresh.yml)${runUrl ? ` ([latest run](${runUrl}))` : ""}. It updates this pull request daily until it merges. Leave review comments here; the next run reads them. Close the pull request to reject the proposal.`,
  ].join("\n");
};

const publish = () => {
  const state = readState();
  const dryRun = process.env.DOCS_REFRESH_DRY_RUN === "true";

  if (state.conflict) {
    if (!dryRun) {
      comment(state.pr, `\`${branch}\` conflicts with \`main\`, so today's docs refresh did not run. Merge \`main\` into this branch and resolve the conflict, or close this pull request so the next run starts fresh.`);
    }
    throw new Error("The docs branch conflicts with main.");
  }

  discardOutsideScope();
  const docsChanged = changedFiles().length > 0;

  if (docsChanged) {
    run("pnpm", ["--dir", "product", "--filter", "gradiated-com", "build"], { inherit: true });
    discardOutsideScope();
  }

  const update = readOut("update.md", "No changes today.");
  const notes = readOut("notes.md", "None.");
  console.log(`Update:\n${update}\n\nNotes:\n${notes}`);
  run("git", ["--no-pager", "diff", "--stat"], { inherit: true });

  if (dryRun) {
    run("git", ["--no-pager", "diff"], { inherit: true });
    console.log("Dry run: nothing pushed.");
    return;
  }

  if (docsChanged) {
    run("git", ["add", "--all", "--", ...changedFiles()]);
    run("git", ["commit", "--file", "-"], { input: `${title}\n\n${update}\n`, env: botEnv });
  }

  const pushed = docsChanged;
  if (pushed) {
    const args = ["push", pushUrl(), `HEAD:refs/heads/${branch}`];
    // A branch left from a closed proposal is replaced; an open PR's branch only moves forward.
    if (!state.pr) args.splice(1, 0, "--force");
    run("git", args);
  }

  const body = `${readOut("pr-body.md", "## What changed\n\nSee the commits.")}\n${footer()}`;

  if (state.pr) {
    if (pushed) {
      gh(["pr", "edit", String(state.pr), "--repo", repo, "--body-file", "-"], { input: body });
      comment(state.pr, `Today's docs update:\n\n${update}`);
    }
    replyToThreads();
    console.log(pushed ? `Updated ${state.url}` : `No new changes for ${state.url}`);
    return;
  }

  if (!pushed) {
    console.log("No docs changes today; no pull request opened.");
    return;
  }

  const url = gh(
    ["pr", "create", "--repo", repo, "--base", "main", "--head", branch, "--title", title, "--body-file", "-"],
    { input: body },
  ).trim();
  console.log(`Opened ${url}`);
};

const commands = { prepare, agent, publish };

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const command = commands[process.argv[2]];
  if (!command) {
    console.error(`Usage: node refresh.mjs ${Object.keys(commands).join("|")}`);
    process.exit(2);
  }
  await command();
}
