"""Hosted decision APIs as evaluation backends: OpenAI's Decisions API (GPT-6 Luna) and TypeSafe's SystemOne API (Jev).

Evaluation only: answers from these models are scored and never written to any training data.

Both map our SystemOne request ({"state", "questions"}) to the vendor format and return our answer format
(noul -> {"noul": p}; choice -> {"probabilities": {key: p}}; score -> {"probabilities": {"0": p, ...}}), so
``gdecide.external`` scores them exactly like a local model. Requests run in parallel threads with retries on 429/5xx.

- OpenAI: POST https://api.openai.com/v1/decisions, model gpt-6-luna. noul -> predicate (criteria appended to the
  instructions), choice -> choices [{value, description}], score -> levels [{label, description}] (2-10 levels).
  A string state is sent as input text; an object state as an input_json part of one user message.
- TypeSafe: POST https://api.typesafe.ai/v1/systemone, the same request format as ours, model jev-1.14.0 (pinned).
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import random
import time

import requests


class Unsupported(ValueError):
    pass


def _text(v):
    """OpenAI wants strings; structured criteria (arrays/objects) are sent as their JSON text."""
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def _post(session, url, body, headers, timeout=120, attempts=8):
    for attempt in range(attempts):
        try:
            r = session.post(url, json=body, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            error = f"{type(e).__name__}: {e}"
        else:
            if r.status_code < 400:
                return r.json()
            error = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code not in (408, 409, 429) and r.status_code < 500:
                raise Unsupported(error)
        time.sleep(min(60, 2 ** attempt) * (0.5 + random.random()))
    raise RuntimeError(error)


class _Parallel:
    unsupported = (Unsupported,)

    def __init__(self, workers: int):
        self.workers = int(workers)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=self.workers, pool_maxsize=self.workers)
        self.session.mount("https://", adapter)
        self.temperature = 1.0

    def decide(self, requests_, temperature=None):
        if isinstance(requests_, dict):
            return self.one(requests_)

        def safe(r):
            try:
                return self.one(r)
            except Exception as e:  # noqa: BLE001  one failed item is recorded as an error, not the whole chunk
                return {"error": f"{type(e).__name__}: {e}"[:400]}

        with concurrent.futures.ThreadPoolExecutor(self.workers) as ex:
            return list(ex.map(safe, requests_))


class OpenAIDecisions(_Parallel):
    URL = "https://api.openai.com/v1/decisions"

    def __init__(self, model: str = "gpt-6-luna", workers: int = 32):
        super().__init__(workers)
        self.model = model
        self.headers = {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}
        self.settings = {"api": self.URL, "model": model, "workers": self.workers}

    @staticmethod
    def question(name, q):
        kind, crit = q["type"], q.get("criteria")
        if kind == "noul":
            text = q["instructions"]
            if crit:
                text += f"\nTrue means: {_text(crit.get('true'))}\nFalse means: {_text(crit.get('false'))}"
            return {"name": name, "type": "predicate", "instructions": _text(text)}
        if kind == "choice":
            items = crit.items() if isinstance(crit, dict) else ((c, None) for c in crit)
            return {"name": name, "type": "choice", "instructions": _text(q["instructions"]),
                    "choices": [{"value": k, "description": _text(v) if v else k} for k, v in items]}
        if kind == "score":
            if not 2 <= len(crit) <= 10:
                raise Unsupported(f"score with {len(crit)} levels")
            return {"name": name, "type": "score", "instructions": _text(q["instructions"]),
                    "levels": [{"label": str(i), "description": _text(d)} for i, d in enumerate(crit)]}
        raise Unsupported(f"question type {kind}")

    def one(self, request):
        state = request["state"]
        if isinstance(state, str):
            input_ = state
        else:
            input_ = [{"role": "user", "content": [{"type": "input_json", "data": state}]}]
        body = {"model": self.model, "input": input_,
                "questions": [self.question(k, q) for k, q in request["questions"].items()]}
        r = _post(self.session, self.URL, body, self.headers)
        answers = {}
        for a in r["answers"]:
            q = request["questions"].get(a["name"])
            if a["type"] == "refusal" or q is None:
                raise Unsupported(f"refusal: {json.dumps(a)[:200]}")
            if a["type"] == "predicate":
                answers[a["name"]] = {"type": "noul", "noul": float(a["probability"])}
            elif a["type"] == "choice":
                answers[a["name"]] = {"type": "choice", "choice": a["choice"], "probabilities": {
                    p["value"]: float(p["probability"]) for p in a["probabilities"]}}
            elif a["type"] == "score":
                answers[a["name"]] = {"type": "score", "score": float(a["score"]), "probabilities": {
                    str(p["label"]): float(p["probability"]) for p in a["probabilities"]}}
        return {"answers": answers, "usage": r.get("usage", {})}


class TypeSafe(_Parallel):
    URL = "https://api.typesafe.ai/v1/systemone"

    def __init__(self, model: str = "jev-1.14.0", workers: int = 32):
        super().__init__(workers)
        self.model = model
        self.headers = {"Authorization": "Bearer " + os.environ["TYPESAFE_API_KEY"]}
        self.settings = {"api": self.URL, "model": model, "workers": self.workers}

    def one(self, request):
        body = {"model": self.model, "state": request["state"], "questions": request["questions"]}
        r = _post(self.session, self.URL, body, self.headers)
        if r.get("model") and not str(r["model"]).endswith(self.model):
            raise RuntimeError(f"answered by {r['model']}, not {self.model}")
        return {"answers": r["answers"], "usage": r.get("usage", {})}
