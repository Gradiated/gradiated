"""Bounded native Kev ASGI adapter. One process/worker per visible GPU."""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import hmac
import importlib.metadata
import importlib.util
import json
import logging
import math
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Literal

log = logging.getLogger("kev.adapter")

MODEL = "jaredpalmer/kev-9b"
REVISION = "2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c"
UPSTREAM_COMMIT = "f0ae8fb9af5762254974dcdba8c82cbf48587b2e"
BASE = "Qwen/Qwen3.5-9B-Base"
BASE_REVISION = "68c46c4b3498877f3ef123c856ecfde50c39f404"
MAX_BODY = 1024 * 1024  # Deliberately below the gateway's 32 MiB cap.
BODY_READ_TIMEOUT_SECONDS = 15
MAX_TOKENS = 8192
MAX_DEPTH = 32
MAX_QUESTIONS = 1024  # The gateway's bound; token limits stop large requests well before it.
MAX_QUESTION_KEY_LENGTH = 200
MAX_CRITERIA = 255
PRIORITIES = (-10, 0, 10)
PREFIX_CACHE_MIN_TOKENS = 384
PREFIX_CACHE_ENTRIES = 4
BODY_TOO_LARGE = f"body exceeds {MAX_BODY // (1024 * 1024)} MiB"


@dataclasses.dataclass(frozen=True)
class Release:
    model: str = MODEL
    revision: str = REVISION
    base: str = BASE
    # None asserts the checkpoint declares no base revision, which small
    # upstream checkpoints do not; the production release pins one.
    base_revision: str | None = BASE_REVISION
    upstream_commit: str = UPSTREAM_COMMIT
    device: Literal["cuda", "cpu"] = "cuda"
    dtype: Literal["bfloat16", "float32"] = "bfloat16"
    allow_unpinned: bool = False


class InvalidRequest(Exception):
    pass


class InvalidModelOutput(RuntimeError):
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
    if type(priority) is not int or priority not in PRIORITIES:
        raise InvalidRequest(f"priority must be an integer in {PRIORITIES}")
    questions = data.get("questions")
    if not isinstance(questions, dict) or not 1 <= len(questions) <= MAX_QUESTIONS:
        raise InvalidRequest(f"questions must contain 1..{MAX_QUESTIONS} entries")
    for key, question in questions.items():
        if not key or len(key) > MAX_QUESTION_KEY_LENGTH or not isinstance(question, dict):
            raise InvalidRequest("invalid question")
        # Instructions are optional, as in TypeSafe's API (its SDK omits them for criteria-only questions).
        if set(question) - {"type", "instructions", "criteria"}:
            raise InvalidRequest("unknown question fields")
        kind, criteria = question.get("type"), question.get("criteria")
        if kind == "choice":
            valid = isinstance(criteria, dict) and 1 <= len(criteria) <= MAX_CRITERIA
        elif kind == "score":
            valid = isinstance(criteria, list) and 1 <= len(criteria) <= MAX_CRITERIA
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
            raise InvalidRequest(f"JSON nesting exceeds {MAX_DEPTH} levels")
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
        # Kev's request record needs instruction text; a question without instructions is asked with none. Other
        # runtimes sharing this App see the request as sent.
        questions = {key: {"instructions": "", **q} for key, q in data["questions"].items()}
        try:
            req = self.api.SystemOneRequest.model_validate({**data, "questions": questions})
            rec, meta = self.api.to_record(req)
        except ValueError:
            raise InvalidRequest("invalid request") from None

        try:
            enc = server.model.encode(server.tok, rec, max_state=MAX_TOKENS,
                                      max_branch=MAX_TOKENS, strict=True)
        except ValueError:
            raise InvalidRequest(f"state or state-plus-question exceeds {MAX_TOKENS} tokens") from None
        length = len(enc["ids"])
        # Bound both packed attention and hybrid Q x padded-row allocations.
        segments = enc["seg"]
        state_tokens = segments.count(0)
        longest_branch = max(segments.count(i) for i in range(1, len(meta) + 1))
        if length > MAX_TOKENS or len(meta) * (state_tokens + longest_branch) > MAX_TOKENS:
            raise InvalidRequest(f"packed or padded model input exceeds {MAX_TOKENS} tokens")
        key = (tuple(enc["ids"][:state_tokens]), bool(enc.get("option_isolation")))
        cache = server.prefix_cache
        eligible = state_tokens >= PREFIX_CACHE_MIN_TOKENS
        with server.lock:
            hit = eligible and key in cache
            started = time.perf_counter()
            try:
                self.sync(server.device)
                if hit:
                    # Remove before execution: a failing forward may mutate its KV.
                    prefix = cache.pop(key)
                    ps = server.model.probs_with_prefix(enc, prefix)
                elif eligible:
                    # Evict before allocation; never exceed the entry bound.
                    if len(cache) >= PREFIX_CACHE_ENTRIES:
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
                    raise InvalidModelOutput("invalid model output")
                answers = self.api.to_answers(probabilities, meta)
                if eligible:
                    cache[key] = prefix
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


