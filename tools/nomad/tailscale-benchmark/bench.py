import argparse
import concurrent.futures
import http.client
import itertools
import json
import ssl
import statistics
import time
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Compare a private Linux-interface route with a public HTTPS proxy using synthetic traffic."
)
parser.add_argument("--private-host", required=True)
parser.add_argument("--public-host", required=True)
parser.add_argument("--token-file", required=True)
parser.add_argument("--label", default="synthetic-transport")
args = parser.parse_args()
GPU = args.private_host
PUBLIC = args.public_host
LABEL = args.label
TOKEN = Path(args.token_file).read_text().strip()


def conn(route):
    if route == "tailscale":
        return http.client.HTTPConnection(GPU, 8888, timeout=30)
    return http.client.HTTPSConnection(
        PUBLIC, 443, timeout=30, context=ssl.create_default_context()
    )


HEAD = {"Authorization": "Bearer " + TOKEN}


def req(c, path="/healthz", body=None, auth=True):
    start = time.perf_counter()
    c.request(
        "POST" if body is not None else "GET",
        path,
        body=body,
        headers=HEAD if auth else {},
    )
    r = c.getresponse()
    data = r.read()
    ms = (time.perf_counter() - start) * 1000
    return r.status, data, ms


def summary(a):
    a = sorted(a)
    return {
        "n": len(a),
        "p50_ms": statistics.median(a),
        "p95_ms": a[min(len(a) - 1, int(0.95 * (len(a) - 1)))],
        "p99_ms": a[min(len(a) - 1, int(0.99 * (len(a) - 1)))],
    }


results = {"label": LABEL, "synthetic": True, "routes": {}}
clients = {x: conn(x) for x in ["public", "tailscale"]}
for route, c in clients.items():
    status, body, ms = req(c)
    assert status == 200 and json.loads(body)["ok"]
    assert req(c, auth=False)[0] == 401
    results["routes"][route] = {
        "first_request_ms": ms,
        "health_ms": [],
        "stream_runs": [],
        "download_mbps": [],
        "upload_mbps": [],
    }
# Alternate matched warm requests; deterministic order.
for i in range(120):
    for route in ["public", "tailscale"] if i % 2 == 0 else ["tailscale", "public"]:
        status, body, ms = req(clients[route])
        assert status == 200
        results["routes"][route]["health_ms"].append(ms)
for round in range(3):
    for route in ["public", "tailscale"] if round % 2 == 0 else ["tailscale", "public"]:
        c = clients[route]
        start = time.perf_counter()
        c.request("GET", "/stream", headers=HEAD)
        r = c.getresponse()
        assert r.status == 200
        times = []
        ids = []
        done = False
        while True:
            line = r.readline()
            if not line:
                break
            if line.startswith(b"data: "):
                if line.strip() == b"data: [DONE]":
                    done = True
                else:
                    ids.append(json.loads(line[6:])["sequence"])
                    times.append(time.perf_counter())
        assert done and ids == list(range(100))
        gaps = [(b - a) * 1000 for a, b in itertools.pairwise(times)]
        results["routes"][route]["stream_runs"].append(
            {
                "first_event_ms": (times[0] - start) * 1000,
                "duration_ms": (time.perf_counter() - start) * 1000,
                "gaps": summary(gaps),
                "max_gap_ms": max(gaps),
                "events": len(ids),
            }
        )
        status, b, ms = req(c, "/blob")
        assert status == 200 and len(b) == 16 * 1024 * 1024
        results["routes"][route]["download_mbps"].append(len(b) * 8 / ms / 1000)
        payload = b"x" * (8 * 1024 * 1024)
        status, b, ms = req(c, "/echo", payload)
        assert status == 200 and json.loads(b)["received"] == len(payload)
        results["routes"][route]["upload_mbps"].append(len(payload) * 8 / ms / 1000)
for route, client in clients.items():

    def one(_, route=route):
        c = conn(route)
        try:
            status, _body, ms = req(c)
            assert status == 200
            return ms
        finally:
            c.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        vals = list(pool.map(one, range(40)))
    results["routes"][route]["concurrency_20_health"] = summary(vals)
    # Cancel a stream and prove subsequent requests still succeed.
    c = conn(route)
    c.request("GET", "/stream", headers=HEAD)
    r = c.getresponse()
    r.readline()
    c.close()
    c = conn(route)
    assert req(c)[0] == 200
    c.close()
    results["routes"][route]["cancellation_recovery"] = True
    results["routes"][route]["health"] = summary(
        results["routes"][route].pop("health_ms")
    )
    client.close()
print(json.dumps(results, indent=2))
