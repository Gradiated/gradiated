"""Per-request latency of linden-1, TypeSafe Jev 1.14 and OpenAI GPT-6 Luna on identical requests, one at a time.

Usage: python latency_compare.py EXAMPLES.json OUT.jsonl --linden URL [--repeats 7]
Needs OPENAI_API_KEY and TYPESAFE_API_KEY. Requests: the post's examples plus synthetic support tickets of about 200,
1,000 and 3,000 tokens with 1 and 4 questions; every timed request differs from the previous one in its first line, so
no cache answers it. Each provider is called in its native format (gdecide.backends.api); latency is wall time at the
client, so it includes the network: the script also reports each endpoint's median TCP connect time.
"""

import argparse
import json
import os
import socket
import statistics
import sys
import time
import uuid
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import requests  # noqa: E402

from gdecide.backends import api  # noqa: E402

PARAGRAPH = ("Customer writes that the order arrived late and one item was damaged in transit. They attached two "
             "photos, mention a previous refund that took three weeks, and ask whether a replacement can ship "
             "before Friday. The account is on the business plan and has eleven open seats. ")
ONE = {"refund": {"type": "noul", "instructions": "Should this ticket be routed to the refunds team?"}}
FOUR = {**ONE,
        "urgency": {"type": "choice", "instructions": "How urgent is this ticket?",
                    "criteria": {"low": None, "normal": None, "high": None}},
        "sentiment": {"type": "score", "instructions": "How satisfied is the customer?",
                      "criteria": ["very unhappy", "unhappy", "neutral", "happy", "very happy"]},
        "escalate": {"type": "noul", "instructions": "Should a manager review this ticket?"}}


class Linden:
    def __init__(self, url, model):
        self.url, self.model, self.session = url.rstrip("/") + "/v1/systemone", model, requests.Session()

    def one(self, request):
        r = self.session.post(self.url, json={"model": self.model, **request}, timeout=120)
        r.raise_for_status()
        return r.json()


def connect_ms(url):
    host = urlparse(url).hostname
    port = urlparse(url).port or (443 if url.startswith("https") else 80)
    times = []
    for _ in range(5):
        t = time.perf_counter()
        socket.create_connection((host, port), timeout=10).close()
        times.append((time.perf_counter() - t) * 1000)
    return round(statistics.median(times), 1)


def vary(state):
    """The same state with a fresh request id first, so no cache can answer a timed request."""
    tag = f"request {uuid.uuid4()}"
    if isinstance(state, dict) and set(state) == {"messages"}:
        first, *rest = state["messages"]
        return {"messages": [{**first, "content": f"{tag}\n{first['content']}"}, *rest]}
    if isinstance(state, dict):
        return {"request_id": tag, **state}
    return f"{tag}\n{state}"


def cases(examples):
    if examples and "description" in examples[0]:  # latency_cases.json: representative requests, varied per call
        for ex in examples:
            yield ex["name"], lambda ex=ex: {"state": vary(ex["state"]), "questions": ex["questions"]}
        return
    for ex in examples:
        yield ex["name"], lambda ex=ex: {"state": ex["state"], "questions": ex["questions"]}
    for size, n in (("200", 4), ("1000", 20), ("3000", 60)):
        for name, qs in (("1q", ONE), ("4q", FOUR)):
            yield f"ticket-{size}-{name}", lambda n=n, qs=qs: {
                "state": {"ticket": {"id": str(uuid.uuid4()), "body": PARAGRAPH * n}}, "questions": qs}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("examples"); p.add_argument("out")
    p.add_argument("--linden"); p.add_argument("--linden-model", default="gradiated/linden-1")
    p.add_argument("--models", default="linden-1,jev-1.14,gpt-6-luna")
    p.add_argument("--repeats", type=int, default=7)
    a = p.parse_args()
    wanted = a.models.split(",")
    make_client = {"linden-1": lambda: Linden(a.linden, a.linden_model), "jev-1.14": lambda: api.TypeSafe(workers=1),
                   "gpt-6-luna": lambda: api.OpenAIDecisions(workers=1)}
    models = {m: make_client[m]() for m in wanted}
    urls = {m: u for m, u in (("linden-1", a.linden), ("jev-1.14", api.TypeSafe.URL),
                              ("gpt-6-luna", api.OpenAIDecisions.URL)) if m in wanted}
    print(json.dumps({"connect_ms": {m: connect_ms(u) for m, u in urls.items()}}), flush=True)
    with open(a.out, "a") as f:
        for name, make in cases(json.load(open(a.examples))):
            for model, client in models.items():
                warm = client.one(make())  # warm the connection
                tokens = (warm.get("usage") or {}).get("input_tokens")
                times = []
                for _ in range(a.repeats):
                    request = make()
                    t = time.perf_counter()
                    client.one(request)
                    times.append((time.perf_counter() - t) * 1000)
                row = {"case": name, "model": model, "median_ms": round(statistics.median(times), 1),
                       "p90_ms": round(sorted(times)[int(0.9 * (len(times) - 1))], 1), "min_ms": round(min(times), 1),
                       "input_tokens": tokens}
                f.write(json.dumps(row) + "\n"); f.flush(); print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
