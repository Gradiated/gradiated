# Agent task queue

GitHub Issues are the shared task system and GitHub Projects are the execution view. Do not depend on a chat thread to explain work. The repository remains the source of truth for code, research, prompts, and artifacts.

## Workflow

1. Create a GitHub issue from the appropriate template, then link its URL in a task packet based on `tasks/template.md` when detailed local coordination is needed.
2. Claim the issue and set its Project status to `In Progress`; then move the packet to `tasks/active/` and add the owner, thread, scope, and start time.
3. Work only inside the declared scope. Split the task if another agent needs overlapping files.
4. Move completed packets to `tasks/done/` with the verification result and commit SHA.
5. Keep `tasks/queue.md` as a local mirror only; the GitHub issue and Project are authoritative for cross-agent priority and status.

Use stable IDs such as `2026-07-13-browser-runtime`. Never put credentials, cookies, or private external state in a task packet.