class HttpError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class App:
    """ASGI with pre-body admission, no inference queue, and bounded body reads."""

    def __init__(self, engine, token=None):
        self.engine = engine
        self.token_digest = hashlib.sha256(token).digest() if token is not None else None
        self.slot = threading.Lock()
        self.tasks = set()
        self.busy_rejections = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self._lifespan(receive, send)
        if scope["type"] != "http":
            return

        headers = scope.get("headers", [])
        path, method = scope["path"], scope["method"]
        if not self._authorized(headers):
            return await respond_error(send, 401, "unauthorized")
        if path == "/health" and method == "GET":
            return await respond_json(send, 200, {"status": "ok", "model": self.engine.model})
        if path == "/v1/models" and method == "GET":
            return await respond_json(send, 200, {"models": [{"id": self.engine.model}]})
        if path == "/metrics" and method == "GET":
            return await respond_text(send, 200, self._metrics())
        if path != "/v1/systemone":
            return await respond_error(send, 404, "not found")
        if method != "POST":
            return await respond_error(send, 405, "method not allowed")
        if not self.slot.acquire(blocking=False):
            self.busy_rejections += 1
            return await respond_error(send, 429, "runtime busy")

        transferred = False
        try:
            data = await self._read_json_body(headers, receive)
            if data is not None:
                transferred = True
                await self._infer(send, data)
        except HttpError as exc:
            await respond_error(send, exc.status, exc.message)
        finally:
            if not transferred:
                self.slot.release()

    async def _lifespan(self, receive, send):
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif event["type"] == "lifespan.shutdown":
                if self.tasks:
                    await asyncio.gather(*self.tasks, return_exceptions=True)
                await send({"type": "lifespan.shutdown.complete"})
                return

    def _metrics(self):
        return (
            "# TYPE kev_busy gauge\n"
            f"kev_busy {int(self.slot.locked())}\n"
            "# TYPE kev_busy_rejections_total counter\n"
            f"kev_busy_rejections_total {self.busy_rejections}\n"
        )

    def _authorized(self, headers):
        if self.token_digest is None:
            return True

        values = [v for k, v in headers if k.lower() == b"authorization"]
        value = values[0] if len(values) == 1 else b""
        provided = value[7:] if value.startswith(b"Bearer ") else b""
        return hmac.compare_digest(hashlib.sha256(provided).digest(), self.token_digest)

    async def _read_json_body(self, headers, receive):
        header_map = dict(headers)
        if header_map.get(b"content-type", b"").split(b";", 1)[0].strip() != b"application/json":
            raise HttpError(415, "application/json required")

        length = header_map.get(b"content-length", b"0")
        if not length.isdigit():
            raise HttpError(400, "invalid content-length")
        if int(length) > MAX_BODY:
            raise HttpError(413, BODY_TOO_LARGE)

        body = bytearray()
        try:
            async with asyncio.timeout(BODY_READ_TIMEOUT_SECONDS):
                while True:
                    event = await receive()
                    if event["type"] == "http.disconnect":
                        return None

                    chunk = event.get("body", b"")
                    if len(body) + len(chunk) > MAX_BODY:
                        raise HttpError(413, BODY_TOO_LARGE)
                    body.extend(chunk)
                    if not event.get("more_body", False):
                        break
        except TimeoutError:
            raise HttpError(408, "body read timeout") from None

        try:
            return validate(json.loads(body, object_pairs_hook=_object), self.engine.model)
        except (ValueError, RecursionError, InvalidRequest):
            raise HttpError(422, "invalid request") from None

    async def _infer(self, send, data):
        # The worker owns release. Cancelling the HTTP task cannot free the GPU.
        task = asyncio.create_task(asyncio.to_thread(self.work, data))
        self.tasks.add(task)
        task.add_done_callback(self.finished)
        try:
            result = await asyncio.shield(task)
        except InvalidRequest as exc:
            return await respond_error(send, 422, str(exc))
        except Exception:
            return await respond_error(send, 500, "inference failed")

        await respond_json(send, 200, result)

    def work(self, data):
        try:
            return self.engine.answer(data)
        except InvalidRequest:
            raise
        except InvalidModelOutput as exc:
            log.error("invalid_model_output error=%s", type(exc).__name__)
            raise
        except Exception as exc:
            log.error("inference_failed error=%s", type(exc).__name__)
            raise
        finally:
            self.slot.release()

    def finished(self, task):
        self.tasks.discard(task)
        if not task.cancelled():
            task.exception()  # work() has logged it; consume it after the caller goes away.


