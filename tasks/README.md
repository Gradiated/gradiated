# Agent task queue

GitHub Issues are the shared task system and GitHub Projects are the execution view. Do not depend on a chat thread to explain work. The repository remains the source of truth for code, research, prompts, and artifacts.

## Workflow

1. Create a GitHub issue from the appropriate template, then link its URL in a task packet based on `tasks/template.md` when detailed local coordination is needed.
2. Claim the issue and set its Project status to `In Progress`; then move the packet from `tasks/inbox/` to `tasks/active/` and add the owner, thread, scope, and start time.
3. Work only inside the declared scope. Split the task if another agent needs overlapping files.
4. Move completed packets to `tasks/done/` with the verification result, commit SHA, known limitations, and exact resume command.
5. Keep `tasks/queue.md` as a local mirror only; the GitHub issue and Project are authoritative for cross-agent priority and status.

The directories have explicit meanings:

- `tasks/inbox/`: accepted but not started packets;
- `tasks/active/`: one claimed owner is working the packet;
- `tasks/done/`: completed or permanently blocked handoffs.

Use one stable packet ID per issue. Do not create a second packet to represent the same work, and do not use a packet as a substitute for the GitHub issue.

Use stable IDs such as `2026-07-13-browser-runtime`. Never put credentials, cookies, or private external state in a task packet.

For agents sharing this workspace, use `python3 tools/devex/claim.py start <stable-id> --issue <url> --scope <path-or-artifact-root>` before editing. It uses an atomic directory claim under `tasks/active/`; a second process receives the existing claim instead of overwriting the packet. Release the claim after a completed or blocked handoff. This protects local concurrency only; GitHub remains the cross-agent source of truth.
