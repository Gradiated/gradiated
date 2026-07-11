#!/usr/bin/env python3
"""Sartor bridge: progress dashboard + prompt inbox. Stdlib only.
GET /            dashboard (auto-refreshing)
GET /api/state   {status, chat}
POST /prompt     {text} -> appended to inbox.jsonl (picked up by Claude's monitor)
"""
import json, os, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIR = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(DIR, "inbox.jsonl")
OUTBOX = os.path.join(DIR, "outbox.jsonl")
STATUS = os.path.join(DIR, "status.json")
REPORT = os.path.join(DIR, "..", "docs", "REPORT.md")

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>sartor — live</title><style>
body{background:#0d1117;color:#e6edf3;font:15px/1.5 -apple-system,system-ui,sans-serif;max-width:780px;margin:0 auto;padding:16px}
h1{font-size:18px} h2{font-size:14px;color:#8b949e;margin:18px 0 6px;text-transform:uppercase;letter-spacing:.05em}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;margin:8px 0;white-space:pre-wrap;word-wrap:break-word}
.me{border-left:3px solid #d29922}.claude{border-left:3px solid #2f81f7}
.ts{color:#8b949e;font-size:12px}
textarea{width:100%;box-sizing:border-box;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:10px;font:inherit;min-height:70px}
button{background:#238636;color:#fff;border:0;border-radius:8px;padding:10px 18px;font:inherit;margin-top:6px;cursor:pointer}
#stat{color:#3fb950;font-size:13px}</style></head><body>
<h1>🚢 sartor — live progress <span id="stat"></span></h1>
<h2>send a prompt to Claude</h2>
<textarea id="t" placeholder="prompt…"></textarea><br>
<button onclick="send()">send</button>
<h2>status</h2><div class="card" id="status">loading…</div>
<h2>conversation</h2><div id="chat"></div>
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
    for line in open(p):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/state":
            try:
                st = json.load(open(STATUS))
            except Exception:
                st = {"text": "no status yet", "updated": "-"}
            chat = [{"who": "me", **m} for m in read_jsonl(INBOX)] + \
                   [{"who": "claude", **m} for m in read_jsonl(OUTBOX)]
            chat.sort(key=lambda m: m.get("ts", ""), reverse=True)
            self._send(200, json.dumps({
                "status_text": st.get("text", ""),
                "updated": st.get("updated", "-"),
                "chat": chat[:50],
            }))
        elif self.path == "/report":
            try:
                import markdown
                html = markdown.markdown(open(REPORT).read(), extensions=["tables", "fenced_code"])
            except Exception as e:
                html = "<pre>" + open(REPORT).read().replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
            self._send(200, html, "text/html; charset=utf-8")
        else:
            self._send(404, "{}")

    def do_POST(self):
        if self.path != "/prompt":
            return self._send(404, "{}")
        try:
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(n))
            text = str(d.get("text", ""))[:20000].strip()
            if not text:
                return self._send(400, '{"err":"empty"}')
            rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "text": text}
            with open(INBOX, "a") as f:
                f.write(json.dumps(rec) + "\n")
            self._send(200, '{"ok":true}')
        except Exception as e:
            self._send(500, json.dumps({"err": str(e)}))

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8710), H).serve_forever()