async def respond_json(send, status, payload):
    body = json.dumps(payload, allow_nan=False).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if status == 429:
        headers.append((b"retry-after", b"1"))

    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def respond_text(send, status, text):
    body = text.encode()
    headers = [(b"content-type", b"text/plain; version=0.0.4"), (b"content-length", str(len(body)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def respond_error(send, status, message):
    await respond_json(send, status, {"error": {"message": message}})


def installed_commit():
    """The commit pip records (PEP 610) when Kev is installed from Git."""
    try:
        recorded = importlib.metadata.distribution("kev").read_text("direct_url.json")
    except importlib.metadata.PackageNotFoundError:
        return None

    return json.loads(recorded or "{}").get("vcs_info", {}).get("commit_id")


def verify_source(root, commit, allow_unpinned, installed=None):
    """Verify Kev is the pinned upstream commit: a clean checkout, or installed from Git.

    Any other installed copy has nothing to verify, so accepting one is a real
    weakening that must be asked for.
    """
    if not (root / ".git").is_dir():
        if installed == commit or allow_unpinned:
            return
        raise RuntimeError(
            "Kev is neither a checkout nor installed from Git at the pinned commit; "
            "pin the source at build time and pass --allow-unpinned-source"
        )
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--", "kev"], text=True)
    if head != commit or dirty:
        raise RuntimeError("requires the clean pinned Kev source checkout")


def load_engine(release=None):
    release = release or Release()
    spec = importlib.util.find_spec("kev")
    if spec is None or spec.origin is None:
        raise RuntimeError("Kev is not importable")

    verify_source(Path(spec.origin).resolve().parent.parent, release.upstream_commit,
                  release.allow_unpinned, installed_commit())
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


def warm_engine(engine):
    started = time.perf_counter()
    cached_state = "ok " * (PREFIX_CACHE_MIN_TOKENS + 1)
    questions = {
        "state": {"type": "choice", "instructions": "Choose the state.",
                  "criteria": {"ready": "Ready", "error": "Error"}},
        "ready": {"type": "noul", "instructions": "Is the state ready?"},
        "quality": {"type": "score", "instructions": "Rate readiness.",
                    "criteria": ["Not ready", "Ready"]},
    }
    for state in ("Ready", cached_state, cached_state):
        engine.answer({"model": engine.model, "state": state, "questions": questions})

    engine.server.prefix_cache.clear()
    log.info("Runtime warmup completed in %.3fs", time.perf_counter() - started)


@dataclasses.dataclass(frozen=True)
class Options:
    release: Release
    token: bytes | None
    host: str
    port: int


def read_token(path):
    token = Path(path).read_bytes().rstrip(b"\r\n")
    if not 16 <= len(token) <= 4096 or any(c < 33 or c > 126 for c in token):
        raise ValueError("token file must contain 16..4096 printable non-space ASCII bytes")

    return token


def parse_options(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8009)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--revision")
    parser.add_argument("--base")
    parser.add_argument("--base-revision")
    parser.add_argument("--upstream-commit")
    parser.add_argument("--device", default="cuda", choices=("cuda", "cpu"))
    parser.add_argument("--dtype", default="bfloat16", choices=("bfloat16", "float32"))
    parser.add_argument("--allow-unpinned-source", action="store_true")
    args = parser.parse_args(argv)

    pinned = (args.model, args.revision, args.base, args.base_revision, args.upstream_commit)
    placement = {"device": args.device, "dtype": args.dtype, "allow_unpinned": args.allow_unpinned_source}
    if all(value is None for value in pinned):
        release = Release(**placement)
    elif all(value is not None for value in pinned):
        release = Release(model=args.model, revision=args.revision, base=args.base,
                          base_revision=args.base_revision or None,
                          upstream_commit=args.upstream_commit, **placement)
    else:
        parser.error("--model, --revision, --base, --base-revision and --upstream-commit go together")

    token = None
    if args.token_file:
        try:
            token = read_token(args.token_file)
        except ValueError as exc:
            parser.error(str(exc))

    return Options(release, token, args.host, args.port)


def main():
    options = parse_options()
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    import uvicorn
    engine = load_engine(options.release)
    warm_engine(engine)
    uvicorn.run(App(engine, options.token),
                host=options.host, port=options.port,
                workers=1, limit_concurrency=64, timeout_keep_alive=5, access_log=False)


if __name__ == "__main__":
    main()
