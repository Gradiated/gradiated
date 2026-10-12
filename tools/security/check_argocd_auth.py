#!/usr/bin/env python3
"""Exercise the pinned Argo login gate with signed, synthetic OIDC identities."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "infra/environments/prod/us-east-1/kubernetes/platform/argocd-domain-gate.yaml"


def encoded(value):
    if not isinstance(value, bytes):
        value = json.dumps(value).encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def main():
    documents = list(yaml.safe_load_all(MANIFEST.read_text()))
    config = next(d for d in documents if d["kind"] == "ConfigMap")["data"]["oauth2-proxy.cfg"]
    image = next(d for d in documents if d["kind"] == "Deployment")["spec"]["template"]["spec"]["containers"][0]["image"]
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    jwk = {"kty": "RSA", "kid": "fixture", "use": "sig", "alg": "RS256",
           "n": encoded(numbers.n.to_bytes(256, "big")),
           "e": encoded(numbers.e.to_bytes(3, "big"))}
    codes = {}
    identity = {}
    upstream_hits = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_json(self, data):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/issuer/.well-known/openid-configuration":
                self.send_json({"issuer": issuer, "authorization_endpoint": issuer + "/authorize",
                                "token_endpoint": issuer + "/token", "jwks_uri": issuer + "/keys",
                                "response_types_supported": ["code"],
                                "subject_types_supported": ["public"],
                                "id_token_signing_alg_values_supported": ["RS256"],
                                "code_challenge_methods_supported": ["S256"]})
            elif path == "/issuer/keys":
                self.send_json({"keys": [jwk]})
            elif path == "/issuer/authorize":
                params = parse_qs(urlsplit(self.path).query)
                code = secrets.token_hex(12)
                codes[code] = {**identity, "nonce": params["nonce"][0]}
                self.send_response(302)
                self.send_header("Location", params["redirect_uri"][0] + "?" + urlencode({
                    "code": code, "state": params["state"][0]}))
                self.end_headers()
            else:
                upstream_hits.append(path)
                self.send_json({"upstream": "reached"})

        def do_POST(self):
            params = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
            claims = {"iss": issuer, "aud": "argocd-domain-gate", "sub": "fixture-user",
                      "iat": int(time.time()), "exp": int(time.time()) + 300,
                      **codes.pop(params["code"][0])}
            message = encoded({"alg": "RS256", "kid": "fixture"}) + "." + encoded(claims)
            token = message + "." + encoded(key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256()))
            self.send_json({"access_token": "fixture-access", "token_type": "Bearer",
                            "expires_in": 300, "id_token": token})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    issuer = f"http://127.0.0.1:{server.server_port}/issuer"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        proxy_port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{proxy_port}"
    container = "argocd-gate-fixture-" + secrets.token_hex(6)
    try:
        with tempfile.TemporaryDirectory(prefix="argocd-gate-fixture-") as directory:
            path = Path(directory) / "oauth2-proxy.cfg"
            path.write_text(config)
            subprocess.run(["docker", "run", "--rm", "-d", "--name", container,
                            "--network", "host", "--read-only", "--cap-drop", "ALL",
                            "--security-opt", "no-new-privileges",
                            "-v", f"{path}:/fixture.cfg:ro",
                            "-e", "OAUTH2_PROXY_CLIENT_SECRET=fixture-secret",
                            "-e", "OAUTH2_PROXY_COOKIE_SECRET=" + encoded(secrets.token_bytes(32)),
                            image, "--config=/fixture.cfg", "--http-address=127.0.0.1:" + str(proxy_port),
                            "--oidc-issuer-url=" + issuer,
                            "--redirect-url=" + origin + "/oauth2/callback",
                            "--upstream=" + issuer.replace("/issuer", "/"),
                            "--cookie-secure=false", "--cookie-name=fixture_gate",
                            "--whitelist-domain=127.0.0.1:*"], check=True,
                           capture_output=True, timeout=60)
            for _ in range(100):
                try:
                    if requests.get(origin + "/ready", timeout=1).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Fixture proxy did not become ready")
            for headers in [{}, {"X-Forwarded-Email": "staff@gradiated.com"},
                            {"Authorization": "Bearer fixture-forged-token"}]:
                upstream_hits.clear()
                response = requests.get(origin + "/api/v1/applications", headers=headers,
                                        allow_redirects=False, timeout=5)
                assert response.status_code == 302, response.status_code
                assert not upstream_hits, "Unauthenticated API request reached Argo"
            for email, verified, expected in [
                ("josh@gradiated.com", True, 200),
                ("new-staff@gradiated.com", True, 200),
                ("staff@posthog.com", True, 403),
                ("staff@gradiated.com.attacker.example", True, 403),
                ("staff@sub.gradiated.com", True, 403),
                ("staff@gradiated.com", False, 500),
            ]:
                identity.clear()
                identity.update(email=email, email_verified=verified)
                upstream_hits.clear()
                with requests.Session() as session:
                    response = session.get(origin + "/", timeout=10)
                assert response.status_code == expected, (email, verified, response.status_code)
                assert bool(upstream_hits) == (expected == 200), (email, upstream_hits)
            print("Signed OIDC login: Gradiated staff allowed; PostHog, suffix/subdomain tricks and unverified email blocked before upstream.")
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=30)
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
