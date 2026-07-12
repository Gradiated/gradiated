#!/usr/bin/env python3
"""Sartor bridge: progress dashboard + prompt inbox. Stdlib only.
GET /            dashboard (auto-refreshing)
GET /api/state   {status, chat}
POST /prompt     {text} -> appended to inbox.jsonl (picked up by Claude's monitor)
"""
import html as html_lib
import hmac
import json, os, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIR = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(DIR, "inbox.jsonl")
OUTBOX = os.path.join(DIR, "outbox.jsonl")
STATUS = os.path.join(DIR, "status.json")
LABLOG = os.path.join(DIR, "lablog.jsonl")
REPORT = os.path.join(DIR, "..", "docs", "REPORT.md")
CODEX_ROOT = os.environ.get("SARTOR_CODEX_ROOT", "/Users/js/dev/inference-foundry")
CODEX_PROMPT_MAX_CHARS = 20000
CODEX_REQUEST_MAX_BYTES = 65536

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>sartor — live</title><style>
body{background:#0d1117;color:#e6edf3;font:15px/1.5 -apple-system,system-ui,sans-serif;max-width:780px;margin:0 auto;padding:16px}
h1{font-size:18px} h2{font-size:14px;color:#8b949e;margin:18px 0 6px;text-transform:uppercase;letter-spacing:.05em}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;margin:8px 0;white-space:pre-wrap;word-wrap:break-word}
.me{border-left:3px solid #d29922}.claude{border-left:3px solid #2f81f7}
.ts{color:#8b949e;font-size:12px}
textarea{width:100%;box-sizing:border-box;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:10px;font:inherit;min-height:70px}
button,.codex-link{background:#238636;color:#fff;border:0;border-radius:8px;padding:10px 18px;font:inherit;margin-top:6px;cursor:pointer}
.codex-link{display:inline-block;text-decoration:none;background:#8957e5;margin:0 0 10px}
#stat{color:#3fb950;font-size:13px}</style></head><body>
<h1>🚢 sartor — live progress <span id="stat"></span></h1>
<a class="codex-link" href="/codex">open inference foundry · Codex</a>
<h2>send a prompt to Claude</h2>
<textarea id="t" placeholder="prompt…"></textarea><br>
<button onclick="send()">send</button>
<h2>status</h2><div class="card" id="status">loading…</div>
<h2>conversation</h2><div id="chat"></div>
<h2>lab log (newest first)</h2><div id="lablog"></div>
<h2>full report (auto-updates)</h2><div class="card" id="report" style="white-space:normal">loading…</div>
<style>#report table{border-collapse:collapse;margin:8px 0;display:block;overflow-x:auto}
#report td,#report th{border:1px solid #30363d;padding:4px 8px;font-size:13px}
#report h1,#report h2,#report h3{margin:14px 0 6px}#report code{background:#0d1117;padding:1px 4px;border-radius:4px}</style>
<script>
async function refresh(){
  try{
    const r=await fetch('/api/state');const d=await r.json();
    document.getElementById('status').textContent=d.status_text;
    document.getElementById('stat').textContent='· updated '+d.updated;
    document.getElementById('chat').innerHTML=d.chat.map(m=>
      `<div class="card ${m.who}"><span class="ts">${m.ts} — ${m.who}</span>\n${m.text
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')}</div>`).join('');
    document.getElementById('lablog').innerHTML=d.lablog.map(e=>
      `<div class="card"><span class="ts">${e.ts} · ${e.kind}</span>\n${e.text.replace(/&/g,'&amp;').replace(/</g,'&lt;')}</div>`).join('');
  }catch(e){document.getElementById('stat').textContent='· reconnecting…'}
}
async function send(){
  const t=document.getElementById('t').value.trim();if(!t)return;
  await fetch('/prompt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});
  document.getElementById('t').value='';setTimeout(refresh,300);
}
async function loadReport(){try{const r=await fetch('/report');document.getElementById('report').innerHTML=await r.text();}catch(e){}}
refresh();setInterval(refresh,8000);loadReport();setInterval(loadReport,60000);
</script></body></html>"""

def read_jsonl(p):
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out

def read_json(p, fallback):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return fallback

def render_markdown(p, label):
    try:
        with open(p, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return "<pre>" + html_lib.escape(label + " not available") + "</pre>"
    try:
        import markdown
        return markdown.markdown(text, extensions=["tables", "fenced_code"])
    except Exception:
        return "<pre>" + html_lib.escape(text) + "</pre>"

class H(BaseHTTPRequestHandler):
    inbox_path = INBOX
    outbox_path = OUTBOX
    status_path = STATUS
    lablog_path = LABLOG
    report_path = REPORT
    codex_index_path = os.path.join(CODEX_ROOT, "dashboard", "index.html")
    codex_status_path = os.path.join(CODEX_ROOT, "dashboard", "status.json")
    codex_inbox_path = os.path.join(CODEX_ROOT, "dashboard", "inbox.jsonl")
    codex_outbox_path = os.path.join(CODEX_ROOT, "dashboard", "outbox.jsonl")
    codex_prompt_token_path = os.path.join(CODEX_ROOT, "dashboard", "prompt-token")
    codex_monitor_heartbeat_path = os.path.join(
        CODEX_ROOT, "dashboard", ".monitor-heartbeat"
    )
    codex_summary_path = os.path.join(
        CODEX_ROOT, "experiments", "qwen3-8b", "summary-v0.json"
    )
    codex_validation_result_path = os.path.join(
        CODEX_ROOT, "validation", "results", "qwen3-0.6b-int4-sweep-v1.json"
    )
    codex_report_path = os.path.join(
        CODEX_ROOT, "experiments", "qwen3-8b", "README.md"
    )
    codex_validation_path = os.path.join(CODEX_ROOT, "validation", "README.md")
    codex_overnight_path = os.path.join(
        CODEX_ROOT, "docs", "OVERNIGHT_REPORT_2026-07-12.md"
    )
    codex_glm_path = os.path.join(CODEX_ROOT, "docs", "GLM_CO_DESIGN.md")
    codex_business_path = os.path.join(
        CODEX_ROOT, "docs", "BUSINESS_VALIDATION.md"
    )
    codex_simulators_path = os.path.join(
        CODEX_ROOT, "docs", "SIMULATOR_LANDSCAPE.md"
    )
    codex_decisions_path = os.path.join(
        CODEX_ROOT, "docs", "OPTIMIZATION_DECISIONS.md"
    )
    codex_hardware_path = os.path.join(
        CODEX_ROOT, "docs", "CUSTOM_HARDWARE_FEASIBILITY.md"
    )

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _send_json(self, code, value):
        self._send(
            code,
            json.dumps(value, ensure_ascii=False),
            "application/json; charset=utf-8",
        )

    def _codex_chat(self):
        chat = []
        for who, path in (("me", self.codex_inbox_path), ("codex", self.codex_outbox_path)):
            for message in read_jsonl(path):
                if isinstance(message, dict):
                    chat.append({**message, "who": who})
        chat.sort(key=lambda message: message.get("ts", ""), reverse=True)
        return chat[:100]

    def _codex_chat_summary(self):
        inbox = [message for message in read_jsonl(self.codex_inbox_path) if isinstance(message, dict)]
        outbox = [message for message in read_jsonl(self.codex_outbox_path) if isinstance(message, dict)]
        return {
            "inbox_count": len(inbox),
            "outbox_count": len(outbox),
            "latest_inbox_timestamp": max(
                (message.get("ts", "") for message in inbox), default=""
            ),
            "latest_outbox_timestamp": max(
                (message.get("ts", "") for message in outbox), default=""
            ),
        }

    def _codex_authorized(self):
        try:
            with open(self.codex_prompt_token_path, encoding="utf-8") as f:
                expected = f.read().strip()
        except (OSError, UnicodeDecodeError):
            return False
        supplied = self.headers.get("X-Codex-Prompt-Token", "")
        return bool(expected) and hmac.compare_digest(
            supplied.encode("utf-8"), expected.encode("utf-8")
        )

    def _codex_session_active(self):
        try:
            age_seconds = time.time() - os.path.getmtime(
                self.codex_monitor_heartbeat_path
            )
        except OSError:
            return False
        return 0.0 <= age_seconds <= 30.0

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path in ("/codex", "/codex/"):
            try:
                with open(self.codex_index_path, encoding="utf-8") as f:
                    page = f.read()
            except (OSError, UnicodeDecodeError):
                return self._send(404, "codex dashboard not available", "text/plain; charset=utf-8")
            self._send(200, page, "text/html; charset=utf-8")
        elif self.path == "/api/codex-state":
            status = read_json(self.codex_status_path, {})
            chat = self._codex_chat() if self._codex_authorized() else []
            self._send_json(200, {
                "status": status,
                "status_text": status.get("claim_status", {}).get("summary", ""),
                "summary": read_json(self.codex_summary_path, {}),
                "validation": read_json(self.codex_validation_result_path, {}),
                "chat": chat,
                "chat_summary": self._codex_chat_summary(),
                "recent_progress": status.get("recent_progress", []),
                "session_active": self._codex_session_active(),
                "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
        elif self.path in ("/codex/status.json", "/dashboard/status.json"):
            self._send_json(200, read_json(self.codex_status_path, {}))
        elif self.path == "/codex/report":
            self._send(
                200,
                render_markdown(self.codex_report_path, "Codex report"),
                "text/html; charset=utf-8",
            )
        elif self.path == "/codex/validation":
            self._send(
                200,
                render_markdown(self.codex_validation_path, "Codex validation"),
                "text/html; charset=utf-8",
            )
        elif self.path in (
            "/codex/overnight",
            "/codex/glm",
            "/codex/business",
            "/codex/simulators",
            "/codex/decisions",
            "/codex/hardware",
        ):
            path, label = {
                "/codex/overnight": (self.codex_overnight_path, "Codex overnight report"),
                "/codex/glm": (self.codex_glm_path, "Codex GLM dossier"),
                "/codex/business": (self.codex_business_path, "Codex business dossier"),
                "/codex/simulators": (
                    self.codex_simulators_path,
                    "Codex simulator landscape",
                ),
                "/codex/decisions": (
                    self.codex_decisions_path,
                    "Codex optimization decisions",
                ),
                "/codex/hardware": (
                    self.codex_hardware_path,
                    "Codex custom hardware feasibility audit",
                ),
            }[self.path]
            self._send(
                200,
                render_markdown(path, label),
                "text/html; charset=utf-8",
            )
        elif self.path == "/api/state":
            try:
                with open(self.status_path, encoding="utf-8") as f:
                    st = json.load(f)
            except Exception:
                st = {"text": "no status yet", "updated": "-"}
            chat = [{"who": "me", **m} for m in read_jsonl(self.inbox_path)] + \
                   [{"who": "claude", **m} for m in read_jsonl(self.outbox_path)]
            chat.sort(key=lambda m: m.get("ts", ""), reverse=True)
            self._send(200, json.dumps({
                "status_text": st.get("text", ""),
                "updated": st.get("updated", "-"),
                "chat": chat[:50],
                "lablog": list(reversed(read_jsonl(self.lablog_path)))[:200],
            }))
        elif self.path == "/sartor-report.html":
            p = os.path.join(DIR, "..", "docs", "sartor-report.html")
            self._send(200, open(p).read(), "text/html; charset=utf-8")
        elif self.path == "/report":
            try:
                import markdown
                with open(self.report_path, encoding="utf-8") as f:
                    report = f.read()
                html = markdown.markdown(report, extensions=["tables", "fenced_code"])
            except Exception as e:
                with open(self.report_path, encoding="utf-8") as f:
                    report = f.read()
                html = "<pre>" + report.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
            self._send(200, html, "text/html; charset=utf-8")
        else:
            self._send(404, "{}")

    def do_POST(self):
        if self.path == "/codex/prompt":
            return self._codex_prompt()
        if self.path != "/prompt":
            return self._send(404, "{}")
        try:
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(n))
            text = str(d.get("text", ""))[:20000].strip()
            if not text:
                return self._send(400, '{"err":"empty"}')
            rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "text": text}
            with open(self.inbox_path, "a") as f:
                f.write(json.dumps(rec) + "\n")
            self._send(200, '{"ok":true}')
        except Exception as e:
            self._send(500, json.dumps({"err": str(e)}))

    def _codex_prompt(self):
        if not self._codex_authorized():
            return self._send_json(401, {"err": "unauthorized"})
        try:
            size = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            return self._send_json(400, {"err": "invalid_content_length"})
        if size <= 0:
            return self._send_json(400, {"err": "empty_body"})
        if size > CODEX_REQUEST_MAX_BYTES:
            return self._send_json(413, {"err": "body_too_large"})
        try:
            payload = json.loads(self.rfile.read(size))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._send_json(400, {"err": "invalid_json"})
        if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
            return self._send_json(400, {"err": "invalid_text"})
        text = payload["text"].strip()
        if not text:
            return self._send_json(400, {"err": "empty"})
        if len(text) > CODEX_PROMPT_MAX_CHARS:
            return self._send_json(413, {"err": "text_too_long"})
        record = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "text": text}
        try:
            os.makedirs(os.path.dirname(self.codex_inbox_path), exist_ok=True)
            with open(self.codex_inbox_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            return self._send_json(500, {"err": "write_failed"})
        self._send_json(200, {"ok": True})

def handler_for_roots(
    bridge_root=DIR, codex_root=CODEX_ROOT, codex_prompt_token_path=None
):
    class RootedHandler(H):
        pass

    RootedHandler.inbox_path = os.path.join(bridge_root, "inbox.jsonl")
    RootedHandler.outbox_path = os.path.join(bridge_root, "outbox.jsonl")
    RootedHandler.status_path = os.path.join(bridge_root, "status.json")
    RootedHandler.lablog_path = os.path.join(bridge_root, "lablog.jsonl")
    RootedHandler.report_path = os.path.abspath(
        os.path.join(bridge_root, "..", "docs", "REPORT.md")
    )
    RootedHandler.codex_index_path = os.path.join(codex_root, "dashboard", "index.html")
    RootedHandler.codex_status_path = os.path.join(codex_root, "dashboard", "status.json")
    RootedHandler.codex_inbox_path = os.path.join(codex_root, "dashboard", "inbox.jsonl")
    RootedHandler.codex_outbox_path = os.path.join(codex_root, "dashboard", "outbox.jsonl")
    RootedHandler.codex_prompt_token_path = codex_prompt_token_path or os.path.join(
        codex_root, "dashboard", "prompt-token"
    )
    RootedHandler.codex_monitor_heartbeat_path = os.path.join(
        codex_root, "dashboard", ".monitor-heartbeat"
    )
    RootedHandler.codex_summary_path = os.path.join(
        codex_root, "experiments", "qwen3-8b", "summary-v0.json"
    )
    RootedHandler.codex_validation_result_path = os.path.join(
        codex_root, "validation", "results", "qwen3-0.6b-int4-sweep-v1.json"
    )
    RootedHandler.codex_report_path = os.path.join(
        codex_root, "experiments", "qwen3-8b", "README.md"
    )
    RootedHandler.codex_validation_path = os.path.join(codex_root, "validation", "README.md")
    RootedHandler.codex_overnight_path = os.path.join(
        codex_root, "docs", "OVERNIGHT_REPORT_2026-07-12.md"
    )
    RootedHandler.codex_glm_path = os.path.join(codex_root, "docs", "GLM_CO_DESIGN.md")
    RootedHandler.codex_business_path = os.path.join(
        codex_root, "docs", "BUSINESS_VALIDATION.md"
    )
    RootedHandler.codex_simulators_path = os.path.join(
        codex_root, "docs", "SIMULATOR_LANDSCAPE.md"
    )
    RootedHandler.codex_decisions_path = os.path.join(
        codex_root, "docs", "OPTIMIZATION_DECISIONS.md"
    )
    RootedHandler.codex_hardware_path = os.path.join(
        codex_root, "docs", "CUSTOM_HARDWARE_FEASIBILITY.md"
    )
    return RootedHandler

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8710), H).serve_forever()
