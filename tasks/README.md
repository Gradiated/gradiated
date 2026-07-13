# Agent task queue

The repository is the shared task system. Do not depend on a chat thread to explain work.

## Workflow

1. Create one task packet from `tasks/template.md` under `tasks/inbox/`.
2. Claim it by moving it to `tasks/active/` and adding the owner, thread, scope, and start time.
3. Work only inside the declared scope. Split the task if another agent needs overlapping files.
4. Move completed packets to `tasks/done/` with the verification result and commit SHA.
5. Keep `tasks/queue.md` as the short list of priorities; the task packet is authoritative.

Use stable IDs such as `2026-07-13-browser-runtime`. Never put credentials, cookies, or private external state in a task packet.
