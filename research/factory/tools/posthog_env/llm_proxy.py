"""Route OpenAI and Anthropic calls through the CLIProxyAPI subscription proxy (stdlib only).

Deployed to /opt/posthog-env/llm_proxy.py on the GPU host, where an SSH reverse tunnel maps 127.0.0.1:8317 to the
proxy. The client key is read from CLIPROXY_KEY or /root/.cliproxy_key and is never printed.

Two uses:
  * judges, critics and calibration: `judge_complete(prompt, model, effort)` posts one chat completion to the proxy
    with retries and backoff. There is no fallback transport.
  * PostHog AI rollouts (agent_driver.install_models): with POSTHOG_ENV_LLM_VIA_PROXY=1 the OpenAI sub-models and the
    Anthropic root/summarizer use the proxy as their base URL. `SUBMODEL_MAP` maps models the subscriptions do not
    offer to the closest available one. Launch scripts call `default_on_for_new_runs()` so new runs opt in while
    steps of chains that were already running keep their original routing.
"""

from __future__ import annotations

import contextlib
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request

PROXY_BASE = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8317").rstrip("/")
KEY_FILE = os.environ.get("CLIPROXY_KEY_FILE", "/root/.cliproxy_key")
FLAG = "POSTHOG_ENV_LLM_VIA_PROXY"
# Chains already running when the proxy became the default keep their original routing.
CUTOVER_EPOCH = float(os.environ.get("POSTHOG_ENV_LLM_PROXY_CUTOVER", "1793373300"))  # 2026-10-30 15:15 UTC

# Sub-models PostHog requests that neither subscription serves -> closest model the proxy offers.
# gpt-4.1 (non-reasoning, mid tier; taxonomy, memory, max_tools) -> gpt-5.6-terra
# gpt-5.2 (frontier, called with reasoning effort "none"; schema generators) -> gpt-5.6-sol
SUBMODEL_MAP = {
    "gpt-4.1": "gpt-5.6-terra",
    "gpt-4o": "gpt-5.6-terra",
    "gpt-4": "gpt-5.6-terra",
    "gpt-5": "gpt-5.6-terra",
    "gpt-5.2": "gpt-5.6-sol",
    "gpt-5.5": "gpt-5.6-sol",
    "gpt-4.1-mini": "gpt-5.6-luna",
    "gpt-4o-mini": "gpt-5.6-luna",
    "gpt-5-mini": "gpt-5.6-luna",
    "o4-mini": "gpt-5.6-luna",
    "o3": "gpt-5.6-sol",
}

# The retired Codex relay prefixed every judge prompt with this; kept so judge prompts are unchanged.
JUDGE_PREAMBLE = ("You are being used as an evaluation judge, not as a coding agent. Do not run commands or edit "
                  "files. Read the task below and reply with only the requested output.\n\n")

_SLOTS: threading.BoundedSemaphore | None = None
_SLOTS_LOCK = threading.Lock()


def proxy_key() -> str:
    key = os.environ.get("CLIPROXY_KEY")
    if key:
        return key
    with open(KEY_FILE) as f:
        return f.read().strip()


def available() -> bool:
    return bool(os.environ.get("CLIPROXY_KEY")) or os.path.exists(KEY_FILE)


def enabled() -> bool:
    """Rollout opt-in for PostHog sub-models and the Anthropic root."""
    return os.environ.get(FLAG) == "1"


def _slots() -> threading.BoundedSemaphore:
    global _SLOTS
    with _SLOTS_LOCK:
        if _SLOTS is None:
            n = os.environ.get("LLM_PROXY_CONCURRENCY") or os.environ.get("CODEX_RELAY_CONCURRENCY") or "8"
            _SLOTS = threading.BoundedSemaphore(int(n))
    return _SLOTS


def chat(body: dict, timeout: float = 900) -> dict:
    """One POST to the proxy's /v1/chat/completions; raises urllib errors."""
    req = urllib.request.Request(f"{PROXY_BASE}/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {proxy_key()}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def judge_complete(prompt: str, model: str = "gpt-6.1-sol", reasoning_effort: str | None = None,
                   attempts: int = 8, timeout: float = 900, preamble: bool = True,
                   limit: bool = True) -> tuple[str, dict]:
    """Judge text through the proxy, retried with jittered exponential backoff. Returns (text, raw usage).
    limit=True caps concurrent calls per process (LLM_PROXY_CONCURRENCY, else CODEX_RELAY_CONCURRENCY, else 8)."""
    body: dict = {"model": model,
                  "messages": [{"role": "user", "content": (JUDGE_PREAMBLE if preamble else "") + prompt}]}
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    last = ""
    for attempt in range(attempts):
        with _slots() if limit else contextlib.nullcontext():
            try:
                d = chat(body, timeout)
                text = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                if text:
                    return text, d.get("usage") or {}
                last = "empty completion"
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read()[:200].decode(errors='replace')}"
            except Exception as e:  # noqa: BLE001
                last = f"{type(e).__name__}: {str(e)[:200]}"
        time.sleep(min(60.0, 2 ** attempt * 2) * (0.75 + 0.5 * random.random()))
    raise RuntimeError(f"proxy judge failed after {attempts} attempts: {last}")


def rollout_env() -> dict[str, str]:
    """Environment that points the OpenAI and Anthropic SDKs (and PostHog's OPENAI_BASE_URL setting) at the proxy."""
    key = proxy_key()
    return {"OPENAI_BASE_URL": f"{PROXY_BASE}/v1", "OPENAI_API_BASE": f"{PROXY_BASE}/v1", "OPENAI_API_KEY": key,
            "ANTHROPIC_BASE_URL": PROXY_BASE, "ANTHROPIC_API_URL": PROXY_BASE, "ANTHROPIC_API_KEY": key}


def _start_epoch(pid: int) -> float:
    with open("/proc/stat") as f:
        btime = next(int(line.split()[1]) for line in f if line.startswith("btime"))
    with open(f"/proc/{pid}/stat") as f:
        fields = f.read().rsplit(")", 1)[1].split()
    return btime + int(fields[19]) / os.sysconf("SC_CLK_TCK")


def _old_chain_ancestor() -> str | None:
    """A script (bash/python) ancestor started before the cutover, i.e. a chain that predates the proxy default."""
    pid = os.getppid()
    while pid > 1:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                args = [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
            with open(f"/proc/{pid}/stat") as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
            is_script = any(a.endswith((".sh", ".py")) for a in args[1:]) or (
                len(args) >= 3 and os.path.basename(args[0]) in ("bash", "sh") and args[1] == "-c")
            if is_script and _start_epoch(pid) < CUTOVER_EPOCH:
                return " ".join(args)[:120]
        except FileNotFoundError:  # the ancestor exited while walking; its children were reparented
            return None
        except (OSError, ValueError, StopIteration, IndexError):
            return "unknown ancestry"  # conservative: keep the original routing
        pid = ppid
    return None


def default_on_for_new_runs() -> None:
    """Called at the top of launch scripts: opt new runs into the proxy unless the flag is set explicitly, the key
    is missing, or the launch is a later step of a chain that was already running at the cutover."""
    if FLAG in os.environ or not available():
        return
    if _old_chain_ancestor() is None:
        os.environ[FLAG] = "1"
