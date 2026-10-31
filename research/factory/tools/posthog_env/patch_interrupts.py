"""Resume PostHog AI graph interrupts in the env runner (loop review b10). Idempotent; backs up run_task.py once.

    python3 patch_interrupts.py /opt/posthog-env/runner/run_task.py

PostHog AI pauses its graph (LangGraph interrupt) for approval-gated tools (e.g. editing a saved insight), for
create_form questions, and for client-side tools. The runner never resumed, so the turn ended on the tool call with no
result and no final answer while reporting status ok (3 of 15 b10 pilot rollouts). Now each pending interrupt is
resumed the way a typical user would respond, up to 10 times per turn:
  ApprovalRequest        -> approve
  MultiQuestionForm      -> dismiss the form (the tool tells the agent to continue without the answers)
  ClientToolCallRequest  -> result {"error": "not available in this environment"}
Each resume is recorded in the turn info ("resumes"); a turn that still ends with a pending interrupt gets status
"interrupted", and a turn without a final answer gets status "no_final_answer" (both excluded from normal scoring).
"""

import os
import shutil
import sys

p = sys.argv[1]
bak = p + ".before-interrupts-20261031"
if not os.path.exists(bak):
    shutil.copy2(p, bak)
s = open(p).read()
if "async def resume_interrupts" in s:
    print("already patched")
    sys.exit(0)

helper = '''
def _pending_interrupts(snapshot) -> list:
    return [(task, intr) for task in (snapshot.tasks or []) if getattr(task, "result", None) is None
            for intr in (getattr(task, "interrupts", None) or [])]


def _resume_payload_for(value) -> tuple[str, dict] | None:
    from ee.hogai.tool import ClientToolCallRequest, pending_approval_proposal_id
    from posthog.schema import MultiQuestionForm

    pid = pending_approval_proposal_id(value)
    if pid:
        return "approve", {"action": "approve", "proposal_id": pid}
    if isinstance(value, MultiQuestionForm):
        return "dismiss_form", {"action": "dismiss_form"}
    if isinstance(value, ClientToolCallRequest):
        return "client_tool_unavailable", {"action": "client_tool_result", "tool_call_id": value.original_tool_call_id,
                                           "result": {"error": "This action is not available in this environment."}}
    return None


async def resume_interrupts(team, user, conversation, runner, info: dict, consume_fn, deadline: float) -> None:
    """Resume pending graph interrupts like a typical user (approve / dismiss form / client tool unavailable)."""
    from ee.hogai.chat_agent.runner import ChatAgentRunner

    for _ in range(10):
        try:
            snapshot = await runner._graph.aget_state(runner._get_config())
        except Exception:  # noqa: BLE001
            return
        pend = _pending_interrupts(snapshot)
        if not pend:
            return
        got = _resume_payload_for(pend[0][1].value)
        if got is None or deadline - time.time() < 10:
            info["status"] = "interrupted"
            return
        kind, payload = got
        info.setdefault("resumes", []).append(kind)
        runner = ChatAgentRunner(team, conversation, new_message=None, user=user, is_new_conversation=False,
                                 resume_payload=payload, is_agent_billable=False)
        try:
            await asyncio.wait_for(consume_fn(runner), timeout=deadline - time.time())
        except TimeoutError:
            info["status"] = "wall_time"
            return
        except Exception as e:  # noqa: BLE001
            info["resume_error"] = f"{type(e).__name__}: {str(e)[:200]}"
            return
    info["status"] = "interrupted"

'''
anchor = "async def run_conversation("
assert s.count(anchor) == 1
s = s.replace(anchor, helper + "\n" + anchor, 1)

old = '''        async def consume() -> None:
            async for _kind, msg in runner.astream():
                if isinstance(msg, FailureMessage):
                    info["failure_messages"] += 1

        try:
            await asyncio.wait_for(consume(), timeout=remaining)'''
new = '''        async def consume_runner(r) -> None:
            async for _kind, msg in r.astream():
                if isinstance(msg, FailureMessage):
                    info["failure_messages"] += 1

        async def consume() -> None:
            await consume_runner(runner)

        try:
            await asyncio.wait_for(consume(), timeout=remaining)
            await resume_interrupts(team, user, conversation, runner, info, consume_runner, deadline)'''
assert s.count(old) == 1, s.count(old)
s = s.replace(old, new, 1)
open(p, "w").write(s)
print("patched")
