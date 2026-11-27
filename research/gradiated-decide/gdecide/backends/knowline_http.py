"""KnowLine through its own release server: SGLang (prefix cache) behind ``knowline_server.py``'s /v1/systemone.

``vm/serve-knowline.sh`` starts one server per GPU with the release settings (``serve_knowline.sh``: read twice,
question header past 32,768 tokens, ``temperatures.json``); rank ``r`` of ``gdecide.evaluate --backend knowline-http``
sends its requests to port ``base_port + local_rank``, ``workers`` at a time. The transformers backend
(``gdecide.backends.knowline``) gives the same prompts but has no prefix cache, about 4x the prefill.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import requests


class Unsupported(ValueError):
    """The server rejected the request (HTTP 413 or 422), as the release front end reports unsupported requests."""


class KnowLineHTTP:
    unsupported = (Unsupported,)

    def __init__(self, url: str, workers: int = 32, timeout: float = 1800.0):
        self.url, self.workers, self.timeout = url.rstrip("/"), int(workers), float(timeout)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=self.workers, pool_maxsize=self.workers)
        self.session.mount("http://", adapter)
        self.settings = {"server": self.url, "workers": self.workers, "layout": "release serve_knowline.sh"}

    def one(self, request: dict) -> dict:
        r = self.session.post(f"{self.url}/v1/systemone", json={"state": request["state"],
                              "questions": request["questions"]}, timeout=self.timeout)
        if r.status_code in (413, 422):
            raise Unsupported(r.json().get("error", r.text)[:2000])
        r.raise_for_status()
        body = r.json()
        return {"answers": body["answers"], "usage": body.get("usage", {})}

    def decide(self, requests_, temperature: float | None = None):
        if temperature not in (None, 1.0):
            raise ValueError("KnowLine's temperature is set by the server")
        if isinstance(requests_, dict):
            return self.one(requests_)
        with ThreadPoolExecutor(self.workers) as pool:
            return list(pool.map(self.one, requests_))
