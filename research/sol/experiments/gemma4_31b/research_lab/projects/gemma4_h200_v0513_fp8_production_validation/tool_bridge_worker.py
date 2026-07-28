#!/usr/bin/env python3
"""Final consumer-gate worker; no benchmark or NLL requests are issued here."""
from __future__ import annotations

import argparse
import ast
import hashlib
import http.client
import json
import os
import pathlib
import re
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
MODEL = "google/gemma-4-31B-it"
ROOT = pathlib.Path("/home/glmrunner/gemma-v0513-quality-recovery")
UPSTREAM_PORT = 30000
BRIDGE_PORT = 31000


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def split_top(text: str, separator: str = ",") -> list[str]:
    result, start, depth, quote, escaped = [], 0, 0, False, False
    for i, ch in enumerate(text):
        if quote:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == '"': quote = False
        elif ch == '"': quote = True
        elif ch in "[{": depth += 1
        elif ch in "]}": depth -= 1
        elif ch == separator and depth == 0:
            result.append(text[start:i]); start = i + 1
    result.append(text[start:])
    return [x.strip() for x in result if x.strip()]


def parse_value(value: str) -> object:
    value = value.strip().replace('<|"|>', '"')
    if not value: return {}
    try: return json.loads(value)
    except Exception: pass
    if value.startswith("{") and value.endswith("}"):
        return parse_object(value[1:-1])
    if value.startswith("[") and value.endswith("]"):
        return [parse_value(x) for x in split_top(value[1:-1])]
    if (value.startswith('"') and value.endswith('"')):
        try: return json.loads(value)
        except Exception: return value[1:-1]
    if value in {"true", "false", "null"}: return {"true": True, "false": False, "null": None}[value]
    try: return int(value)
    except ValueError: pass
    try: return float(value)
    except ValueError: return value


def parse_object(text: str) -> dict[str, object]:
    out: dict[str, object] = {}
    for part in split_top(text):
        key, sep, value = part.partition(":")
        if not sep: continue
        key = key.strip().replace('<|"|>', '"').strip('"')
        out[key] = parse_value(value)
    return out


def parse_gemma_calls(content: object) -> list[dict[str, object]]:
    if not isinstance(content, str): return []
    text = content.replace('<|tool_response>', '')
    calls = []
    for match in re.finditer(r"<\|tool_call\>call:(\w+)\{(.*?)\}<tool_call\|>", text, re.S):
        name, arguments = match.group(1), parse_object(match.group(2))
        calls.append({"id": f"call_{len(calls)}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)}})
    if calls: return calls
    # The feature sentinel may be rendered as a JSON list rather than token grammar.
    try:
        items = json.loads(content)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("name"), str):
                    args = item.get("parameters", item.get("arguments", {}))
                    calls.append({"id": f"call_{len(calls)}", "type": "function", "function": {"name": item["name"], "arguments": json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)}})
    except Exception: pass
    return calls


def normalize_response(response: dict) -> dict:
    result = json.loads(json.dumps(response))
    for choice in result.get("choices", []):
        message = choice.get("message") or {}
        if message.get("tool_calls"):
            continue
        calls = parse_gemma_calls(message.get("content"))
        if calls:
            message["tool_calls"] = calls; message["content"] = None
            choice["finish_reason"] = "tool_calls"
    return result


def post(port: int, payload: dict) -> dict:
    body = canonical(payload)
    request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


class BridgeHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0")); raw = self.rfile.read(length)
        conn = http.client.HTTPConnection("127.0.0.1", UPSTREAM_PORT, timeout=180)
        conn.request("POST", self.path, raw, {"Content-Type": "application/json"})
        upstream = conn.getresponse(); data = upstream.read(); conn.close()
        try: output = normalize_response(json.loads(data))
        except Exception: output = json.loads(data)
        encoded = json.dumps(output, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(upstream.status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
    def log_message(self, *_args: object) -> None: pass


def wait_ready() -> None:
    for _ in range(180):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{UPSTREAM_PORT}/v1/models", timeout=5) as response:
                if MODEL in response.read().decode(errors="replace"): return
        except Exception: pass
        time.sleep(5)
    raise RuntimeError("server_not_ready")


def start_arm(arm: str, native_parser: bool) -> tuple[str, subprocess.Popen, ThreadingHTTPServer]:
    name = f"gemma4-tool-gate-{arm}"
    args = ["--model-path", "/work/checkpoint", "--tokenizer-path", "/work/checkpoint", "--served-model-name", MODEL, "--dtype", "bfloat16", "--tp-size", "1", "--kv-cache-dtype", "fp8_e5m2", "--host", "0.0.0.0", "--port", str(UPSTREAM_PORT), "--context-length", "5000", "--max-running-requests", "8", "--mem-fraction-static", "0.85", "--skip-server-warmup", "--enable-dynamic-chunking", "--chunked-prefill-size", "2048", "--enable-fused-qk-norm-rope", "--cuda-graph-max-bs", "8", "--prefill-attention-backend", "triton", "--decode-attention-backend", "triton", "--page-size", "1", "--num-continuous-decode-steps", "1", "--triton-attention-num-kv-splits", "8"]
    if arm == "fp8": args += ["--quantization", "fp8"]; entry = ["python3", "/work/quality-input/proven_v0513_endpoint_entrypoint.py"]
    else: entry = ["python3", "-m", "sglang.launch_server"]
    if native_parser: args += ["--tool-call-parser", "gemma4"]
    env = ["-e", f"FP8_MODULE_AUDIT=/work/quality-artifacts/tool-bridge-run/{arm}-fp8-modules.jsonl", "-e", f"FP8_CONSUMER_AUDIT=/work/quality-artifacts/tool-bridge-run/{arm}-fp8-consumers.jsonl", "-e", f"FP8_RUNTIME_AUDIT=/work/quality-artifacts/tool-bridge-run/{arm}-fp8-runtime.json"]
    command = ["sudo", "docker", "run", "-d", "--name", name, "--gpus", "all", "--ipc=host", "--network", "host", "-v", f"{ROOT}:/work", *env, IMAGE, *entry, *args]
    launched = subprocess.run(command, capture_output=True, text=True, check=False)
    if launched.returncode: raise RuntimeError(f"server_start_{arm}:{launched.stderr[-1000:]}")
    wait_ready()
    return name, None, None


def _serve() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", BRIDGE_PORT), BridgeHandler); server.serve_forever()


def stop(name: str, bridge: ThreadingHTTPServer | None, proxy: subprocess.Popen | None) -> None:
    if proxy: proxy.terminate(); proxy.wait(timeout=20)
    if bridge:
        bridge.shutdown(); bridge.server_close()
    subprocess.run(["sudo", "docker", "rm", "-f", name], capture_output=True, check=False)


def sentinel_payload(multi: bool) -> dict:
    tools = [{"type": "function", "function": {"name": "lookup_user", "description": "Look up a user by id.", "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}}}, {"type": "function", "function": {"name": "get_user_details", "description": "Get details for a user.", "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}}}]
    prompt = "Call lookup_user for user_id demo_user." if not multi else "Call lookup_user for user_id demo_user, then call get_user_details for user_id demo_user. Use both tools in that order."
    return {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "tools": tools, "tool_choice": "required", "temperature": 0, "max_tokens": 128}


def validate_response(response: dict, expected: list[tuple[str, dict]]) -> dict:
    choice = (response.get("choices") or [{}])[0]; message = choice.get("message") or {}; calls = message.get("tool_calls") or []
    observed = []
    for call in calls:
        fn = call.get("function") or {}; 
        try: args = json.loads(fn.get("arguments", "{}"))
        except Exception: args = None
        observed.append((fn.get("name"), args))
    usage = response.get("usage") or {}; valid_usage = all(isinstance(usage.get(k), int) and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
    return {"pass": observed == expected and choice.get("finish_reason") == "tool_calls" and valid_usage and message.get("content") is None, "observed": observed, "expected": expected, "finish_reason": choice.get("finish_reason"), "usage": usage, "raw_sha256": sha_bytes(canonical(response))}


def rescore_existing(root: pathlib.Path, parser_hash: str) -> dict:
    binding = json.loads((ROOT / "quality-input" / "tool_bridge_bindings.json").read_text())
    requests = {row["case_id"]: row for row in (json.loads(line) for line in (ROOT / "quality-input" / "taubench_requests.jsonl").read_text().splitlines())}
    result = {}
    outdir = root / "rescore"; outdir.mkdir(exist_ok=True)
    for arm in ("bf16", "fp8"):
        source = ROOT / "quality-artifacts" / "run" / "captures" / f"{arm}-tau.jsonl"
        source_hash = sha_bytes(source.read_bytes())
        expected_hash = binding[f"{arm}_tau_raw_sha256"]
        if source_hash != expected_hash: raise RuntimeError(f"raw_hash_mismatch_{arm}")
        rows = []; passed = 0
        for line in source.read_text().splitlines():
            row = json.loads(line); normalized = normalize_response(row["raw_response"]); msg = ((normalized.get("choices") or [{}])[0].get("message") or {})
            observed = []
            for call in msg.get("tool_calls") or []:
                fn = call.get("function") or {}
                try: arguments = json.loads(fn.get("arguments", "{}"))
                except Exception: arguments = None
                observed.append({"name": fn.get("name"), "arguments": arguments})
            expected = requests[row["case_id"]].get("expected_actions", [])
            ok = observed == expected; passed += int(ok)
            rows.append({"case_id": row["case_id"], "source_raw_response_sha256": row["raw_response_bytes_sha256"], "normalized_response": normalized, "observed_actions": observed, "expected_actions": expected, "pass": ok, "parser_sha256": parser_hash})
        (outdir / f"{arm}.jsonl").write_text("\n".join(json.dumps(x, sort_keys=True, ensure_ascii=False) for x in rows) + "\n")
        result[arm] = {"count": len(rows), "task_success": passed / len(rows), "source_sha256": source_hash, "normalized_sha256": sha_bytes((outdir / f"{arm}.jsonl").read_bytes()), "parser_sha256": parser_hash}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--artifact-root", type=pathlib.Path, required=True); args = parser.parse_args()
    root = args.artifact_root; root.mkdir(parents=True, exist_ok=True); (root / "sentinels").mkdir(exist_ok=True)
    # Probe the exact image before selecting the bridge; stdout is retained as evidence.
    probe = subprocess.run(["sudo", "docker", "run", "--rm", "--entrypoint", "python3", IMAGE, "-c", "import sglang; print(sglang.__version__); import sglang.srt.function_call.function_call_parser as p; print(p.__file__); print([x for x in dir(p) if 'Parser' in x or 'PARSER' in x])"], capture_output=True, text=True, check=False)
    choices = subprocess.run(["sudo", "docker", "run", "--rm", "--entrypoint", "python3", IMAGE, "-m", "sglang.launch_server", "--help"], capture_output=True, text=True, check=False)
    (root / "parser-probe.stdout").write_text(probe.stdout + "\n--- launch_server_help ---\n" + choices.stdout); (root / "parser-probe.stderr").write_text(probe.stderr + "\n--- launch_server_help_stderr ---\n" + choices.stderr)
    parser_mode = "bridge_gemma_schema_v1"
    native_parser = "gemma4" in choices.stdout
    if native_parser: parser_mode = "native_gemma4_with_schema_rescore_v1"
    parser_bytes = pathlib.Path(__file__).read_bytes(); parser_hash = sha_bytes(parser_bytes)
    expected = {"single": [("lookup_user", {"user_id": "demo_user"})], "multi": [("lookup_user", {"user_id": "demo_user"}), ("get_user_details", {"user_id": "demo_user"})]}
    (root / "INVOCATION_STATE.json").write_text(json.dumps({"bf16_scientific_started": False, "fp8_scientific_started": False}, indent=2) + "\n")
    arms = {}
    for arm in ("bf16", "fp8"):
        name = None; bridge = None; proxy = None
        try:
            marker = json.loads((root / "INVOCATION_STATE.json").read_text()); marker[f"{arm}_scientific_started"] = True; (root / "INVOCATION_STATE.json").write_text(json.dumps(marker, indent=2) + "\n")
            name, _unused, bridge = start_arm(arm, native_parser)
            bridge = ThreadingHTTPServer(("0.0.0.0", BRIDGE_PORT), BridgeHandler)
            threading.Thread(target=bridge.serve_forever, daemon=True).start()
            rows = []
            for kind in ("single", "multi"):
                raw = post(BRIDGE_PORT, sentinel_payload(kind == "multi")); normalized = normalize_response(raw); check = validate_response(normalized, expected[kind]); rows.append({"kind": kind, "request": sentinel_payload(kind == "multi"), "response": raw, "normalized": normalized, "check": check})
            arms[arm] = {"parser_sha256": parser_hash, "parser_mode": parser_mode, "sentinels": rows}
        finally:
            if name: stop(name, bridge, proxy)
    atomic = {"schema_version": 1, "parser_mode": parser_mode, "parser_sha256": parser_hash, "image": IMAGE, "checkpoint_schema_sha256": sha_bytes((ROOT / "checkpoint" / "tokenizer_config.json").read_bytes()), "image_probe": {"returncode": probe.returncode, "stdout_sha256": sha_bytes((probe.stdout + choices.stdout).encode()), "stderr_sha256": sha_bytes((probe.stderr + choices.stderr).encode()), "native_choices_inspected": "tool-call-parser" in choices.stdout or "tool-call-parser" in choices.stderr}, "arms": arms, "parser_byte_identical": arms["bf16"]["parser_sha256"] == arms["fp8"]["parser_sha256"], "gate_pass": all(x["sentinels"][i]["check"]["pass"] for x in arms.values() for i in (0, 1))}
    if atomic["gate_pass"]:
        atomic["rescore"] = rescore_existing(root, parser_hash)
    (root / "SENTINEL_TERMINAL.json").write_text(json.dumps(atomic, indent=2, sort_keys=True) + "\n")
    return 0 if atomic["gate_pass"] else 1


if __name__ == "__main__" and __name__ != "bridge-only": raise SystemExit(main())
