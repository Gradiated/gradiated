"""Bounded native Kev ASGI adapter. One process/worker per visible GPU."""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import hmac
import json
import math
from pathlib import Path
import subprocess
import threading
import time

MODEL = "jaredpalmer/kev-9b"
REVISION = "2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c"
UPSTREAM_COMMIT = "f0ae8fb9af5762254974dcdba8c82cbf48587b2e"
BASE = "Qwen/Qwen3.5-9B-Base"
BASE_REVISION = "68c46c4b3498877f3ef123c856ecfde50c39f404"
MAX_BODY = 1024 * 1024  # Deliberately below the gateway's 32 MiB cap.
MAX_TOKENS = 8192
MAX_DEPTH = 32


@dataclasses.dataclass(frozen=True)
class Release:
    """The exact model release and placement an adapter process serves."""

    model: str = MODEL
    revision: str = REVISION
    base: str = BASE
    # None asserts the checkpoint declares no base revision, which small
    # upstream checkpoints do not; the production release pins one.
    base_revision: str | None = BASE_REVISION
    upstream_commit: str = UPSTREAM_COMMIT
    device: str = "cuda"
    dtype: str = "bfloat16"
    allow_unpinned: bool = False


class InvalidRequest(Exception):
    pass


def validate(data, model=MODEL):
    """Validate without coercion; bound nested JSON before upstream rendering."""
    if not isinstance(data, dict) or set(data) - {"model", "state", "questions", "priority"}:
        raise InvalidRequest("unknown request fields or invalid object")
    if data.get("model") != model or "state" not in data:
        raise InvalidRequest(f"model must be {model} and state is required")
    if not isinstance(data["state"], (str, dict, list)):
        raise InvalidRequest("state must be a string, object, or array")
    priority = data.get("priority", 0)
    if type(priority) is not int or priority not in (-10, 0, 10):
        raise InvalidRequest("priority must be an integer: -10, 0, or 10")
    questions = data.get("questions")
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 64:
        raise InvalidRequest("questions must contain 1..64 entries")
    for key, question in questions.items():
        if not key or len(key) > 200 or not isinstance(question, dict):
            raise InvalidRequest("invalid question")
        if set(question) - {"type", "instructions", "criteria"} or "instructions" not in question:
            raise InvalidRequest("unknown question fields or missing instructions")
        kind, criteria = question.get("type"), question.get("criteria")
        if kind == "choice":
            valid = isinstance(criteria, dict) and 1 <= len(criteria) <= 255
        elif kind == "score":
            valid = isinstance(criteria, list) and 2 <= len(criteria) <= 255
        elif kind == "noul":
            valid = criteria is None or (isinstance(criteria, dict) and not set(criteria) - {"false", "true"})
        else:
            valid = False
        if not valid:
            raise InvalidRequest("invalid question type or criteria")
    stack = [(data, 0)]
    while stack:
        value, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise InvalidRequest("JSON nesting exceeds 32 levels")
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, float) and not math.isfinite(value):
            raise InvalidRequest("JSON numbers must be finite")
    return {key: value for key, value in data.items() if key != "priority"}


