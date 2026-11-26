#!/usr/bin/env python3
"""MCP OAuth token for the private administrative listener.

The private listener is reached through a local port-forward, but its tokens
are issued for https://ops.gradiated.com/mcp. MCP clients that require the
OAuth resource to match the URL they connect to (Claude Code does) cannot log
in there, so they send this token as a header instead.

  private-token.py login    sign in through the browser and store the token
  private-token.py header   print {"Authorization": ...}, refreshing if needed

The token file is created with mode 0600 and never printed by `login`.
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ISSUER = "https://ops.gradiated.com"
RESOURCE = f"{ISSUER}/mcp"
SCOPE = "production:read"
STORE = Path(os.environ.get("GRADIATED_OPS_TOKEN_FILE", Path.home() / ".config/gradiated/ops-mcp-private-token.json"))


def post(path, body, form=True):
    data = urllib.parse.urlencode(body).encode() if form else json.dumps(body).encode()
    kind = "application/x-www-form-urlencoded" if form else "application/json"
    request = urllib.request.Request(ISSUER + path, data=data, headers={"Content-Type": kind})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def save(state):
    STORE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = STORE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STORE)


def keep(state, tokens):
    state.update(access_token=tokens["access_token"], expires_at=time.time() + int(tokens.get("expires_in", 3600)))
    if tokens.get("refresh_token"):
        state["refresh_token"] = tokens["refresh_token"]
    save(state)
    return state


def login():
    server = http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
    redirect = f"http://127.0.0.1:{server.server_port}/callback"
    client = post("/register", {"client_name": "Gradiated private ops token", "redirect_uris": [redirect],
                                "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
                                "token_endpoint_auth_method": "none"}, form=False)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    url = f"{ISSUER}/authorize?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client["client_id"], "redirect_uri": redirect, "scope": SCOPE,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "resource": RESOURCE})
    result = {}

    class Callback(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({k: v[0] for k, v in query.items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Signed in. You can close this tab.")

        def log_message(self, *args):
            pass

    server.RequestHandlerClass = Callback
    print(f"Opening the browser to sign in. If it does not open, visit:\n{url}", file=sys.stderr)
    webbrowser.open(url)
    while "code" not in result and "error" not in result:
        server.handle_request()
    if result.get("state") != state or "code" not in result:
        sys.exit(f"Sign-in failed: {result.get('error', 'state mismatch')}")
    tokens = post("/token", {"grant_type": "authorization_code", "code": result["code"], "redirect_uri": redirect,
                             "client_id": client["client_id"], "code_verifier": verifier, "resource": RESOURCE})
    keep({"client_id": client["client_id"]}, tokens)
    print(f"Token stored in {STORE}", file=sys.stderr)


def header():
    state = json.loads(STORE.read_text())
    if state["expires_at"] - time.time() < 120:
        tokens = post("/token", {"grant_type": "refresh_token", "refresh_token": state["refresh_token"],
                                 "client_id": state["client_id"], "resource": RESOURCE})
        state = keep(state, tokens)
    print(json.dumps({"Authorization": f"Bearer {state['access_token']}"}))


if __name__ == "__main__":
    {"login": login, "header": header}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
