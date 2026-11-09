"""Resolve trusted, explicit clean Codex receipts to actual PR commits."""
import json
from pathlib import Path
import re
import sys

BOT = "chatgpt-codex-connector"
MARKER = "<!-- codex-review-receipt:v1 -->"
COMMIT = re.compile(r"^\*\*Reviewed commit:\*\*\s*`([0-9a-f]{7,40})`[ \t]*$", re.M)
CLEAN = re.compile(r"^Codex Review: Didn't find any major issues[.!](?:[^\n]*)$", re.M)
BADGE = re.compile(r"!\[P[012] Badge\]")
BLOCKING_BADGE = re.compile(r"!\[P[01] Badge\]")


def clean_commits(comments, commits, inline_comments):
    commits = list(dict.fromkeys(sha for sha in commits if re.fullmatch(r"[0-9a-f]{40}", sha)))
    accepted = set()
    for comment in comments:
        actor = comment.get("author") or {}
        if actor.get("__typename") != "Bot" or actor.get("login") != BOT:
            continue
        edits = comment.get("userContentEdits") or {}
        if edits.get("pageInfo", {}).get("hasNextPage") is not False:
            continue
        history = edits.get("nodes")
        if not isinstance(history, list) or any(not isinstance(edit, dict) or
               (edit.get("editor") or {}).get("__typename") != "Bot" or
               (edit.get("editor") or {}).get("login") != BOT for edit in history):
            continue
        body = comment.get("body") or ""
        lines = body.splitlines()
        result = [line for line in lines[1:] if line.strip()]
        if (not lines or lines[0] != MARKER or len(result) < 2 or not CLEAN.fullmatch(result[0])
                or not COMMIT.fullmatch(result[1]) or BADGE.search(body)
                or "Here are some automated review suggestions" in body):
            continue
        references = COMMIT.findall(body)
        if len(references) != 1:
            continue
        matches = [sha for sha in commits if sha.startswith(references[0])]
        if len(matches) != 1:
            continue
        sha = matches[0]
        if any(item.get("login") == BOT + "[bot]" and item.get("reply") is None and
               item.get("commit") == sha and BLOCKING_BADGE.search(item.get("body") or "")
               for item in inline_comments):
            continue
        accepted.add(sha)
    return [sha for sha in commits if sha in accepted]


if __name__ == "__main__":
    comments, commits, inline_comments = map(Path, sys.argv[1:])
    for sha in clean_commits(json.loads(comments.read_text()), commits.read_text().splitlines(),
                             json.loads(inline_comments.read_text())):
        print(sha)