class Engine:
    """Instrument the pinned Server's model/cache; keep upstream hybrid operations."""

    def __init__(self, server, api, sync, model=MODEL):
        self.server, self.api, self.sync = server, api, sync
        self.model = model

    def answer(self, data):
        server = self.server
        req = self.api.SystemOneRequest.model_validate(data)
        rec, meta = self.api.to_record(req)
        try:
            enc = server.model.encode(server.tok, rec, max_state=MAX_TOKENS,
                                      max_branch=MAX_TOKENS, strict=True)
        except ValueError:
            raise InvalidRequest("state or state-plus-question exceeds 8192 tokens") from None
        length = len(enc["ids"])
        # Bound both packed attention and hybrid Q x padded-row allocations.
        segments = enc["seg"]
        state_tokens = segments.count(0)
        longest_branch = max(segments.count(i) for i in range(1, len(meta) + 1))
        if length > MAX_TOKENS or len(meta) * (state_tokens + longest_branch) > MAX_TOKENS:
            raise InvalidRequest("packed or padded model input exceeds 8192 tokens")
        key = (tuple(enc["ids"][:state_tokens]), bool(enc.get("option_isolation")))
        cache = server.prefix_cache
        eligible = state_tokens >= 384
        hit = eligible and key in cache
        with server.lock:
            started = time.perf_counter()
            try:
                self.sync(server.device)
                if hit:
                    # Remove before execution: a failing forward may mutate its KV.
                    prefix = cache.pop(key)
                    ps = server.model.probs_with_prefix(enc, prefix)
                elif eligible:
                    # Evict before allocation; never retain a fifth prefix.
                    if len(cache) >= 4:
                        cache.pop(next(iter(cache)))
                    ps, prefix = server.model.probs_and_prefix(enc)
                else:
                    ps = server.model.probs(enc)
                self.sync(server.device)
                probabilities = [p.tolist() for p in ps]
                if len(probabilities) != len(meta) or any(
                    len(p) != len(m["keys"]) or any(not math.isfinite(v) for v in p)
                    for p, m in zip(probabilities, meta)
                ):
                    raise RuntimeError("invalid model output")
                answers = self.api.to_answers(probabilities, meta)
                if eligible:
                    cache[key] = prefix
                    if hit:
                        server.prefix_hits += 1
                    else:
                        server.prefix_misses += 1
            except BaseException:
                cache.clear()  # No potentially damaged state survives a GPU error.
                # Thread completion must mean GPU completion, also on exceptions.
                self.sync(server.device)
                raise
        return {"model": self.model, "answers": answers,
                "usage": {"input_tokens": length,
                          "cached_input_tokens": state_tokens if hit else 0,
                          "output_tokens": 0},
                "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidRequest("duplicate JSON fields")
        result[key] = value
    return result


class App:
    """ASGI with pre-body admission, no inference queue, and bounded body reads."""

    def __init__(self, engine, token=None, model=MODEL):
        self.engine = engine
        self.model = model
        self.token_digest = hashlib.sha256(token).digest() if token is not None else None
        self.slot = threading.Lock()
        self.tasks = set()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    if self.tasks:
                        await asyncio.gather(*self.tasks, return_exceptions=True)
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        elif scope["type"] != "http":
            return
        headers = scope.get("headers", [])
        if self.token_digest is not None:
            values = [v for k, v in headers if k.lower() == b"authorization"]
            value = values[0] if len(values) == 1 else b""
            provided = value[7:] if value.startswith(b"Bearer ") else b""
            if not hmac.compare_digest(hashlib.sha256(provided).digest(), self.token_digest):
                return await self.respond(send, 401, "unauthorized")
        path, method = scope["path"], scope["method"]
        if path == "/health" and method == "GET":
            return await self.respond(send, 200, {"status": "ok", "model": self.model})
        if path == "/v1/models" and method == "GET":
            return await self.respond(send, 200, {"models": [{"id": self.model}]})
        if path != "/v1/systemone":
            return await self.respond(send, 404, "not found")
        if method != "POST":
            return await self.respond(send, 405, "method not allowed")
        if not self.slot.acquire(blocking=False):
            return await self.respond(send, 429, "runtime busy")
        transferred = False
        try:
            header_map = dict(headers)
            if header_map.get(b"content-type", b"").split(b";", 1)[0].strip() != b"application/json":
                return await self.respond(send, 415, "application/json required")
            try:
                declared = int(header_map.get(b"content-length", b"0"))
            except ValueError:
                return await self.respond(send, 400, "invalid content-length")
            if declared < 0 or declared > MAX_BODY:
                return await self.respond(send, 413, "body exceeds 1 MiB")
            body = bytearray()
            async with asyncio.timeout(15):
                while True:
                    event = await receive()
                    if event["type"] == "http.disconnect":
                        return
                    chunk = event.get("body", b"")
                    if len(body) + len(chunk) > MAX_BODY:
                        return await self.respond(send, 413, "body exceeds 1 MiB")
                    body.extend(chunk)
                    if not event.get("more_body", False):
                        break
            try:
                data = validate(json.loads(body, object_pairs_hook=_object), self.model)
            except (ValueError, RecursionError, InvalidRequest):
                return await self.respond(send, 422, "invalid request")
            # The worker owns release. Cancelling the HTTP task cannot free the GPU.
            task = asyncio.create_task(asyncio.to_thread(self.work, data))
            self.tasks.add(task)
            task.add_done_callback(self.finished)
            transferred = True
            try:
                result = await asyncio.shield(task)
            except InvalidRequest as exc:
                return await self.respond(send, 422, str(exc))
            except Exception:
                return await self.respond(send, 500, "inference failed")
            return await self.respond(send, 200, result)
        except TimeoutError:
            return await self.respond(send, 408, "body read timeout")
        finally:
            if not transferred:
                self.slot.release()

    def work(self, data):
        try:
            return self.engine.answer(data)
        finally:
            self.slot.release()

    def finished(self, task):
        self.tasks.discard(task)
        if not task.cancelled():
            task.exception()  # Consume failures after the HTTP caller goes away.

    @staticmethod
    async def respond(send, status, value):
        payload = value if isinstance(value, dict) else {"error": {"message": value}}
        body = json.dumps(payload, allow_nan=False).encode()
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        if status == 429:
            headers.append((b"retry-after", b"1"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def verify_source(root, commit, allow_unpinned):
    """Verify the checkout matches the pinned upstream commit and is clean.

    An installed copy has no checkout to verify, so the pin has to be enforced where
    the image is built instead. That is a real weakening, so it must be asked for.
    """
    if not (root / ".git").is_dir():
        if not allow_unpinned:
            raise RuntimeError(
                "no Kev source checkout to verify; the caller must pin the source at "
                "build time and pass --allow-unpinned-source"
            )
        return
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--", "kev"], text=True)
    if head != commit or dirty:
        raise RuntimeError("requires the clean pinned Kev source checkout")


def load_engine(release=None):
    release = release or Release()
    import kev
    root = Path(kev.__file__).resolve().parent.parent
    verify_source(root, release.upstream_commit, release.allow_unpinned)
    import torch
    from kev import api
    from kev.checkpoint import Checkpoint, LoadOptions
    from kev.device import sync
    from kev.serve import Server

    if release.device == "cuda" and (
        not torch.cuda.is_available() or torch.cuda.device_count() != 1
    ):
        raise RuntimeError("expose exactly one CUDA GPU per adapter process")
    checkpoint = Checkpoint(f"{release.model}@{release.revision}")
    if checkpoint.meta.base != release.base or checkpoint.meta.base_revision != release.base_revision:
        raise RuntimeError("unexpected base model release")
    # Pinned kev.device.sync recognizes "cuda", not "cuda:0". Visibility pins it.
    dtype = getattr(torch, release.dtype)
    tokenizer, model = checkpoint.load(release.device, LoadOptions(dtype=dtype))
    return Engine(Server(checkpoint, tokenizer, model, release.device), api, sync, release.model)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8009)
    parser.add_argument("--token-file", type=Path)
    # Defaults are the pinned production release; overriding one requires naming the
    # whole release, so a partial override cannot silently weaken the pin.
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--revision", default=REVISION)
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--base-revision", default=BASE_REVISION)
    parser.add_argument("--upstream-commit", default=UPSTREAM_COMMIT)
    parser.add_argument("--device", default="cuda", choices=("cuda", "cpu"))
    parser.add_argument("--dtype", default="bfloat16", choices=("bfloat16", "float32"))
    parser.add_argument("--allow-unpinned-source", action="store_true")
    args = parser.parse_args()
    release = Release(
        model=args.model,
        revision=args.revision,
        base=args.base,
        base_revision=args.base_revision or None,
        upstream_commit=args.upstream_commit,
        device=args.device,
        dtype=args.dtype,
        allow_unpinned=args.allow_unpinned_source,
    )
    token = None
    if args.token_file:
        token = args.token_file.read_bytes().rstrip(b"\r\n")
        if not 16 <= len(token) <= 4096 or any(c < 33 or c > 126 for c in token):
            parser.error("token file must contain 16..4096 printable non-space ASCII bytes")
    import uvicorn
    uvicorn.run(App(load_engine(release), token, release.model),
                host=args.host, port=args.port,
                workers=1, limit_concurrency=64, timeout_keep_alive=5, access_log=False)


if __name__ == "__main__":
    main()
