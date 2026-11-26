"""Submit candidates to a persistent engine tier and wait for the result."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

PORTS = {"fast": 18110, "slow": 18120}


def _url(tier: str, path: str) -> str:
    return f"http://127.0.0.1:{PORTS[tier]}{path}"


def _get(tier: str, path: str, timeout: float = 30) -> dict:
    with urllib.request.urlopen(_url(tier, path), timeout=timeout) as response:
        return json.loads(response.read())


def submit(tier: str, source: str, agent: str, name: str, profile: bool) -> dict:
    body = json.dumps({"source": source, "agent": agent, "name": name, "profile": profile}).encode()
    request = urllib.request.Request(_url(tier, "/submit"), data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def wait(tier: str, job_id: str, timeout: float) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data = _get(tier, f"/result?id={job_id}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {"status": "lost", "job_id": job_id, "error": "the engine restarted and no longer knows this job; resubmit"}
            data = {"status": "unreachable", "error": str(exc)}
        except OSError as exc:
            data = {"status": "unreachable", "error": str(exc)}
        if data.get("status") not in ("queued", "running", "unreachable"):
            return data
        time.sleep(2)
    return {"status": "client_timeout", "job_id": job_id}


def summarize(result: dict) -> dict:
    keep = (
        "job_id", "status", "speedup", "per_concurrency_speedup", "error", "correctness",
        "hot_reload_s", "check_s", "measure_s", "job_s", "queue_wait_s", "gpu_lock_wait_s", "profile", "traceback", "changed",
    )
    summary = {k: result[k] for k in keep if k in result}
    if "measurement" in result:
        summary["tps_per_user"] = {c: round(v["tps_per_user"], 2) for c, v in result["measurement"].items()}
        summary["spread"] = {c: round(v["spread"], 4) for c, v in result["measurement"].items()}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("submit")
    s.add_argument("--tier", choices=PORTS, required=True)
    s.add_argument("--file", required=True)
    s.add_argument("--agent", default="anon")
    s.add_argument("--name", default="")
    s.add_argument("--profile", action="store_true")
    s.add_argument("--timeout", type=float, default=3600)
    st = sub.add_parser("status")
    b = sub.add_parser("baseline")
    b.add_argument("--tier", choices=PORTS, required=True)
    r = sub.add_parser("reload-ext")
    r.add_argument("--tier", choices=PORTS, required=True)
    p = sub.add_parser("profile-baseline")
    p.add_argument("--tier", choices=PORTS, default="fast")
    args = parser.parse_args()
    if args.command == "submit":
        source = open(args.file).read()
        ticket = submit(args.tier, source, args.agent, args.name, args.profile)
        print(json.dumps({"submitted": ticket}), flush=True)
        result = wait(args.tier, ticket["job_id"], args.timeout)
        print(json.dumps(summarize(result.get("result") or result), indent=1))
    elif args.command == "status":
        out = {}
        for tier in PORTS:
            try:
                out[tier] = _get(tier, "/status")
            except OSError as exc:
                out[tier] = {"error": str(exc)}
        print(json.dumps(out, indent=1))
    elif args.command == "reload-ext":
        print(json.dumps(_get(args.tier, "/admin/reload_ext", timeout=300)))
    elif args.command == "baseline":
        print(json.dumps(_get(args.tier, "/baseline"), indent=1))
    else:
        print(json.dumps(_get(args.tier, "/profile_baseline", timeout=900), indent=1))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
